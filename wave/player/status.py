"""
Wave MPV Player Status Polling Mixin.
Polls playback telemetry from MPV JSON IPC.
"""

from typing import Dict
from wave.util.format import format_duration


class StatusMixin:
    def get_status(self) -> Dict:
        """
        Poll playback status from mpv IPC.
        Returns:
            {
                "active": bool,
                "paused": bool,
                "time_pos": float,
                "duration": float,
                "time_str": str,
                "dur_str": str,
                "percent": float,
                "volume": float,
                "title": str,
                "artist": str,
                "eof": bool
            }
        """
        if not self.is_playing or not self.current_track:
            return {
                "active": False,
                "paused": False,
                "time_pos": 0.0,
                "duration": 0.0,
                "time_str": "00:00",
                "dur_str": "00:00",
                "percent": 0.0,
                "volume": self.volume,
                "title": "",
                "artist": "",
                "eof": False,
                "is_offline": False,
                "repeat_mode": self.repeat_mode,
                "shuffle": self.shuffle,
            }

        pos_res = self.send_command(["get_property", "time-pos"])
        dur_res = self.send_command(["get_property", "duration"])
        pause_res = self.send_command(["get_property", "pause"])
        idle_res = self.send_command(["get_property", "idle-active"])

        # Check if song ended
        is_idle = idle_res.get("data", False) if idle_res else False
        time_pos = pos_res.get("data", 0.0) if (pos_res and pos_res.get("data") is not None) else self._last_time_pos
        duration = dur_res.get("data", 0.0) if (dur_res and dur_res.get("data") is not None) else self._last_duration
        is_paused = pause_res.get("data", self.is_paused) if (pause_res and pause_res.get("data") is not None) else self.is_paused
        self.is_paused = bool(is_paused)

        if time_pos:
            self._last_time_pos = float(time_pos)
        if duration:
            self._last_duration = float(duration)

        percent = 0.0
        if self._last_duration > 0:
            percent = min(100.0, (self._last_time_pos / self._last_duration) * 100.0)

        # Detect track completion: was playing, now idle and was near end
        eof = False
        if is_idle and self._last_time_pos > 0 and (self._last_duration == 0 or self._last_time_pos >= self._last_duration - 2):
            eof = True

        return {
            "active": True,
            "paused": is_paused,
            "time_pos": self._last_time_pos,
            "duration": self._last_duration,
            "time_str": format_duration(self._last_time_pos),
            "dur_str": format_duration(self._last_duration),
            "percent": percent,
            "volume": self.volume,
            "title": self.current_track.get("title", ""),
            "artist": self.current_track.get("artist", ""),
            "eof": eof,
            "is_offline": self.is_offline,
            "repeat_mode": self.repeat_mode,
            "shuffle": self.shuffle,
        }


__all__ = ["StatusMixin"]
