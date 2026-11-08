"""
Playlist CRUD dialogs, renaming, and import mixin for WaveApp.
"""
import asyncio
from typing import Dict, Optional

from wave.tui.modals.confirm import ConfirmModal
from wave.tui.modals.import_playlist import ImportPlaylistModal
from wave.tui.modals.new_playlist import NewPlaylistModal
from wave.tui.modals.playlist_select import PlaylistSelectModal
from wave.tui.modals.rename_playlist import RenamePlaylistModal

class PlaylistsMixin:

    def _open_playlist_menu_at_index(self, idx: int):
        active_list = self._get_active_list()
        if 0 <= idx < len(active_list):
            track = active_list[idx]
            self._show_playlist_modal_for_track(track)

    def action_open_playlist_menu(self):
        """Add highlighted track to a playlist with key 'm'."""
        self._open_playlist_menu_at_index(self.selected_idx)

    def _show_playlist_modal_for_track(self, track: Dict):
        playlists = self.db.get_playlists()

        def handle_select_pl(result: Optional[int]):
            if result is None:
                return
            if result == -1:
                self.action_create_new_playlist(initial_track=track)
            else:
                self.db.add_to_playlist(result, track)
                asyncio.create_task(self._auto_cache_track(track))
                pl = self.db.get_playlist(result)
                pl_name = pl["name"] if pl else "Playlist"
                self.notify(f"[PLAYLIST] Disimpan ke '{pl_name}'!", timeout=2.5)
                self._update_sidebar_counts()
                self._refresh_playlists_sidebar()
                if self.current_view == f"PLAYLIST:{result}":
                    self._populate_table(self.db.get_playlist_tracks(result))

        self.push_screen(PlaylistSelectModal(track, playlists), handle_select_pl)

    def action_create_new_playlist(self, initial_track: Optional[Dict] = None):
        """Prompt modal to create a new playlist."""
        def handle_new_pl(name: Optional[str]):
            if not name:
                return
            pl_id = self.db.create_playlist(name)
            if not pl_id:
                self.notify("[ERROR] Gagal membuat playlist.", timeout=2.0)
                return
            if initial_track:
                self.db.add_to_playlist(pl_id, initial_track)
                asyncio.create_task(self._auto_cache_track(initial_track))
                self.notify(f"[PLAYLIST] '{name}' dibuat & lagu ditambahkan!", timeout=2.5)
            else:
                self.notify(f"[PLAYLIST] Playlist '{name}' berhasil dibuat!", timeout=2.5)
            self._update_sidebar_counts()
            self._refresh_playlists_sidebar()
            self.action_nav_playlist(pl_id)

        self.push_screen(NewPlaylistModal(), handle_new_pl)

    def action_import_playlist(self, initial_url: str = ""):
        """Prompt modal to import a YouTube playlist with custom name."""
        def handle_import_data(result: Optional[Dict[str, str]]):
            if not result or not result.get("url"):
                return
            url = result["url"]
            name = result.get("name")
            self.import_youtube_playlist(url, custom_name=name)

        self.push_screen(ImportPlaylistModal(initial_url=initial_url), handle_import_data)

    def _confirm_delete_playlist(self, pl_id: int):
        pl = self.db.get_playlist(pl_id)
        pl_name = pl["name"] if pl else "Playlist"

        def on_confirm(yes: bool):
            if yes:
                self.db.delete_playlist(pl_id)
                self.notify(f"[PLAYLIST] '{pl_name}' berhasil dihapus.", timeout=2.5)
                self.action_nav_search()
                self._update_sidebar_counts()
                self._refresh_playlists_sidebar()

        self.push_screen(ConfirmModal("HAPUS PLAYLIST", f"Yakin ingin menghapus playlist '{pl_name}' secara permanen?"), on_confirm)

    def action_rename_current_playlist(self):
        """Prompt modal to rename the currently viewed playlist."""
        if not self.current_view.startswith("PLAYLIST:"):
            self.notify("[INFO] Buka sebuah playlist terlebih dahulu untuk mengubah namanya.", timeout=2.0)
            return

        pl_id = int(self.current_view.split(":")[1])
        pl = self.db.get_playlist(pl_id)
        if not pl:
            return

        def handle_rename(new_name: Optional[str]):
            if not new_name or new_name == pl["name"]:
                return
            if self.db.rename_playlist(pl_id, new_name):
                self.notify(f"[PLAYLIST] Berhasil diubah menjadi '{new_name}'!", timeout=2.5)
                self._update_sidebar_counts()
                self._refresh_playlists_sidebar()
                self._update_view_header()
            else:
                self.notify("[ERROR] Gagal mengubah nama playlist (mungkin nama sudah ada).", timeout=2.5)

        self.push_screen(RenamePlaylistModal(pl["name"]), handle_rename)
