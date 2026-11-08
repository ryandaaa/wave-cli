"""
Liked songs toggling for rows and now-playing track mixin for WaveApp.
"""
import asyncio

from textual.content import Content
from textual.widgets import Button, Input

from wave.tui.widgets.track_row import TrackRow

class LikesMixin:

    def _toggle_like_at_index(self, idx: int):
        active_list = self._get_active_list()
        if 0 <= idx < len(active_list):
            track = active_list[idx]
            vid_id = track.get("id", "")
            btn = None
            try:
                btn = self.query_one(f"#btn-row-fav-{idx}", Button)
            except Exception:
                pass
            if self.db.is_liked(vid_id):
                self.db.remove_liked(vid_id)
                self.notify("[LIKED] Dihapus dari Favorit", timeout=2.0)
                if btn:
                    btn.label = Content("[ Fav ]")
                    btn.remove_class("is-liked")
            else:
                self.db.add_liked(
                    vid_id,
                    track.get("title", ""),
                    track.get("artist", ""),
                    track.get("duration", ""),
                    track.get("duration_sec", 0),
                    track.get("url", "")
                )
                self.notify("[LIKED] Disimpan ke Favorit!", timeout=2.0)
                if btn:
                    btn.label = Content("[ Liked ]")
                    btn.add_class("is-liked")
                asyncio.create_task(self._auto_cache_track(track))
            self._update_sidebar_counts()
            if self.current_view == "LIKED":
                self._populate_table(self.db.get_liked_songs())
                self._update_view_header()

    def action_toggle_like(self):
        """Bookmark/like highlighted track with key 'f'."""
        self._toggle_like_at_index(self.selected_idx)

    def action_toggle_like_now_playing(self):
        """Toggle like/favorite on the currently playing track (hotkey 'F' or click [Fav])."""
        track = self.player.current_track
        if not track or not track.get("id"):
            self.notify("[FAV] Tidak ada lagu yang sedang diputar.", timeout=1.5)
            return

        vid_id = track.get("id", "")
        if self.db.is_liked(vid_id):
            self.db.remove_liked(vid_id)
            title = track.get("title", "")[:30]
            self.notify(f"[LIKED] Dihapus dari Favorit: {title}", timeout=2.0)
        else:
            self.db.add_liked(
                vid_id,
                track.get("title", ""),
                track.get("artist", ""),
                track.get("duration", ""),
                track.get("duration_sec", 0),
                track.get("url", "")
            )
            title = track.get("title", "")[:30]
            self.notify(f"[LIKED] Disimpan ke Favorit: {title}", timeout=2.0)
            asyncio.create_task(self._auto_cache_track(track))

        self._update_sidebar_counts()
        for row in self.query(TrackRow):
            if row.track.get("id") == vid_id:
                is_liked = self.db.is_liked(vid_id)
                row.is_liked = is_liked
                try:
                    b = row.query_one(f"#btn-row-fav-{row.idx}", Button)
                    b.label = Content("[ Liked ]") if is_liked else Content("[ Fav ]")
                    if is_liked:
                        b.add_class("is-liked")
                    else:
                        b.remove_class("is-liked")
                except Exception:
                    pass
        if self.current_view == "LIKED":
            self._populate_table(self.db.get_liked_songs())
            self._update_view_header()
