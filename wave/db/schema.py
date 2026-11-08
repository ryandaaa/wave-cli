"""Database schema and initialization mixin for wave-cli."""

import sqlite3
from typing import Set

from .migrations import MigrationMixin


class SchemaMixin(MigrationMixin):
    """Database table initialization and fresh schema creation."""

    def _init_db(self) -> None:
        """Initialize database tables and run version migrations."""
        with self._connection() as conn:
            self._run_migrations(conn)

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

        # Safe additive migrations for v2.x features (player_state autoplay, repeat_mode, shuffle columns)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {r["name"] if isinstance(r, sqlite3.Row) else r[0] for r in cursor.fetchall()}
        if "player_state" in tables:
            ps_cols = self._get_columns(cursor, "player_state")
            if "autoplay" not in ps_cols:
                cursor.execute("ALTER TABLE player_state ADD COLUMN autoplay INTEGER DEFAULT 1;")
            if "repeat_mode" not in ps_cols:
                cursor.execute("ALTER TABLE player_state ADD COLUMN repeat_mode TEXT DEFAULT 'OFF';")
            if "shuffle" not in ps_cols:
                cursor.execute("ALTER TABLE player_state ADD COLUMN shuffle INTEGER DEFAULT 0;")

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

        # Performance indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_liked_songs_added ON liked_songs(added_at DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_played_at ON history(played_at DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_video_id ON history(video_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_playlists_name ON playlists(name);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_playlist_tracks_pos ON playlist_tracks(playlist_id, position);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_playlist_tracks_vid ON playlist_tracks(playlist_id, video_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_queue_tracks_pos ON queue_tracks(position);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_queue_tracks_vid ON queue_tracks(video_id);")
