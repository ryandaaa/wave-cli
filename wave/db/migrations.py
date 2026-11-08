"""Database migration mixin for wave-cli."""

import sqlite3
from typing import Set


class MigrationMixin:
    """Schema migration methods for upgrading legacy database schemas."""

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
                repeat_mode TEXT DEFAULT 'OFF',
                shuffle INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        ps_cols = self._get_columns(cursor, "player_state")
        if "autoplay" not in ps_cols:
            cursor.execute("ALTER TABLE player_state ADD COLUMN autoplay INTEGER DEFAULT 1;")
        if "repeat_mode" not in ps_cols:
            cursor.execute("ALTER TABLE player_state ADD COLUMN repeat_mode TEXT DEFAULT 'OFF';")
        if "shuffle" not in ps_cols:
            cursor.execute("ALTER TABLE player_state ADD COLUMN shuffle INTEGER DEFAULT 0;")

        # 6. Create performance indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_liked_songs_added ON liked_songs(added_at DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_played_at ON history(played_at DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_video_id ON history(video_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_playlists_name ON playlists(name);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_playlist_tracks_pos ON playlist_tracks(playlist_id, position);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_playlist_tracks_vid ON playlist_tracks(playlist_id, video_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_queue_tracks_pos ON queue_tracks(position);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_queue_tracks_vid ON queue_tracks(video_id);")
