"""Liked songs (favorites) database mixin."""

import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Union


class LikedMixin:
    """CRUD operations for user liked tracks."""

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
