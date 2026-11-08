"""
Playback modes (shuffle, repeat, radio mix, autoplay) mixin for WaveApp.
"""
from typing import Dict

from textual.containers import VerticalScroll
from textual.content import Content
from textual.widgets import Button, Label

from wave.youtube.radio import fetch_radio_mix

class ModesMixin:

    async def _refresh_radio_recommendations(self, seed_track: Dict):
        v_id = seed_track.get("id", "")
        if not v_id:
            return
        artist = seed_track.get("artist", "")
        title = seed_track.get("title", "")
        try:
            recs = await fetch_radio_mix(v_id, artist=artist, title=title, limit=12)
            if recs:
                existing_ids = {self.player.current_track.get("id")} if self.player.current_track else set()
                existing_ids.update(t.get("id") for t in self.player.queue if t.get("id"))
                existing_ids.update(t.get("id") for t in self.player.context_queue if t.get("id"))
                existing_ids.update(self.player.session_played_ids)

                filtered = []
                for r in recs:
                    if r.get("id") and r.get("id") not in existing_ids:
                        r["is_radio"] = True
                        filtered.append(r)
                if filtered:
                    self.player.radio_queue = filtered
                    self._update_sidebar_counts()
                    if self.current_view == "RADIO":
                        scroll = self.query_one("#tracks-scroll", VerticalScroll)
                        # Only re-populate table if it was empty or showing empty message
                        has_tracks = bool(scroll.children and not any(isinstance(c, Label) and c.has_class("empty-state") for c in scroll.children))
                        if not has_tracks:
                            self._populate_table(self.player.radio_queue)
                        else:
                            self._update_row_playing_states(seed_track.get("id"))
                        self._update_view_header()
        except Exception:
            pass

    def action_toggle_shuffle(self):
        """Toggle shuffle mode (hotkey 's')."""
        is_shuf = self.player.toggle_shuffle()
        self._save_current_player_state()
        state_str = "ON (Acak)" if is_shuf else "OFF (Normal)"
        self.notify(f"[SHUFFLE] Mode Acak: {state_str}", timeout=1.5)

    def action_toggle_repeat(self):
        """Cycle repeat mode: OFF -> ALL -> ONE -> OFF (hotkey 't')."""
        mode = self.player.toggle_repeat()
        self._save_current_player_state()
        desc = {
            "OFF": "OFF (Tidak Ulang)",
            "ALL": "ALL (Ulang Playlist)",
            "ONE": "ONE (Ulang 1 Lagu)"
        }.get(mode, mode)
        self.notify(f"[REPEAT] Mode Putar Ulang: {desc}", timeout=1.5)

    def action_toggle_autoplay(self):
        is_on = self.player.toggle_autoplay()
        self._save_current_player_state()
        try:
            btn = self.query_one("#btn-toggle-autoplay", Button)
            btn.label = Content(f"[ Radio: {'ON' if is_on else 'OFF'} ]")
        except Exception:
            pass
        self.notify(f"[AUTOPLAY] Mode Radio: {'ON' if is_on else 'OFF'}", timeout=1.5)
        self._update_sidebar_counts()
        if self.current_view == "RADIO":
            self._update_view_header()
            self._populate_table(self.player.radio_queue)
