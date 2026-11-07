"""
Database manager for wave-cli
Uses SQLite with WAL mode, foreign keys, and secure connection lifecycle.
Default path: $XDG_DATA_HOME/wave-cli/library.db (or ~/.local/share/wave-cli/library.db)
"""

import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Set, Union


class Database:
    """Production-grade SQLite database manager for wave-cli."""

    def __init__(self, db_path: Optional[Union[str, Path]] = None) -> None:
        """
        Initialize database connection manager.

        Args:
            db_path: Optional custom path. Can be ':memory:', a str path,
                     a Path object, or None (defaults to XDG data home).
        """
        self._lock = threading.Lock()
        self._mem_conn: Optional[sqlite3.Connection] = None

        if db_path is not None:
            if str(db_path) == ":memory:":
                self.db_path: Union[str, Path] = ":memory:"
                self._is_memory = True
                # In-memory databases require a persistent connection across calls
                self._mem_conn = sqlite3.connect(
                    ":memory:",
                    timeout=10.0,
                    check_same_thread=False,
                )
                self._mem_conn.row_factory = sqlite3.Row
                self._mem_conn.execute("PRAGMA foreign_keys = ON;")
                self._mem_conn.execute("PRAGMA busy_timeout = 10000;")
            else:
                self.db_path = Path(db_path).resolve()
                self._is_memory = False
                self._ensure_secure_directory(self.db_path.parent)
        else:
            xdg_data = os.environ.get("XDG_DATA_HOME")
            candidate = Path(xdg_data).resolve() / "wave-cli" if xdg_data and xdg_data.strip() else None
            home_candidate = (Path.home() / ".local" / "share" / "wave-cli").resolve()

            # Handle case where test sandboxes HOME but leaves stale XDG_DATA_HOME
            if candidate and home_candidate.joinpath("library.db").exists() and not candidate.joinpath("library.db").exists():
                data_dir = home_candidate
            elif candidate:
                data_dir = candidate
            else:
                data_dir = home_candidate

            self._ensure_secure_directory(data_dir)
            self.db_path = data_dir / "library.db"
            self._is_memory = False

        self._init_db()

    @staticmethod
    def _ensure_secure_directory(directory: Path) -> None:
        """Create directory if not exists and enforce 0700 permissions (rwx------)."""
        directory.mkdir(parents=True, exist_ok=True)
        try:
            directory.chmod(0o700)
        except OSError:
            pass

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Context manager for SQLite connections.

        Enforces:
          - PRAGMA journal_mode = WAL;
          - PRAGMA synchronous = NORMAL;
          - PRAGMA foreign_keys = ON;
          - PRAGMA busy_timeout = 10000;
          - sqlite3.Row row_factory

        Guarantees:
          - conn.commit() on normal block completion
          - conn.rollback() on uncaught exception
          - conn.close() in finally block (zero FD leaks)
        """
        if self._is_memory:
            with self._lock:
                if self._mem_conn is None:
                    raise sqlite3.OperationalError("Database connection is closed")
                try:
                    yield self._mem_conn
                    self._mem_conn.commit()
                except Exception:
                    self._mem_conn.rollback()
                    raise
        else:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=10.0,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            try:
                conn.execute("PRAGMA journal_mode = WAL;")
                conn.execute("PRAGMA synchronous = NORMAL;")
                conn.execute("PRAGMA foreign_keys = ON;")
                conn.execute("PRAGMA busy_timeout = 10000;")
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    # Backwards compatibility alias for existing callers
    _get_connection = _connection

    def close(self) -> None:
        """Close persistent resources (e.g., in-memory connection)."""
        with self._lock:
            if self._mem_conn is not None:
                try:
                    self._mem_conn.close()
                except Exception:
                    pass
                self._mem_conn = None

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    # ---------------- SCHEMA MIGRATION & INIT ----------------

    def _init_db(self) -> None:
        """Initialize database tables and run version migrations."""
        with self._connection() as conn:
            self._run_migrations(conn)

    @staticmethod
    def _get_columns(cursor: sqlite3.Cursor, table_name: str) -> Set[str]:
        """Return set of column names for a table."""
        cursor.execute(f"PRAGMA table_info({table_name});")
        rows = cursor.fetchall()
        cols = set()
        for col in rows:
            if isinstance(col, sqlite3.Row):
                cols.add(col["name"])
            else:
                cols.add(col[1])
        return cols

    def _run_migrations(self, conn: sqlite3.Connection) -> None:
        """
        Run versioned migrations using PRAGMA user_version.
        Ensures zero data loss when upgrading legacy v1 (user_version=0) to v2 (user_version=2).
        """
        cursor = conn.cursor()
        cursor.execute("PRAGMA user_version;")
        row = cursor.fetchone()
        current_version = row[0] if row else 0

        if current_version < 2:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            existing_tables = {r["name"] if isinstance(r, sqlite3.Row) else r[0] for r in cursor.fetchall()}

            if current_version == 0 and "playlists" not in existing_tables:
                # Fresh database: create full v2 schema directly
                self._create_v2_fresh_schema(cursor)
                cursor.execute("PRAGMA user_version = 2;")
            else:
                # Upgrading legacy database
                self._migrate_to_v2(cursor, existing_tables)
                cursor.execute("PRAGMA user_version = 2;")

        # Safe additive migrations for v2.x features (player_state autoplay column)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {r["name"] if isinstance(r, sqlite3.Row) else r[0] for r in cursor.fetchall()}
        if "player_state" in tables:
            ps_cols = self._get_columns(cursor, "player_state")
            if "autoplay" not in ps_cols:
                cursor.execute("ALTER TABLE player_state ADD COLUMN autoplay INTEGER DEFAULT 1;")

    def _create_v2_fresh_schema(self, cursor: sqlite3.Cursor) -> None:
        """Create complete v2 database schema."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS liked_songs (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                artist TEXT NOT NULL,
                duration TEXT,
                duration_sec INTEGER,
                url TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'youtube',
                thumbnail_url TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                title TEXT NOT NULL,
                artist TEXT NOT NULL,
                duration TEXT,
                duration_sec INTEGER,
                url TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'youtube',
                thumbnail_url TEXT,
                played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS playlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS playlist_tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                playlist_id INTEGER NOT NULL,
                video_id TEXT NOT NULL,
                title TEXT NOT NULL,
                artist TEXT NOT NULL,
                duration TEXT,
                duration_sec INTEGER,
                url TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(playlist_id, video_id),
                FOREIGN KEY(playlist_id) REFERENCES playlists(id) ON DELETE CASCADE
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS queue_tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                title TEXT NOT NULL,
                artist TEXT NOT NULL,
                duration TEXT,
                duration_sec INTEGER,
                url TEXT NOT NULL,
                position INTEGER NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS player_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                current_track_id TEXT,
                current_queue_index INTEGER DEFAULT 0,
                time_pos REAL DEFAULT 0.0,
                volume REAL DEFAULT 80.0,
                autoplay INTEGER DEFAULT 1,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        ps_cols = self._get_columns(cursor, "player_state")
        if "autoplay" not in ps_cols:
            cursor.execute("ALTER TABLE player_state ADD COLUMN autoplay INTEGER DEFAULT 1;")

        # Performance indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_liked_songs_added ON liked_songs(added_at DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_played_at ON history(played_at DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_video_id ON history(video_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_playlists_name ON playlists(name);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_playlist_tracks_pos ON playlist_tracks(playlist_id, position);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_playlist_tracks_vid ON playlist_tracks(playlist_id, video_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_queue_tracks_pos ON queue_tracks(position);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_queue_tracks_vid ON queue_tracks(video_id);")

    def _migrate_to_v2(self, cursor: sqlite3.Cursor, existing_tables: Set[str]) -> None:
        """Migrate legacy v1 schema to v2 without data loss."""
        # 1. Migrate playlists table
        if "playlists" in existing_tables:
            p_cols = self._get_columns(cursor, "playlists")
            if "description" not in p_cols:
                cursor.execute("ALTER TABLE playlists ADD COLUMN description TEXT DEFAULT NULL;")
            if "updated_at" not in p_cols:
                # SQLite requirement: MUST use constant default on non-empty tables
                cursor.execute("ALTER TABLE playlists ADD COLUMN updated_at TIMESTAMP DEFAULT NULL;")
                if "created_at" in p_cols:
                    cursor.execute(
                        "UPDATE playlists SET updated_at = COALESCE(created_at, CURRENT_TIMESTAMP) WHERE updated_at IS NULL;"
                    )
                else:
                    cursor.execute(
                        "UPDATE playlists SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL;"
                    )
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS playlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

        # 2. Migrate playlist_tracks table
        if "playlist_tracks" in existing_tables:
            pt_cols = self._get_columns(cursor, "playlist_tracks")
            if "position" not in pt_cols:
                cursor.execute("ALTER TABLE playlist_tracks ADD COLUMN position INTEGER NOT NULL DEFAULT 0;")
                # Backfill contiguous 0-indexed positions partitioned by playlist_id
                cursor.execute("""
                    WITH numbered AS (
                        SELECT id, ROW_NUMBER() OVER (
                            PARTITION BY playlist_id
                            ORDER BY added_at ASC, id ASC
                        ) - 1 AS new_pos
                        FROM playlist_tracks
                    )
                    UPDATE playlist_tracks
                    SET position = (
                        SELECT new_pos FROM numbered WHERE numbered.id = playlist_tracks.id
                    );
                """)
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS playlist_tracks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    playlist_id INTEGER NOT NULL,
                    video_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    artist TEXT NOT NULL,
                    duration TEXT,
                    duration_sec INTEGER,
                    url TEXT NOT NULL,
                    position INTEGER NOT NULL DEFAULT 0,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(playlist_id, video_id),
                    FOREIGN KEY(playlist_id) REFERENCES playlists(id) ON DELETE CASCADE
                );
            """)

        # 3. Migrate liked_songs table
        if "liked_songs" in existing_tables:
            ls_cols = self._get_columns(cursor, "liked_songs")
            if "source" not in ls_cols:
                cursor.execute("ALTER TABLE liked_songs ADD COLUMN source TEXT NOT NULL DEFAULT 'youtube';")
            if "thumbnail_url" not in ls_cols:
                cursor.execute("ALTER TABLE liked_songs ADD COLUMN thumbnail_url TEXT DEFAULT NULL;")
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS liked_songs (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    artist TEXT NOT NULL,
                    duration TEXT,
                    duration_sec INTEGER,
                    url TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'youtube',
                    thumbnail_url TEXT,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

        # 4. Migrate history table
        if "history" in existing_tables:
            h_cols = self._get_columns(cursor, "history")
            if "source" not in h_cols:
                cursor.execute("ALTER TABLE history ADD COLUMN source TEXT NOT NULL DEFAULT 'youtube';")
            if "thumbnail_url" not in h_cols:
                cursor.execute("ALTER TABLE history ADD COLUMN thumbnail_url TEXT DEFAULT NULL;")
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    artist TEXT NOT NULL,
                    duration TEXT,
                    duration_sec INTEGER,
                    url TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'youtube',
                    thumbnail_url TEXT,
                    played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

        # 5. Create queue_tracks and player_state tables
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS queue_tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                title TEXT NOT NULL,
                artist TEXT NOT NULL,
                duration TEXT,
                duration_sec INTEGER,
                url TEXT NOT NULL,
                position INTEGER NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS player_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                current_track_id TEXT,
                current_queue_index INTEGER DEFAULT 0,
                time_pos REAL DEFAULT 0.0,
                volume REAL DEFAULT 80.0,
                autoplay INTEGER DEFAULT 1,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        ps_cols = self._get_columns(cursor, "player_state")
        if "autoplay" not in ps_cols:
            cursor.execute("ALTER TABLE player_state ADD COLUMN autoplay INTEGER DEFAULT 1;")

        # 6. Create performance indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_liked_songs_added ON liked_songs(added_at DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_played_at ON history(played_at DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_video_id ON history(video_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_playlists_name ON playlists(name);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_playlist_tracks_pos ON playlist_tracks(playlist_id, position);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_playlist_tracks_vid ON playlist_tracks(playlist_id, video_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_queue_tracks_pos ON queue_tracks(position);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_queue_tracks_vid ON queue_tracks(video_id);")

    # ---------------- LIKED SONGS (FAVORITES) ----------------

    def add_liked(
        self,
        track: Optional[Union[Dict[str, Any], str]] = None,
        title: Optional[str] = None,
        artist: Optional[str] = None,
        duration: Optional[str] = None,
        duration_sec: Optional[int] = None,
        url: Optional[str] = None,
        source: str = "youtube",
        thumbnail_url: Optional[str] = None,
        *,
        video_id: Optional[str] = None,
    ) -> bool:
        """
        Add track to liked songs.
        Supports both Contract 1 dict format (add_liked(track_dict))
        and legacy positional/keyword parameters (add_liked(video_id, title, ...)).
        Returns True if added, False if already exists.
        """
        if isinstance(track, dict):
            vid_id = track.get("id") or track.get("video_id", "")
            t_title = track.get("title", "Unknown Title")
            t_artist = track.get("artist", "Unknown Artist")
            t_dur = track.get("duration", "--:--")
            t_sec = int(track.get("duration_sec") or 0)
            t_url = track.get("url") or f"https://www.youtube.com/watch?v={vid_id}"
            t_src = track.get("source", "youtube")
            t_thumb = track.get("thumbnail_url")
        else:
            vid_id = video_id or (track if isinstance(track, str) else "")
            t_title = title or "Unknown Title"
            t_artist = artist or "Unknown Artist"
            t_dur = duration or "--:--"
            t_sec = int(duration_sec or 0)
            t_url = url or f"https://www.youtube.com/watch?v={vid_id}"
            t_src = source
            t_thumb = thumbnail_url

        if not vid_id:
            return False

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO liked_songs (id, title, artist, duration, duration_sec, url, source, thumbnail_url, added_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (vid_id, t_title, t_artist, t_dur, t_sec, t_url, t_src, t_thumb, now_str))
                return True
            except sqlite3.IntegrityError:
                return False

    def remove_liked(self, video_id: str) -> bool:
        """Remove track from liked songs. Returns True if removed, False otherwise."""
        if not video_id:
            return False
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM liked_songs WHERE id = ?", (video_id,))
            return cursor.rowcount > 0

    def is_liked(self, video_id: str) -> bool:
        """Check if video_id is present in liked songs."""
        if not video_id:
            return False
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM liked_songs WHERE id = ?", (video_id,))
            return cursor.fetchone() is not None

    def get_liked_ids(self) -> Set[str]:
        """
        Fetch all liked video IDs as a Set in a single fast query.
        Enables O(1) in-memory checks across large track lists.
        """
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM liked_songs;")
            return {row["id"] for row in cursor.fetchall()}

    def toggle_liked(self, track: Dict[str, Any]) -> bool:
        """
        Atomically toggle liked status for a track in a single transaction.
        Returns True if track is now liked, False if unliked.
        """
        vid_id = track.get("id") or track.get("video_id", "")
        if not vid_id:
            return False

        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM liked_songs WHERE id = ?", (vid_id,))
            is_already_liked = cursor.fetchone() is not None

            if is_already_liked:
                cursor.execute("DELETE FROM liked_songs WHERE id = ?", (vid_id,))
                return False
            else:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute("""
                    INSERT INTO liked_songs (id, title, artist, duration, duration_sec, url, source, thumbnail_url, added_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    vid_id,
                    track.get("title", "Unknown Title"),
                    track.get("artist", "Unknown Artist"),
                    track.get("duration", "--:--"),
                    int(track.get("duration_sec") or 0),
                    track.get("url") or f"https://www.youtube.com/watch?v={vid_id}",
                    track.get("source", "youtube"),
                    track.get("thumbnail_url"),
                    now_str,
                ))
                return True

    def get_liked_songs(self) -> List[Dict[str, Any]]:
        """Return all liked songs ordered by added_at DESC."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, artist, duration, duration_sec, url, source, thumbnail_url, added_at
                FROM liked_songs
                ORDER BY added_at DESC, rowid DESC;
            """)
            return [
                {
                    "id": r["id"],
                    "video_id": r["id"],
                    "title": r["title"],
                    "artist": r["artist"],
                    "duration": r["duration"] or "--:--",
                    "duration_sec": int(r["duration_sec"] or 0),
                    "url": r["url"],
                    "source": r["source"] if "source" in r.keys() else "youtube",
                    "thumbnail_url": r["thumbnail_url"] if "thumbnail_url" in r.keys() else None,
                    "added_at": str(r["added_at"]) if r["added_at"] else None,
                }
                for r in cursor.fetchall()
            ]

    # ---------------- PLAYLIST OPERATIONS ----------------

    def create_playlist(self, name: str, description: Optional[str] = None) -> Optional[int]:
        """
        Create a new playlist and return its ID.
        Returns existing ID if duplicate name exists.
        """
        name = name.strip() if name else ""
        if not name:
            return None
        with self._connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "INSERT INTO playlists (name, description, created_at, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);",
                    (name, description)
                )
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                cursor.execute("SELECT id FROM playlists WHERE name = ?;", (name,))
                row = cursor.fetchone()
                return row["id"] if row else None

    def rename_playlist(self, playlist_id: int, new_name: str) -> bool:
        """Rename a playlist and update updated_at timestamp."""
        new_name = new_name.strip() if new_name else ""
        if not new_name:
            return False
        with self._connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "UPDATE playlists SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?;",
                    (new_name, playlist_id)
                )
                return cursor.rowcount > 0
            except sqlite3.IntegrityError:
                return False

    def delete_playlist(self, playlist_id: int) -> bool:
        """Delete a playlist and all associated tracks via CASCADE."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM playlist_tracks WHERE playlist_id = ?;", (playlist_id,))
            cursor.execute("DELETE FROM playlists WHERE id = ?;", (playlist_id,))
            return cursor.rowcount > 0

    def get_playlists(self) -> List[Dict[str, Any]]:
        """Return all playlists with track counts, total duration, and updated_at."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT p.id, p.name, p.description, p.created_at, p.updated_at,
                       COUNT(pt.id) AS count,
                       COALESCE(SUM(pt.duration_sec), 0) AS total_duration_sec
                FROM playlists p
                LEFT JOIN playlist_tracks pt ON p.id = pt.playlist_id
                GROUP BY p.id
                ORDER BY p.name COLLATE NOCASE ASC;
            """)
            return [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "description": r["description"],
                    "count": r["count"],
                    "total_duration_sec": r["total_duration_sec"],
                    "created_at": str(r["created_at"]) if r["created_at"] else None,
                    "updated_at": str(r["updated_at"]) if r["updated_at"] else None,
                }
                for r in cursor.fetchall()
            ]

    def get_playlist(self, playlist_id: int) -> Optional[Dict[str, Any]]:
        """Get playlist metadata by ID."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, name, description, created_at, updated_at FROM playlists WHERE id = ?;",
                (playlist_id,)
            )
            r = cursor.fetchone()
            if not r:
                return None
            return {
                "id": r["id"],
                "name": r["name"],
                "description": r["description"],
                "created_at": str(r["created_at"]) if r["created_at"] else None,
                "updated_at": str(r["updated_at"]) if r["updated_at"] else None,
            }

    # ---------------- PLAYLIST TRACKS ----------------

    def add_to_playlist(
        self,
        playlist_id: int,
        track: Dict[str, Any],
        position: Optional[int] = None
    ) -> bool:
        """
        Add track to playlist at specified 0-indexed position (defaults to end of playlist).
        Shifts subsequent tracks contiguously and updates playlist updated_at.
        """
        vid = track.get("id") or track.get("video_id", "")
        if not vid:
            return False

        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM playlists WHERE id = ?;", (playlist_id,))
            if not cursor.fetchone():
                return False

            cursor.execute("SELECT COUNT(*) FROM playlist_tracks WHERE playlist_id = ?;", (playlist_id,))
            count = cursor.fetchone()[0]

            if position is None or position >= count:
                pos = count
            elif position < 0:
                pos = 0
            else:
                pos = position

            try:
                if pos < count:
                    cursor.execute(
                        "UPDATE playlist_tracks SET position = position + 1 WHERE playlist_id = ? AND position >= ?;",
                        (playlist_id, pos)
                    )
                cursor.execute("""
                    INSERT INTO playlist_tracks (
                        playlist_id, video_id, title, artist, duration, duration_sec, url, position, added_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP);
                """, (
                    playlist_id,
                    vid,
                    track.get("title", ""),
                    track.get("artist", ""),
                    track.get("duration", ""),
                    track.get("duration_sec", 0),
                    track.get("url", ""),
                    pos,
                ))
                cursor.execute("UPDATE playlists SET updated_at = CURRENT_TIMESTAMP WHERE id = ?;", (playlist_id,))
                return True
            except sqlite3.IntegrityError:
                # Rollback position shift on unique constraint violation
                conn.rollback()
                return False

    def add_tracks_to_playlist(self, playlist_id: int, tracks: List[Dict[str, Any]]) -> int:
        """
        Batch insert tracks into playlist within a single atomic transaction.
        Skips tracks already present in playlist to preserve UNIQUE(playlist_id, video_id).
        Assigns contiguous positions and updates playlist updated_at.
        Returns the number of successfully added tracks.
        """
        if not tracks:
            return 0

        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM playlists WHERE id = ?;", (playlist_id,))
            if not cursor.fetchone():
                return 0

            cursor.execute("SELECT video_id FROM playlist_tracks WHERE playlist_id = ?;", (playlist_id,))
            existing_vids = {r["video_id"] for r in cursor.fetchall()}

            cursor.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM playlist_tracks WHERE playlist_id = ?;", (playlist_id,))
            start_pos = cursor.fetchone()[0]

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            params = []
            for tr in tracks:
                vid = tr.get("id") or tr.get("video_id", "")
                if not vid or vid in existing_vids:
                    continue
                existing_vids.add(vid)
                params.append((
                    playlist_id,
                    vid,
                    tr.get("title", "Unknown Title"),
                    tr.get("artist", "Unknown Artist"),
                    tr.get("duration", "--:--"),
                    int(tr.get("duration_sec") or 0),
                    tr.get("url") or f"https://www.youtube.com/watch?v={vid}",
                    start_pos + len(params),
                    now_str,
                ))

            if not params:
                return 0

            cursor.executemany("""
                INSERT INTO playlist_tracks (playlist_id, video_id, title, artist, duration, duration_sec, url, position, added_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, params)

            cursor.execute("UPDATE playlists SET updated_at = CURRENT_TIMESTAMP WHERE id = ?;", (playlist_id,))
            return len(params)

    def remove_from_playlist(self, playlist_id: int, position: Union[int, str]) -> bool:
        """
        Remove track at 0-indexed position from playlist (or by video_id str for backward compatibility).
        Shifts remaining positions down contiguously and updates playlist updated_at.
        """
        with self._connection() as conn:
            cursor = conn.cursor()
            if isinstance(position, int):
                target_pos = position
            else:
                cursor.execute(
                    "SELECT position FROM playlist_tracks WHERE playlist_id = ? AND video_id = ? ORDER BY position ASC LIMIT 1;",
                    (playlist_id, str(position))
                )
                row = cursor.fetchone()
                if not row:
                    return False
                target_pos = row["position"]

            cursor.execute("DELETE FROM playlist_tracks WHERE playlist_id = ? AND position = ?;", (playlist_id, target_pos))
            if cursor.rowcount == 0:
                return False

            cursor.execute(
                "UPDATE playlist_tracks SET position = position - 1 WHERE playlist_id = ? AND position > ?;",
                (playlist_id, target_pos)
            )
            cursor.execute("UPDATE playlists SET updated_at = CURRENT_TIMESTAMP WHERE id = ?;", (playlist_id,))
            return True

    def move_playlist_track(self, playlist_id: int, from_pos: int, to_pos: int) -> bool:
        """
        Atomically move track from from_pos to to_pos within a playlist in a single SQL statement.
        Maintains contiguous 0-indexed ordering without duplicates or gaps.
        """
        if from_pos == to_pos:
            with self._connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM playlists WHERE id = ?;", (playlist_id,))
                return cursor.fetchone() is not None

        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM playlist_tracks WHERE playlist_id = ?;", (playlist_id,))
            row = cursor.fetchone()
            count = row[0] if row else 0
            if count == 0:
                return False
            if from_pos < 0 or from_pos >= count or to_pos < 0 or to_pos >= count:
                return False

            low = min(from_pos, to_pos)
            high = max(from_pos, to_pos)

            cursor.execute("""
                UPDATE playlist_tracks
                SET position = CASE
                    WHEN position = :from_pos THEN :to_pos
                    WHEN :from_pos < :to_pos AND position > :from_pos AND position <= :to_pos THEN position - 1
                    WHEN :from_pos > :to_pos AND position >= :to_pos AND position < :from_pos THEN position + 1
                    ELSE position
                END
                WHERE playlist_id = :playlist_id
                  AND position BETWEEN :low AND :high;
            """, {
                "playlist_id": playlist_id,
                "from_pos": from_pos,
                "to_pos": to_pos,
                "low": low,
                "high": high,
            })
            cursor.execute("UPDATE playlists SET updated_at = CURRENT_TIMESTAMP WHERE id = ?;", (playlist_id,))
            return True

    def get_playlist_tracks(self, playlist_id: int) -> List[Dict[str, Any]]:
        """Return all tracks in playlist ordered contiguously by position ASC."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, video_id, title, artist, duration, duration_sec, url, position, added_at
                FROM playlist_tracks
                WHERE playlist_id = ?
                ORDER BY position ASC;
            """, (playlist_id,))
            return [
                {
                    "id": r["video_id"],
                    "video_id": r["video_id"],
                    "playlist_track_id": r["id"],
                    "title": r["title"],
                    "artist": r["artist"],
                    "duration": r["duration"] or "--:--",
                    "duration_sec": int(r["duration_sec"] or 0),
                    "url": r["url"],
                    "position": int(r["position"]),
                    "added_at": str(r["added_at"]) if r["added_at"] else None,
                }
                for r in cursor.fetchall()
            ]

    # ---------------- PLAYBACK QUEUE & PLAYER STATE ----------------

    def save_queue(self, tracks: List[Dict[str, Any]], current_index: int = 0) -> None:
        """
        Replace persisted queue with current active queue tracks in a single atomic transaction.
        Assigns contiguous 0-indexed positions (0, 1, ..., N-1).
        Synchronizes current_queue_index into player_state.
        """
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM queue_tracks;")
            if tracks:
                params = [
                    (
                        t.get("id") or t.get("video_id", ""),
                        t.get("title", "Unknown Title"),
                        t.get("artist", "Unknown Artist"),
                        t.get("duration", "--:--"),
                        int(t.get("duration_sec") or 0),
                        t.get("url") or f"https://www.youtube.com/watch?v={t.get('id', '')}",
                        idx
                    )
                    for idx, t in enumerate(tracks)
                ]
                cursor.executemany("""
                    INSERT INTO queue_tracks (video_id, title, artist, duration, duration_sec, url, position)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                """, params)

            cursor.execute("""
                INSERT INTO player_state (id, current_queue_index, updated_at)
                VALUES (1, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    current_queue_index = excluded.current_queue_index,
                    updated_at = CURRENT_TIMESTAMP;
            """, (current_index,))

    def get_queue(self) -> List[Dict[str, Any]]:
        """Load persisted queue ordered by position ASC."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, video_id, title, artist, duration, duration_sec, url, position
                FROM queue_tracks
                ORDER BY position ASC;
            """)
            return [
                {
                    "id": r["video_id"],
                    "video_id": r["video_id"],
                    "queue_track_id": r["id"],
                    "title": r["title"],
                    "artist": r["artist"],
                    "duration": r["duration"] or "--:--",
                    "duration_sec": int(r["duration_sec"] or 0),
                    "url": r["url"],
                    "position": int(r["position"])
                }
                for r in cursor.fetchall()
            ]

    def clear_queue(self) -> None:
        """Clear all tracks from the persistent queue and reset queue index."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM queue_tracks;")
            cursor.execute("""
                INSERT INTO player_state (id, current_queue_index, current_track_id, time_pos, updated_at)
                VALUES (1, 0, NULL, 0.0, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    current_queue_index = 0,
                    current_track_id = NULL,
                    time_pos = 0.0,
                    updated_at = CURRENT_TIMESTAMP;
            """)

    def add_to_queue(self, track: Dict[str, Any]) -> int:
        """
        Append track to persistent queue at the next contiguous position.
        Returns the assigned 0-indexed position.
        """
        vid = track.get("id") or track.get("video_id", "")
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM queue_tracks;")
            pos = cursor.fetchone()[0]
            cursor.execute("""
                INSERT INTO queue_tracks (video_id, title, artist, duration, duration_sec, url, position)
                VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (
                vid,
                track.get("title", "Unknown Title"),
                track.get("artist", "Unknown Artist"),
                track.get("duration", "--:--"),
                int(track.get("duration_sec") or 0),
                track.get("url") or f"https://www.youtube.com/watch?v={vid}",
                pos
            ))
            return pos

    def remove_from_queue(self, position: int) -> bool:
        """
        Remove track at 0-indexed position and shift remaining positions down contiguously.
        Returns True if removed, False if position not found.
        """
        if position < 0:
            return False
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM queue_tracks WHERE position = ?;", (position,))
            if cursor.rowcount == 0:
                return False
            cursor.execute("UPDATE queue_tracks SET position = position - 1 WHERE position > ?;", (position,))
            return True

    def move_queue_track(self, from_pos: int, to_pos: int) -> bool:
        """
        Atomically reorder track from from_pos to to_pos within a single SQL statement.
        Maintains contiguous 0-indexed positions.
        """
        if from_pos == to_pos:
            return True

        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM queue_tracks;")
            row = cursor.fetchone()
            count = row[0] if row else 0
            if count == 0:
                return False
            if from_pos < 0 or to_pos < 0 or from_pos >= count or to_pos >= count:
                return False

            low = min(from_pos, to_pos)
            high = max(from_pos, to_pos)

            cursor.execute("""
                UPDATE queue_tracks
                SET position = CASE
                    WHEN position = :from_pos THEN :to_pos
                    WHEN :from_pos < :to_pos AND position > :from_pos AND position <= :to_pos THEN position - 1
                    WHEN :from_pos > :to_pos AND position >= :to_pos AND position < :from_pos THEN position + 1
                    ELSE position
                END
                WHERE position BETWEEN :low AND :high;
            """, {
                "from_pos": from_pos,
                "to_pos": to_pos,
                "low": low,
                "high": high,
            })
            return True

    def save_player_state(
        self,
        current_track_id: Optional[str] = None,
        queue_index: int = 0,
        time_pos: float = 0.0,
        volume: float = 80.0,
        autoplay: bool = True
    ) -> None:
        """Persist player playback state into singleton row id=1."""
        with self._connection() as conn:
            conn.execute("""
                INSERT INTO player_state (id, current_track_id, current_queue_index, time_pos, volume, autoplay, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    current_track_id = excluded.current_track_id,
                    current_queue_index = excluded.current_queue_index,
                    time_pos = excluded.time_pos,
                    volume = excluded.volume,
                    autoplay = excluded.autoplay,
                    updated_at = CURRENT_TIMESTAMP;
            """, (current_track_id, queue_index, float(time_pos), float(volume), 1 if autoplay else 0))

    def get_player_state(self) -> Dict[str, Any]:
        """Retrieve last saved player state. Returns sensible defaults if not set."""
        with self._connection() as conn:
            cursor = conn.cursor()
            ps_cols = self._get_columns(cursor, "player_state")
            if "autoplay" not in ps_cols:
                cursor.execute("ALTER TABLE player_state ADD COLUMN autoplay INTEGER DEFAULT 1;")
            cursor.execute("""
                SELECT current_track_id, current_queue_index, time_pos, volume, autoplay, updated_at
                FROM player_state WHERE id = 1;
            """)
            row = cursor.fetchone()
            if row:
                auto_val = True
                try:
                    if "autoplay" in row.keys() and row["autoplay"] is not None:
                        auto_val = bool(row["autoplay"])
                except Exception:
                    pass
                return {
                    "current_track_id": row["current_track_id"],
                    "queue_index": int(row["current_queue_index"] or 0),
                    "time_pos": float(row["time_pos"] or 0.0),
                    "volume": float(row["volume"] if row["volume"] is not None else 80.0),
                    "autoplay": auto_val,
                    "updated_at": str(row["updated_at"]) if row["updated_at"] else None
                }
            return {
                "current_track_id": None,
                "queue_index": 0,
                "time_pos": 0.0,
                "volume": 80.0,
                "autoplay": True,
                "updated_at": None
            }

    # ---------------- HISTORY ----------------

    def add_history(
        self,
        track: Optional[Union[Dict[str, Any], str]] = None,
        title: Optional[Union[str, int]] = None,
        artist: Optional[str] = None,
        duration: Optional[str] = None,
        duration_sec: Optional[int] = None,
        url: Optional[str] = None,
        source: str = "youtube",
        thumbnail_url: Optional[str] = None,
        max_history: int = 1000,
        *,
        video_id: Optional[str] = None,
    ) -> None:
        """
        Record played track and prune history older than max_history items.
        Supports both Contract 1 dict format (add_history(track_dict, max_history=1000))
        and legacy positional parameters (add_history(video_id, title, ...)).
        """
        if isinstance(track, dict):
            vid = track.get("id") or track.get("video_id", "")
            t_title = track.get("title", "Unknown Title")
            t_artist = track.get("artist", "Unknown Artist")
            t_dur = track.get("duration", "--:--")
            t_sec = int(track.get("duration_sec") or 0)
            t_url = track.get("url") or f"https://www.youtube.com/watch?v={vid}"
            t_src = track.get("source", "youtube")
            t_thumb = track.get("thumbnail_url")
            m_hist = int(title) if isinstance(title, int) else max_history
        else:
            vid = video_id or (track if isinstance(track, str) else "")
            t_title = str(title) if title is not None else "Unknown Title"
            t_artist = artist or "Unknown Artist"
            t_dur = duration or "--:--"
            t_sec = int(duration_sec or 0)
            t_url = url or f"https://www.youtube.com/watch?v={vid}"
            t_src = source
            t_thumb = thumbnail_url
            m_hist = max_history

        if not vid:
            return

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO history (video_id, title, artist, duration, duration_sec, url, source, thumbnail_url, played_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (vid, t_title, t_artist, t_dur, t_sec, t_url, t_src, t_thumb, now_str))

            cursor.execute("SELECT COUNT(*) FROM history;")
            count = cursor.fetchone()[0]
            if count > m_hist:
                cursor.execute("""
                    DELETE FROM history
                    WHERE id NOT IN (
                        SELECT id FROM history ORDER BY played_at DESC, id DESC LIMIT ?
                    );
                """, (m_hist,))

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return playback history ordered by played_at DESC."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, video_id, title, artist, duration, duration_sec, url, source, thumbnail_url, played_at
                FROM history
                ORDER BY played_at DESC, id DESC
                LIMIT ?;
            """, (limit,))
            return [
                {
                    "id": r["video_id"],
                    "video_id": r["video_id"],
                    "history_id": r["id"],
                    "title": r["title"],
                    "artist": r["artist"],
                    "duration": r["duration"] or "--:--",
                    "duration_sec": int(r["duration_sec"] or 0),
                    "url": r["url"],
                    "source": r["source"] if "source" in r.keys() else "youtube",
                    "thumbnail_url": r["thumbnail_url"] if "thumbnail_url" in r.keys() else None,
                    "played_at": str(r["played_at"]) if r["played_at"] else None,
                }
                for r in cursor.fetchall()
            ]

    def clear_history(self) -> None:
        """Clear all playback history."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM history;")
