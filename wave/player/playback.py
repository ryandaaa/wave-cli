"""
Wave MPV Playback Control Mixin.
Handles track playback, skipping, pausing, seeking, volume, and playback state.
"""

import random
from typing import Dict, Optional
from wave.cache import get_cached_audio_path


class PlaybackMixin:
    def play(self, track: Dict):
        """Play a new track immediately."""
        if self.current_track and self.current_track.get("id") != track.get("id"):
            self.history_stack.append(self.current_track)
        self.current_track = track
        track_id = track.get("id")
        if track_id:
            self.session_played_ids.add(track_id)
        self.is_playing = True
        self.is_paused = False
        self._last_time_pos = 0.0
        self._last_duration = track.get("duration_sec", 0.0)

        # Check audio cache for instant 0.01s local playback
        cached_path = get_cached_audio_path(track_id) if track_id else None
        if cached_path:
            target = cached_path
            self.is_offline = True
        else:
            target = track.get("url") or f"https://www.youtube.com/watch?v={track_id or ''}"
            self.is_offline = False

        self.send_command(["loadfile", target, "replace"])

    def play_previous(self) -> Optional[Dict]:
        """Play previous track or restart current track if >3s in."""
        if self._last_time_pos > 3.0:
            self.seek(-self._last_time_pos)
            return self.current_track
        elif self.history_stack:
            prev_track = self.history_stack.pop()
            self.current_track = prev_track
            self.is_playing = True
            self.is_paused = False
            self._last_time_pos = 0.0
            self._last_duration = prev_track.get("duration_sec", 0.0)
            cached_path = get_cached_audio_path(prev_track.get("id")) if prev_track.get("id") else None
            if cached_path:
                target = cached_path
                self.is_offline = True
            else:
                target = prev_track.get("url") or f"https://www.youtube.com/watch?v={prev_track.get('id', '')}"
                self.is_offline = False
            self.send_command(["loadfile", target, "replace"])
            return prev_track
        else:
            self.seek(0)
            return self.current_track

    def play_next(self, is_eof: bool = False) -> Optional[Dict]:
        """
        Play the next track according to tier priority and repeat/shuffle settings:
        0. Repeat One (only triggers on natural track end / is_eof)
        1. Manual queue (user explicit queue)
        2. Context queue (playlist sequence if active)
        2b. Repeat ALL (refills context queue if empty)
        3. Radio queue (algorithmic recommendations if autoplay enabled)
        """
        if is_eof and self.repeat_mode == "ONE" and self.current_track:
            self.play(self.current_track)
            return self.current_track

        next_track = None
        if self.queue:
            next_track = self.queue.pop(0)
        elif self.context_queue:
            next_track = self.context_queue.pop(0)
        elif self.repeat_mode == "ALL" and self.full_context_list:
            refilled = list(self.full_context_list)
            if self.shuffle:
                random.shuffle(refilled)
            self.context_queue = refilled
            if self.context_queue:
                next_track = self.context_queue.pop(0)
        elif self.autoplay and self.radio_queue:
            while self.radio_queue:
                cand = self.radio_queue.pop(0)
                if cand.get("id") not in self.session_played_ids:
                    next_track = cand
                    break

        if next_track:
            self.play(next_track)
            return next_track
        else:
            self.stop()
            return None

    def toggle_pause(self):
        """Toggle pause state."""
        self.is_paused = not self.is_paused
        self.send_command(["cycle", "pause"])

    def seek(self, seconds: float):
        """Seek relative seconds."""
        self.send_command(["seek", seconds, "relative"])

    def set_volume(self, delta: float):
        """Change volume by delta (e.g. +5 or -5)."""
        new_vol = max(0.0, min(100.0, self.volume + delta))
        self.volume = new_vol
        self.send_command(["set_property", "volume", self.volume])

    def stop(self):
        """Stop playback and return to idle."""
        self.send_command(["stop"])
        self.is_playing = False
        self.is_paused = False
        self.current_track = None
        self._last_time_pos = 0.0
