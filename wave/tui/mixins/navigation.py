"""
Navigation and view switching mixin for WaveApp.
"""
from textual.containers import Horizontal, VerticalScroll
from textual.content import Content
from textual.widgets import Button, Input, Label

class NavigationMixin:

    def _set_active_nav(self, active_index: int):
        liked_count = len(self.db.get_liked_songs())
        queue_count = len(self.player.queue)
        radio_count = len(self.player.radio_queue)
        nav_names = {
            1: "SEARCH",
            2: f"QUEUE ({queue_count})",
            3: f"LIKED ({liked_count})",
            4: "HISTORY",
            5: f"RADIO ({radio_count})"
        }
        for i in range(1, 6):
            try:
                btn = self.query_one(f"#nav-btn-{i}", Button)
                name = nav_names[i]
                if i == active_index:
                    btn.label = f"> {i}. {name}"
                    btn.add_class("nav-active")
                else:
                    btn.label = f"  {i}. {name}"
                    btn.remove_class("nav-active")
            except Exception:
                pass
        try:
            for btn in self.query("#sidebar-playlists Button"):
                btn.remove_class("nav-active")
                lbl_text = str(btn.label)
                if lbl_text.startswith("> "):
                    btn.label = lbl_text.replace("> ", "  ")
        except Exception:
            pass

    def _set_active_nav_playlist(self, active_pl_id: int):
        for i in range(1, 6):
            try:
                btn = self.query_one(f"#nav-btn-{i}", Button)
                btn.remove_class("nav-active")
                lbl_text = str(btn.label)
                if lbl_text.startswith("> "):
                    btn.label = lbl_text.replace("> ", "  ")
            except Exception:
                pass
        try:
            for btn in self.query("#sidebar-playlists Button"):
                btn_id = btn.id or ""
                lbl_text = str(btn.label)
                if btn_id == f"nav-pl-{active_pl_id}":
                    btn.add_class("nav-active")
                    if lbl_text.startswith("  "):
                        btn.label = lbl_text.replace("  ", "> ")
                else:
                    btn.remove_class("nav-active")
                    if lbl_text.startswith("> "):
                        btn.label = lbl_text.replace("> ", "  ")
        except Exception:
            pass

    def _update_view_header(self):
        try:
            title_lbl = self.query_one("#view-title", Label)
            actions_box = self.query_one("#view-actions", Horizontal)
            self.run_worker(self._render_view_actions(title_lbl, actions_box))
        except Exception:
            pass

    async def _render_view_actions(self, title_lbl: Label, actions_box: Horizontal):
        try:
            await actions_box.remove_children()
            if self.current_view == "SEARCH":
                count = len(self.tracks_in_table)
                suffix = f" ({count} hasil)" if count else ""
                title_lbl.update(f"[CARI LAGU YOUTUBE]{suffix}")
            elif self.current_view == "QUEUE":
                q_len = len(self.player.queue)
                title_lbl.update(f"[DAFTAR ANTREAN - QUEUE] ({q_len} lagu)")
                if q_len > 0:
                    await actions_box.mount(Button(Content("[ Kosongkan ]"), id="btn-act-clear-queue", classes="view-action-btn modal-btn-danger"))
            elif self.current_view == "RADIO":
                r_len = len(self.player.radio_queue)
                cur = self.player.current_track
                seed_title = f"'{cur.get('title', '')[:25]}'" if cur else "Lagu Aktif"
                auto_str = "ON" if self.player.autoplay else "OFF"
                title_lbl.update(f"[RADIO MIX] Berdasarkan: {seed_title} ({r_len} lagu) [Radio: {auto_str}]")
                if r_len > 0:
                    await actions_box.mount(
                        Button(Content("[ Refresh Radio ]"), id="btn-act-refresh-radio", classes="view-action-btn"),
                        Button(Content("[ Putar Semua ]"), id="btn-act-play-all-radio", classes="view-action-btn")
                    )
            elif self.current_view == "LIKED":
                liked = self.db.get_liked_songs()
                title_lbl.update(f"[LAGU FAVORIT / LIKED SONGS] ({len(liked)} lagu)")
                if len(liked) > 0:
                    await actions_box.mount(
                        Button(Content("[ Download Semua ]"), id="btn-act-download-liked", classes="view-action-btn")
                    )
            elif self.current_view == "HISTORY":
                hist = self.db.get_history(50)
                title_lbl.update(f"[RIWAYAT PEMUTARAN - HISTORY] ({len(hist)} lagu)")
                if len(hist) > 0:
                    await actions_box.mount(Button(Content("[ Bersihkan ]"), id="btn-act-clear-history", classes="view-action-btn modal-btn-danger"))
            elif self.current_view.startswith("PLAYLIST:"):
                pl_id = int(self.current_view.split(":")[1])
                pl = self.db.get_playlist(pl_id)
                pl_name = pl["name"] if pl else "Playlist"
                tracks = self.db.get_playlist_tracks(pl_id)
                title_lbl.update(f"[PLAYLIST: {pl_name.upper()}] ({len(tracks)} lagu)")
                buttons = []
                if len(tracks) > 0:
                    buttons.append(Button(Content("[ Download Semua ]"), id="btn-act-download-pl", classes="view-action-btn"))
                buttons.append(Button(Content("[ Ubah Nama ]"), id="btn-act-rename-pl", classes="view-action-btn"))
                buttons.append(Button(Content("[ Hapus PL ]"), id="btn-act-delete-pl", classes="view-action-btn modal-btn-danger"))
                await actions_box.mount(*buttons)
        except Exception:
            pass

    def action_nav_search(self):
        self.current_view = "SEARCH"
        self._set_active_nav(1)
        self.query_one("#search-input", Input).display = True
        self.query_one("#search-status", Label).display = True
        self._populate_table(self.tracks_in_table)
        self._update_view_header()
        self.query_one("#search-input", Input).focus()

    def action_nav_queue(self):
        self.current_view = "QUEUE"
        self._set_active_nav(2)
        self.query_one("#search-input", Input).display = False
        self.query_one("#search-status", Label).display = False
        self._populate_table(self.player.queue)
        self._update_view_header()
        self.query_one("#tracks-scroll", VerticalScroll).focus()

    def action_nav_liked(self):
        self.current_view = "LIKED"
        self._set_active_nav(3)
        self.query_one("#search-input", Input).display = False
        self.query_one("#search-status", Label).display = False
        liked = self.db.get_liked_songs()
        self._populate_table(liked)
        self._update_view_header()
        self.query_one("#tracks-scroll", VerticalScroll).focus()

    def action_nav_history(self):
        self.current_view = "HISTORY"
        self._set_active_nav(4)
        self.query_one("#search-input", Input).display = False
        self.query_one("#search-status", Label).display = False
        history = self.db.get_history(50)
        self._populate_table(history)
        self._update_view_header()
        self.query_one("#tracks-scroll", VerticalScroll).focus()

    def action_nav_radio(self):
        self.current_view = "RADIO"
        self._set_active_nav(5)
        self.query_one("#search-input", Input).display = False
        self.query_one("#search-status", Label).display = False
        self._populate_table(self.player.radio_queue)
        self._update_view_header()
        self.query_one("#tracks-scroll", VerticalScroll).focus()

    def action_nav_playlist(self, pl_id: int):
        pl = self.db.get_playlist(pl_id)
        if not pl:
            return
        self.current_view = f"PLAYLIST:{pl_id}"
        self._set_active_nav_playlist(pl_id)
        self.query_one("#search-input", Input).display = False
        self.query_one("#search-status", Label).display = False
        tracks = self.db.get_playlist_tracks(pl_id)
        self._populate_table(tracks)
        self._update_view_header()
        self.query_one("#tracks-scroll", VerticalScroll).focus()
