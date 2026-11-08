"""
Queue and playlist track reordering, deletion, and clear operations mixin for WaveApp.
"""
from textual.widgets import Input

from wave.tui.modals.confirm import ConfirmModal

class QueueOpsMixin:

    def action_move_track_up(self):
        """Move selected track up in Queue or Playlist."""
        inp = self.query_one("#search-input", Input)
        if inp.has_focus:
            return
        if self.current_view == "QUEUE":
            if 0 < self.selected_idx < len(self.player.queue):
                new_idx = self.selected_idx - 1
                self.player.move_queue(self.selected_idx, new_idx)
                self.db.save_queue(self.player.queue)
                self.selected_idx = new_idx
                self._populate_table(self._get_active_list())
                self.notify("[QUEUE] Posisi lagu dipindahkan ke atas.", timeout=1.5)
        elif self.current_view.startswith("PLAYLIST:"):
            pl_id = int(self.current_view.split(":")[1])
            tracks = self.db.get_playlist_tracks(pl_id)
            if 0 < self.selected_idx < len(tracks):
                new_idx = self.selected_idx - 1
                if self.db.move_playlist_track(pl_id, self.selected_idx, new_idx):
                    self.selected_idx = new_idx
                    self._populate_table(self.db.get_playlist_tracks(pl_id))
                    self.notify("[PLAYLIST] Posisi lagu dipindahkan ke atas.", timeout=1.5)

    def action_move_track_down(self):
        """Move selected track down in Queue or Playlist."""
        inp = self.query_one("#search-input", Input)
        if inp.has_focus:
            return
        if self.current_view == "QUEUE":
            if 0 <= self.selected_idx < len(self.player.queue) - 1:
                new_idx = self.selected_idx + 1
                self.player.move_queue(self.selected_idx, new_idx)
                self.db.save_queue(self.player.queue)
                self.selected_idx = new_idx
                self._populate_table(self._get_active_list())
                self.notify("[QUEUE] Posisi lagu dipindahkan ke bawah.", timeout=1.5)
        elif self.current_view.startswith("PLAYLIST:"):
            pl_id = int(self.current_view.split(":")[1])
            tracks = self.db.get_playlist_tracks(pl_id)
            if 0 <= self.selected_idx < len(tracks) - 1:
                new_idx = self.selected_idx + 1
                if self.db.move_playlist_track(pl_id, self.selected_idx, new_idx):
                    self.selected_idx = new_idx
                    self._populate_table(self.db.get_playlist_tracks(pl_id))
                    self.notify("[PLAYLIST] Posisi lagu dipindahkan ke bawah.", timeout=1.5)

    def _add_to_queue_at_index(self, idx: int):
        active_list = self._get_active_list()
        if 0 <= idx < len(active_list):
            track = active_list[idx]
            self.player.add_to_queue(track)
            self.db.save_queue(self.player.queue)
            self._update_sidebar_counts()
            title = track.get("title", "")[:35]
            self.notify(f"[QUEUE] Ditambahkan: {title}", timeout=2.0)
            if self.current_view == "QUEUE":
                self._populate_table(self._get_active_list())
                self._update_view_header()

    def action_add_queue(self):
        """Add highlighted track to queue with key 'a'."""
        self._add_to_queue_at_index(self.selected_idx)

    def action_delete_item(self):
        """Delete highlighted track from current playlist or queue with key 'd'."""
        if self.current_view.startswith("PLAYLIST:"):
            pl_id = int(self.current_view.split(":")[1])
            active_list = self._get_active_list()
            if 0 <= self.selected_idx < len(active_list):
                track = active_list[self.selected_idx]
                if self.db.remove_from_playlist(pl_id, self.selected_idx):
                    title = track.get("title", "")[:30]
                    self.notify(f"[PLAYLIST] Dihapus: {title}", timeout=2.0)
                    self._populate_table(self.db.get_playlist_tracks(pl_id))
                    self._update_sidebar_counts()
                    self._refresh_playlists_sidebar()
                    self._update_view_header()
            elif len(active_list) == 0:
                self._confirm_delete_playlist(pl_id)
        elif self.current_view == "LIKED":
            self.action_toggle_like()
        elif self.current_view == "QUEUE":
            if 0 <= self.selected_idx < len(self.player.queue):
                removed = self.player.remove_from_queue(self.selected_idx)
                if removed:
                    self.db.save_queue(self.player.queue)
                    title = removed.get("title", "")[:30]
                    self.notify(f"[QUEUE] Dihapus: {title}", timeout=2.0)
                    self._populate_table(self.player.queue)
                    self._update_sidebar_counts()
                    self._update_view_header()
        elif self.current_view == "RADIO":
            if 0 <= self.selected_idx < len(self.player.radio_queue):
                removed = self.player.radio_queue.pop(self.selected_idx)
                if removed:
                    title = removed.get("title", "")[:30]
                    self.notify(f"[RADIO] Dihapus dari rekomendasi: {title}", timeout=2.0)
                    self._populate_table(self.player.radio_queue)
                    self._update_sidebar_counts()
                    self._update_view_header()

    def action_clear_current_view(self):
        """Clear active queue or playback history with confirmation."""
        if self.current_view == "QUEUE":
            if not self.player.queue:
                self.notify("[QUEUE] Antrean sudah kosong.", timeout=2.0)
                return

            def on_confirm_clear_queue(yes: bool):
                if yes:
                    self.player.clear_queue()
                    self.db.clear_queue()
                    self._populate_table([])
                    self._update_sidebar_counts()
                    self._update_view_header()
                    self.notify("[QUEUE] Seluruh antrean berhasil dikosongkan.", timeout=2.0)

            self.push_screen(ConfirmModal("KOSONGKAN ANTREAN", "Yakin ingin menghapus semua lagu dari antrean?"), on_confirm_clear_queue)

        elif self.current_view == "HISTORY":
            hist = self.db.get_history(50)
            if not hist:
                self.notify("[HISTORY] Riwayat sudah kosong.", timeout=2.0)
                return

            def on_confirm_clear_history(yes: bool):
                if yes:
                    self.db.clear_history()
                    self._populate_table([])
                    self._update_view_header()
                    self.notify("[HISTORY] Seluruh riwayat pemutaran telah dibersihkan.", timeout=2.0)

            self.push_screen(ConfirmModal("BERSIHKAN RIWAYAT", "Yakin ingin menghapus seluruh riwayat pemutaran?"), on_confirm_clear_history)
