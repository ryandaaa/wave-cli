"""Playback history persistence mixin."""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union


class HistoryMixin:
    """Playback history logging and pruning operations."""

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
