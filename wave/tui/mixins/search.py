"""
Search input, query execution, and progressive result loading mixin for WaveApp.
"""
import asyncio
from typing import Optional

from textual import work
from textual.containers import VerticalScroll
from textual.widgets import Input, Label

from wave.tui.widgets.track_row import TrackRow
from wave.youtube.playlist import fetch_youtube_playlist, is_playlist_url
from wave.youtube.search import search_youtube

class SearchMixin:

    async def on_input_submitted(self, event: Input.Submitted):
        query = event.value.strip()
        if not query:
            return

        if is_playlist_url(query):
            self.query_one("#search-input", Input).value = ""
            self.action_import_playlist(initial_url=query)
            return

        self._current_search_query = query
        self._search_spinner_idx = 0
        if self._search_spinner_timer:
            self._search_spinner_timer.stop()
        self._search_spinner_timer = self.set_interval(0.12, self._tick_search_spinner)
        self.perform_search(query)

    @work(exclusive=True, group="import_playlist", thread=False)
    async def import_youtube_playlist(self, url: str, custom_name: Optional[str] = None):
        status_lbl = self.query_one("#search-status", Label)
        status_lbl.update("[IMPORT] Mengambil daftar lagu dari YouTube Playlist...")
        self.notify("[IMPORT] Mengambil metadata playlist dari YouTube...", timeout=2.5)

        pl_title, tracks = await fetch_youtube_playlist(url, limit=150)

        if not tracks:
            status_lbl.update("[ERROR] Gagal mengambil playlist atau playlist kosong / privat.")
            self.notify("[ERROR] Gagal mengambil playlist YouTube. Pastikan link publik & valid.", timeout=3.0)
            return

        final_title = custom_name.strip() if custom_name and custom_name.strip() else pl_title
        pl_id = self.db.create_playlist(final_title)
        if not pl_id:
            self.notify("[ERROR] Gagal membuat playlist di database.", timeout=2.5)
            return

        added_count = 0
        for tr in tracks:
            if self.db.add_to_playlist(pl_id, tr):
                added_count += 1

        self._update_sidebar_counts()
        self._refresh_playlists_sidebar()
        self.action_nav_playlist(pl_id)
        self.notify(f"[PLAYLIST] Berhasil import '{final_title}' ({added_count} lagu)!", timeout=3.5)

    def _tick_search_spinner(self):
        frame = self._spinner_frames[self._search_spinner_idx % len(self._spinner_frames)]
        self._search_spinner_idx += 1
        status_lbl = self.query_one("#search-status", Label)
        status_lbl.update(f"Mencari: \"{self._current_search_query}\" {frame}")

    @work(exclusive=True, group="search", thread=False)
    async def perform_search(self, query: str):
        # 1. Fetch initial batch of 15 fast
        results = await search_youtube(query, limit=15)
        if self._search_spinner_timer:
            self._search_spinner_timer.stop()
            self._search_spinner_timer = None

        status_lbl = self.query_one("#search-status", Label)

        if not results:
            status_lbl.update(f"Tidak ada hasil untuk: \"{query}\". Coba kata kunci lain.")
            return

        self.tracks_in_table = list(results)
        self.selected_idx = 0
        status_lbl.update(f"Ditemukan {len(results)} lagu (memuat lebih banyak...). Gunakan Panah + Enter.")
        self._populate_table(results)
        self.query_one("#tracks-scroll", VerticalScroll).focus()

        # 2. Asynchronously fetch extended batch (up to 40) in background without flicker
        asyncio.create_task(self._fetch_extended_search(query, existing_ids={r.get("id") for r in results if r.get("id")}))

    async def _fetch_extended_search(self, query: str, existing_ids: set):
        try:
            more_results = await search_youtube(query, limit=40)
            if self.current_view != "SEARCH" or self._current_search_query != query:
                return
            new_tracks = [t for t in more_results if t.get("id") and t.get("id") not in existing_ids]
            if not new_tracks:
                try:
                    self.query_one("#search-status", Label).update(
                        f"Ditemukan {len(self.tracks_in_table)} lagu. Gunakan Panah Bawah/Atas + Enter."
                    )
                except Exception:
                    pass
                return

            start_idx = len(self.tracks_in_table)
            self.tracks_in_table.extend(new_tracks)

            cur_id = self.player.current_track.get("id") if self.player.current_track else None
            new_rows = []
            for i, track in enumerate(new_tracks):
                idx = start_idx + i
                t_id = track.get("id", "")
                is_playing = bool(cur_id and cur_id == t_id)
                is_liked = self.db.is_liked(t_id)
                new_rows.append(TrackRow(idx, track, is_selected=False, is_playing=is_playing, is_liked=is_liked))

            scroll = self.query_one("#tracks-scroll", VerticalScroll)
            await scroll.mount(*new_rows)

            try:
                self.query_one("#search-status", Label).update(
                    f"Ditemukan {len(self.tracks_in_table)} lagu. Gunakan Panah Bawah/Atas + Enter."
                )
                self._update_view_header()
            except Exception:
                pass
        except Exception:
            pass

    def action_focus_search(self):
        if self.current_view != "SEARCH":
            self.action_nav_search()
        inp = self.query_one("#search-input", Input)
        inp.focus()

    def action_escape_focus(self):
        """Escape unfocuses search input and returns to track list."""
        self.query_one("#tracks-scroll", VerticalScroll).focus()
