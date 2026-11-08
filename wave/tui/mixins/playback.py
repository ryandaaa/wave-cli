"""
Playback controls, volume, seeking, and track invocation mixin for WaveApp.
"""
import asyncio
import random
from typing import Dict

from textual.content import Content
from textual.widgets import Button, Input, Label

from wave.tui.widgets.track_row import TrackRow
from wave.util.format import make_vol_bar

class PlaybackMixin:

    def action_play_selected(self):
        inp = self.query_one("#search-input", Input)
        if inp.has_focus:
            return
        self._play_track_at_index(self.selected_idx)

    def _play_track_at_index(self, idx: int):
        active_list = self._get_active_list()
        if 0 <= idx < len(active_list):
            track = active_list[idx]
            subsequent = active_list[idx + 1:]
            if self.current_view.startswith("PLAYLIST:") or self.current_view == "LIKED":
                # Context queue follows playlist sequence, keeping full context for Repeat ALL/Shuffle
                self.player.full_context_list = list(active_list)
                if self.player.shuffle:
                    shuffled_rem = [t for i, t in enumerate(active_list) if i != idx]
                    random.shuffle(shuffled_rem)
                    self.player.context_queue = shuffled_rem
                else:
                    self.player.context_queue = list(subsequent)
                self._play_track(track)
            elif self.current_view == "SEARCH":
                # Spotify-style: search does NOT hijack or overwrite user queue!
                self.player.context_queue = []
                self._play_track(track)
            elif self.current_view == "QUEUE":
                if 0 <= idx < len(self.player.queue):
                    self.player.queue.pop(idx)
                    self.db.save_queue(self.player.queue)
                self._play_track(track)
                self._update_sidebar_counts()
                self._populate_table(self.player.queue)
                self._update_view_header()
            elif self.current_view == "RADIO":
                if 0 <= idx < len(self.player.radio_queue):
                    self.player.radio_queue = list(self.player.radio_queue[idx + 1:])
                self._play_track(track)
                self._update_sidebar_counts()
                self._update_row_playing_states(track.get("id"))
                self._update_view_header()

    def _play_next_at_index(self, idx: int):
        active_list = self._get_active_list()
        if 0 <= idx < len(active_list):
            track = active_list[idx]
            self.player.play_next_enqueue(track)
            self.db.save_queue(self.player.queue)
            self._update_sidebar_counts()
            title = track.get("title", "")[:35]
            self.notify(f"[NEXT] Disisipkan berikutnya: {title}", timeout=2.0)
            if self.current_view == "QUEUE":
                self._populate_table(self._get_active_list())
                self._update_view_header()

    def action_play_next_item(self):
        inp = self.query_one("#search-input", Input)
        if inp.has_focus:
            return
        self._play_next_at_index(self.selected_idx)

    def _play_track(self, track: Dict):
        self.is_loading_track = True
        self.loading_track_info = track
        self._load_symbol_idx = 0
        self.player.play(track)
        self.db.add_history(
            track.get("id", ""),
            track.get("title", ""),
            track.get("artist", ""),
            track.get("duration", ""),
            track.get("duration_sec", 0),
            track.get("url", "")
        )
        self._update_player_display_loading(track)
        if self.player.autoplay:
            asyncio.create_task(self._refresh_radio_recommendations(track))
        if self.current_view == "QUEUE":
            self._refresh_current_view()
        else:
            self._update_row_playing_states(track.get("id"))
            self._update_sidebar_counts()

    def action_toggle_pause(self):
        self.player.toggle_pause()
        if self.player.current_track:
            cur_id = self.player.current_track.get("id")
            for row in self.query(TrackRow):
                if row.track.get("id") == cur_id:
                    try:
                        btn = row.query_one(f"#btn-row-play-{row.idx}", Button)
                        btn.label = Content("[ > ]") if self.player.is_paused else Content("[ || ]")
                    except Exception:
                        pass

    def action_prev_track(self):
        prev_track = self.player.play_previous()
        if prev_track:
            self._play_track(prev_track)
        else:
            self.notify("[PLAYER] Tidak ada riwayat lagu sebelumnya.", timeout=2.0)

    def action_next_track(self, is_eof: bool = False):
        next_track = self.player.play_next(is_eof=is_eof)
        self.db.save_queue(self.player.queue)
        self._update_sidebar_counts()
        if next_track:
            self._play_track(next_track)
        else:
            self.notify("[QUEUE] Antrean lagu telah selesai.", timeout=2.0)
        if self.current_view in ("QUEUE", "RADIO"):
            self._populate_table(self._get_active_list())
            self._update_view_header()

    def action_vol_up(self):
        self.player.set_volume(+5.0)
        self._save_current_player_state()
        try:
            stat_lbl = self.query_one("#player-status", Label)
            state_name = "Paused " if self.player.is_paused else ("Playing" if self.player.is_playing else "Ready  ")
            stat_lbl.update(f"STATUS: {state_name}                    VOL: " + make_vol_bar(self.player.volume))
        except Exception:
            pass
        self.notify(f"[VOLUME] {int(self.player.volume)}%", timeout=1.0)

    def action_vol_down(self):
        self.player.set_volume(-5.0)
        self._save_current_player_state()
        try:
            stat_lbl = self.query_one("#player-status", Label)
            state_name = "Paused " if self.player.is_paused else ("Playing" if self.player.is_playing else "Ready  ")
            stat_lbl.update(f"STATUS: {state_name}                    VOL: " + make_vol_bar(self.player.volume))
        except Exception:
            pass
        self.notify(f"[VOLUME] {int(self.player.volume)}%", timeout=1.0)

    def _save_current_player_state(self):
        try:
            cur_id = self.player.current_track.get("id") if self.player.current_track else None
            self.db.save_player_state(
                current_track_id=cur_id,
                queue_index=0,
                time_pos=self.player._last_time_pos,
                volume=self.player.volume,
                autoplay=self.player.autoplay,
                repeat_mode=self.player.repeat_mode,
                shuffle=self.player.shuffle
            )
        except Exception:
            pass

    def action_seek_forward(self):
        self.player.seek(+5.0)

    def action_seek_backward(self):
        self.player.seek(-5.0)
