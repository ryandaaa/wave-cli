"""Playlist metadata management mixin."""

import sqlite3
from typing import Any, Dict, List, Optional

from .playlist_tracks import PlaylistTracksMixin


class PlaylistsMixin(PlaylistTracksMixin):
    """Playlist creation, deletion, renaming, and queries."""

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
