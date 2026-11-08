"""
Central button click dispatcher mixin for WaveApp.
"""
import asyncio

from textual import on
from textual.widgets import Button

from wave.youtube.radio import fetch_radio_mix

class ButtonsMixin:

    @on(Button.Pressed)
    def on_button_click(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        # View Header Actions (Playlist, Queue, History)
        if btn_id == "btn-act-clear-queue":
            self.action_clear_current_view()
        elif btn_id == "btn-act-clear-history":
            self.action_clear_current_view()
        elif btn_id == "btn-act-download-liked":
            liked = self.db.get_liked_songs()
            self._download_tracks_batch(liked, "Favorit")
        elif btn_id == "btn-act-download-pl":
            if self.current_view.startswith("PLAYLIST:"):
                pl_id = int(self.current_view.split(":")[1])
                pl = self.db.get_playlist(pl_id)
                pl_name = pl["name"] if pl else "Playlist"
                tracks = self.db.get_playlist_tracks(pl_id)
                self._download_tracks_batch(tracks, pl_name)
        elif btn_id == "btn-act-rename-pl":
            self.action_rename_current_playlist()
        elif btn_id == "btn-act-delete-pl":
            if self.current_view.startswith("PLAYLIST:"):
                pl_id = int(self.current_view.split(":")[1])
                self._confirm_delete_playlist(pl_id)
        # Row action buttons
        elif btn_id.startswith("btn-row-play-"):
            idx = int(btn_id.replace("btn-row-play-", ""))
            self._select_row(idx)
            self._play_track_at_index(idx)
        elif btn_id.startswith("btn-row-next-"):
            idx = int(btn_id.replace("btn-row-next-", ""))
            self._play_next_at_index(idx)
        elif btn_id.startswith("btn-row-q-"):
            idx = int(btn_id.replace("btn-row-q-", ""))
            self._add_to_queue_at_index(idx)
        elif btn_id.startswith("btn-row-pl-"):
            idx = int(btn_id.replace("btn-row-pl-", ""))
            self._open_playlist_menu_at_index(idx)
        elif btn_id.startswith("btn-row-fav-"):
            idx = int(btn_id.replace("btn-row-fav-", ""))
            self._toggle_like_at_index(idx)
        # Player bottom controls
        elif btn_id == "btn-play":
            self.action_toggle_pause()
        elif btn_id == "btn-prev":
            self.action_prev_track()
        elif btn_id == "btn-next":
            self.action_next_track()
        elif btn_id == "btn-seek-back":
            self.action_seek_backward()
        elif btn_id == "btn-seek-fwd":
            self.action_seek_forward()
        elif btn_id == "btn-vol-down":
            self.action_vol_down()
        elif btn_id == "btn-vol-up":
            self.action_vol_up()
        elif btn_id == "btn-player-fav":
            self.action_toggle_like_now_playing()
        elif btn_id == "btn-toggle-shuffle":
            self.action_toggle_shuffle()
        elif btn_id == "btn-toggle-repeat":
            self.action_toggle_repeat()
        elif btn_id == "btn-toggle-autoplay":
            self.action_toggle_autoplay()
        # Sidebar Navigation
        elif btn_id == "nav-btn-1":
            self.action_nav_search()
        elif btn_id == "nav-btn-2":
            self.action_nav_queue()
        elif btn_id == "nav-btn-3":
            self.action_nav_liked()
        elif btn_id == "nav-btn-4":
            self.action_nav_history()
        elif btn_id == "nav-btn-5":
            self.action_nav_radio()
        elif btn_id == "btn-act-refresh-radio":
            if self.player.current_track:
                self.notify("[RADIO] Memperbarui daftar rekomendasi...", timeout=1.5)
                async def _do_manual_refresh():
                    seed = self.player.current_track
                    recs = await fetch_radio_mix(seed.get("id", ""), artist=seed.get("artist", ""), title=seed.get("title", ""), limit=15)
                    if recs:
                        for r in recs:
                            r["is_radio"] = True
                        self.player.radio_queue = recs
                        self._update_sidebar_counts()
                        if self.current_view == "RADIO":
                            self._populate_table(self.player.radio_queue)
                            self._update_view_header()
                asyncio.create_task(_do_manual_refresh())
            else:
                self.notify("[RADIO] Putar lagu terlebih dahulu.", timeout=2.0)
        elif btn_id == "btn-act-play-all-radio":
            if self.player.radio_queue:
                first = self.player.radio_queue.pop(0)
                self._play_track(first)
                self._update_sidebar_counts()
                self._populate_table(self.player.radio_queue)
                self._update_view_header()
        elif btn_id == "btn-sidebar-new-pl":
            self.action_create_new_playlist()
        elif btn_id == "btn-sidebar-import-pl":
            self.action_import_playlist()
        elif btn_id.startswith("nav-pl-"):
            pl_id = int(btn_id.replace("nav-pl-", ""))
            self.action_nav_playlist(pl_id)
