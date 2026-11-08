"""Persistent playback queue mixin."""

from typing import Any, Dict, List


class QueueMixin:
    """Queue persistence and reordering operations."""

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
