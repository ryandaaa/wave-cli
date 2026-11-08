"""
Playback status polling ticker, progress display, and shutdown mixin for WaveApp.
"""
from typing import Dict

from textual.content import Content
from textual.widgets import Button, Label

from wave.util.format import make_progress_bar, make_vol_bar

class TickerMixin:

    def _update_player_display_loading(self, track: Dict):
        title_lbl = self.query_one("#player-title", Label)
        prog_lbl = self.query_one("#player-progress", Label)
        stat_lbl = self.query_one("#player-status", Label)

        frame = self._load_frames[self._load_symbol_idx % len(self._load_frames)]
        title_str = f"[LOAD {frame}] {track.get('title', '')} - {track.get('artist', '')}"
        title_lbl.update(title_str)
        dur = track.get("duration", "--:--")
        prog_lbl.update(f"00:00 [==>-----------------------------] {dur}")
        stat_lbl.update(f"STATUS: Loading {frame}                  VOL: " + make_vol_bar(self.player.volume))

    def tick_playback(self):
        """Atomic update of ONLY the 3 player labels (no table or layout re-rendering)."""
        try:
            status = self.player.get_status()

            # Handle song completion -> auto-play next in queue or repeat
            if status.get("eof"):
                self.action_next_track(is_eof=True)
                return

            title_lbl = self.query_one("#player-title", Label)
            prog_lbl = self.query_one("#player-progress", Label)
            stat_lbl = self.query_one("#player-status", Label)

            # Sync bottom player buttons (Fav, Shuffle, Repeat)
            try:
                fav_btn = self.query_one("#btn-player-fav", Button)
                if self.player.current_track and self.player.current_track.get("id"):
                    is_fav = self.db.is_liked(self.player.current_track.get("id"))
                    fav_btn.label = Content("[Liked]") if is_fav else Content("[Fav]")
                    if is_fav:
                        fav_btn.add_class("is-liked")
                    else:
                        fav_btn.remove_class("is-liked")
                else:
                    fav_btn.label = Content("[Fav]")
                    fav_btn.remove_class("is-liked")
            except Exception:
                pass

            try:
                shuf_btn = self.query_one("#btn-toggle-shuffle", Button)
                shuf_btn.label = Content(f"[Shuf:{'ON' if self.player.shuffle else 'OFF'}]")
                if self.player.shuffle:
                    shuf_btn.add_class("is-active")
                else:
                    shuf_btn.remove_class("is-active")
            except Exception:
                pass

            try:
                rep_btn = self.query_one("#btn-toggle-repeat", Button)
                rep_btn.label = Content(f"[Rep:{self.player.repeat_mode}]")
                rep_btn.remove_class("is-active", "is-one")
                if self.player.repeat_mode == "ONE":
                    rep_btn.add_class("is-one")
                elif self.player.repeat_mode == "ALL":
                    rep_btn.add_class("is-active")
            except Exception:
                pass

            if not status["active"]:
                self.is_loading_track = False
                title_lbl.update("[IDLE] Belum ada lagu yang diputar")
                prog_lbl.update("00:00 [--------------------------------] 00:00")
                stat_lbl.update("STATUS: Ready                    VOL: " + make_vol_bar(status["volume"]))
                try:
                    self.query_one("#btn-play", Button).label = Content("[>]")
                except Exception:
                    pass
                return

            # Check if we transitioned from loading to playing
            if self.is_loading_track:
                if status["time_pos"] > 0:
                    self.is_loading_track = False
                else:
                    # Still loading, animate symbol
                    self._load_symbol_idx += 1
                    frame = self._load_frames[self._load_symbol_idx % len(self._load_frames)]
                    track = self.loading_track_info or {}
                    title_lbl.update(f"[LOAD {frame}] {track.get('title', '')} - {track.get('artist', '')}")
                    dur = track.get("duration", "--:--")
                    prog_lbl.update(f"00:00 [===>----------------------------] {dur}")
                    stat_lbl.update(f"STATUS: Loading {frame}                  VOL: " + make_vol_bar(status["volume"]))
                    try:
                        self.query_one("#btn-play", Button).label = Content(f"[{frame}]")
                    except Exception:
                        pass
                    return

            # Normal active playback
            play_state = "[PAUSE]" if status["paused"] else "[PLAY]"
            title_str = f"{play_state} {status['title']} - {status['artist']}"
            title_lbl.update(title_str)
            try:
                self.query_one("#btn-play", Button).label = Content("[>]") if status["paused"] else Content("[||]")
            except Exception:
                pass

            # Progress bar
            bar_str = make_progress_bar(status["percent"], width=32)
            prog_lbl.update(f"{status['time_str']} {bar_str} {status['dur_str']}")

            # Bottom status
            state_name = "Paused " if status["paused"] else "Playing"
            audio_source = "Offline/Opus" if status.get("is_offline") else "PipeWire/Opus"
            queue_len = len(self.player.queue)
            radio_len = len(self.player.radio_queue) if self.player.autoplay else 0
            q_info = f"QUEUE: {queue_len}"
            if radio_len > 0:
                q_info += f" (+{radio_len} Radio)"
            auto_text = "ON" if self.player.autoplay else "OFF"
            stat_lbl.update(
                f"STATUS: {state_name} ({audio_source})   {q_info}   RADIO: [{auto_text}]   VOL: " + make_vol_bar(status["volume"])
            )
        except Exception:
            pass

    def action_quit_app(self):
        self._save_current_player_state()
        if self._playback_timer:
            self._playback_timer.stop()
        self.player.close()
        self.exit()
