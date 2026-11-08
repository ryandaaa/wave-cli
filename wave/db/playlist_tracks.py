"""Playlist tracks ordering and management mixin."""

import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Union


class PlaylistTracksMixin:
    """Track manipulation and reordering operations within playlists."""

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
