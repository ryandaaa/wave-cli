"""
Tracklist rendering, row selection, and cursor navigation mixin for WaveApp.
"""
from typing import Dict, List, Optional

from textual import on
from textual.containers import VerticalScroll
from textual.content import Content
from textual.events import Click
from textual.widgets import Button, Input, Label

from wave.cache.audio_cache import is_track_cached
from wave.tui.widgets.track_row import TrackRow

class TracklistMixin:

    def _populate_table(self, tracks: List[Dict]):
        if self.current_view == "SEARCH":
            self.tracks_in_table = tracks
        self.run_worker(self._render_tracks(tracks), exclusive=True)

    async def _render_tracks(self, tracks: List[Dict]):
        scroll = self.query_one("#tracks-scroll", VerticalScroll)
        await scroll.remove_children()
        if not tracks:
            msg = "Belum ada lagu untuk ditampilkan."
            if self.current_view == "SEARCH":
                msg = "Ketik judul lagu / artis di atas dan tekan Enter untuk mencari."
            elif self.current_view == "QUEUE":
                msg = "Antrean kosong. Tekan 'e' [+Next] atau 'a' [+Q] pada lagu untuk menambah antrean."
            elif self.current_view == "RADIO":
                msg = "Belum ada rekomendasi radio. Putar sebuah lagu untuk mengaktifkan radio mix otomatis."
            elif self.current_view == "LIKED":
                msg = "Belum ada lagu favorit. Tekan 'f' atau klik [Fav] pada lagu untuk menyimpannya."
            elif self.current_view.startswith("PLAYLIST:"):
                msg = "Playlist masih kosong. Tekan 'm' atau klik [+PL] pada lagu untuk memasukkannya."
            await scroll.mount(Label(f"  {msg}", classes="empty-state", markup=False))
            self.selected_idx = 0
            return

        cur_id = self.player.current_track.get("id") if self.player.current_track else None
        self.selected_idx = min(self.selected_idx, max(0, len(tracks) - 1))

        rows = []
        for idx, track in enumerate(tracks):
            t_id = track.get("id", "")
            is_playing = (cur_id is not None and cur_id == t_id)
            is_liked = self.db.is_liked(t_id)
            is_selected = (idx == self.selected_idx)
            is_radio = bool(track.get("is_radio", False))
            rows.append(TrackRow(idx, track, is_selected=is_selected, is_playing=is_playing, is_liked=is_liked, is_radio=is_radio))

        await scroll.mount(*rows)

    def action_cursor_down(self):
        inp = self.query_one("#search-input", Input)
        if inp.has_focus:
            self.query_one("#tracks-scroll", VerticalScroll).focus()
            return
        active_list = self._get_active_list()
        if not active_list:
            return
        if self.selected_idx < len(active_list) - 1:
            self._select_row(self.selected_idx + 1)

    def action_cursor_up(self):
        inp = self.query_one("#search-input", Input)
        if inp.has_focus:
            return
        active_list = self._get_active_list()
        if not active_list:
            return
        if self.selected_idx > 0:
            self._select_row(self.selected_idx - 1)

    def _select_row(self, new_idx: int):
        old_idx = self.selected_idx
        self.selected_idx = new_idx
        try:
            self.query_one(f"#row-{old_idx}", TrackRow).remove_class("row-selected")
        except Exception:
            pass
        try:
            new_row = self.query_one(f"#row-{new_idx}", TrackRow)
            new_row.add_class("row-selected")
            new_row.scroll_visible(animate=False)
        except Exception:
            pass

    @on(Click, ".track-row")
    def on_row_click(self, event: Click):
        if isinstance(event.widget, Button):
            return
        row = event.widget if isinstance(event.widget, TrackRow) else event.widget.ancestor(TrackRow)
        if row:
            self._select_row(row.idx)
            self._play_track_at_index(row.idx)

    def _get_active_list(self) -> List[Dict]:
        if self.current_view == "SEARCH":
            return self.tracks_in_table
        elif self.current_view == "QUEUE":
            return self.player.queue
        elif self.current_view == "RADIO":
            return self.player.radio_queue
        elif self.current_view == "LIKED":
            return self.db.get_liked_songs()
        elif self.current_view == "HISTORY":
            return self.db.get_history(50)
        elif self.current_view.startswith("PLAYLIST:"):
            pl_id = int(self.current_view.split(":")[1])
            return self.db.get_playlist_tracks(pl_id)
        return []

    def _update_row_playing_states(self, playing_track_id: Optional[str]):
        """Update playing indicator on existing rows in-place without re-rendering the DOM."""
        try:
            for row in self.query(TrackRow):
                is_this = bool(playing_track_id and row.track.get("id") == playing_track_id)
                row.is_playing = is_this
                if is_this:
                    row.add_class("row-playing")
                else:
                    row.remove_class("row-playing")
                try:
                    btn = row.query_one(f"#btn-row-play-{row.idx}", Button)
                    btn.label = Content("[ || ]") if is_this else Content("[ > ]")
                except Exception:
                    pass
        except Exception:
            pass

    def _update_row_cache_states(self, track_id: Optional[str] = None):
        """Update offline [v] indicator on existing rows in-place without re-rendering DOM."""
        try:
            for row in self.query(TrackRow):
                row_id = row.track.get("id")
                if track_id is None or row_id == track_id:
                    cached = is_track_cached(row_id)
                    try:
                        lbl = row.query_one(f"#lbl-row-cache-{row.idx}", Label)
                        lbl.update("[v]" if cached else "   ")
                        if cached:
                            lbl.add_class("is-cached")
                        else:
                            lbl.remove_class("is-cached")
                    except Exception:
                        pass
        except Exception:
            pass

    def _refresh_current_view(self):
        active = self._get_active_list()
        self._populate_table(active)
        self._update_sidebar_counts()
