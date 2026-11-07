"""
MPV Player Controller via UNIX Domain Socket JSON IPC
"""

import json
import os
import shutil
import socket
import subprocess
import time
from typing import Dict, List, Optional
from search import find_yt_dlp, format_duration


class Player:
    def __init__(self, sock_path: Optional[str] = None, volume: float = 80.0, autoplay: bool = True):
        self.sock_path = sock_path or f"/tmp/wave-mpv-{os.getpid()}.sock"
        self.proc: Optional[subprocess.Popen] = None
        self.sock: Optional[socket.socket] = None
        self.current_track: Optional[Dict] = None
        self.queue: List[Dict] = []           # Manual User Queue (Tier 1)
        self.context_queue: List[Dict] = []   # Playlist/Liked Queue (Tier 2)
        self.radio_queue: List[Dict] = []     # Algorithmic Radio Queue (Tier 3)
        self.history_stack: List[Dict] = []
        self.session_played_ids: set = set()
        self.volume: float = float(volume)
        self.autoplay: bool = bool(autoplay)
        self.is_playing: bool = False
        self.is_paused: bool = False
        self._last_time_pos: float = 0.0
        self._last_duration: float = 0.0

    def _ensure_running(self):
        """Ensure mpv process is alive, restart if crashed."""
        if not self.proc or self.proc.poll() is not None:
            self.start()

    def start(self):
        """Start mpv process in background with JSON IPC server."""
        if os.path.exists(self.sock_path):
            try:
                os.unlink(self.sock_path)
            except OSError:
                pass

        yt_dlp_path = find_yt_dlp()
        cmd = [
            "mpv",
            "--no-video",
            "--idle=yes",
            f"--input-ipc-server={self.sock_path}",
            f"--script-opts=ytdl_hook-ytdl_path={yt_dlp_path}",
            '--ytdl-format=bestaudio/best',
            f"--volume={int(self.volume)}",
            "--msg-level=all=no"
        ]

        self.proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        # Wait until socket is created
        for _ in range(30):
            if os.path.exists(self.sock_path):
                break
            time.sleep(0.1)

        self._connect_socket()

    def _connect_socket(self) -> bool:
        try:
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.settimeout(0.05)
            self.sock.connect(self.sock_path)
            return True
        except (socket.error, OSError):
            self.sock = None
            return False

    def send_command(self, cmd_list: list) -> Optional[dict]:
        """Send a command list to mpv JSON IPC and read response."""
        self._ensure_running()
        if not self.sock:
            if not self._connect_socket():
                return None

        for attempt in range(2):
            try:
                payload = json.dumps({"command": cmd_list}).encode("utf-8") + b"\n"
                self.sock.sendall(payload)

                # Read responses until we get the matching result (skip async events)
                while True:
                    data = b""
                    while not data.endswith(b"\n"):
                        chunk = self.sock.recv(1024)
                        if not chunk:
                            return None
                        data += chunk

                    line = data.decode("utf-8").strip()
                    if not line:
                        continue
                    try:
                        res = json.loads(line)
                        if "error" in res:
                            return res
                    except json.JSONDecodeError:
                        continue
            except (socket.error, socket.timeout, BrokenPipeError, ConnectionResetError):
                self.sock = None
                if attempt == 0 and self._connect_socket():
                    continue
                return None
        return None

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
        url = track.get("url") or f"https://www.youtube.com/watch?v={track.get('id', '')}"
        self.send_command(["loadfile", url, "replace"])

    def remove_from_queue(self, idx: int) -> Optional[Dict]:
        """Remove a track at index from the queue."""
        if 0 <= idx < len(self.queue):
            return self.queue.pop(idx)
        return None

    def clear_queue(self) -> None:
        """Clear all tracks from the queue."""
        self.queue.clear()

    def move_queue(self, from_idx: int, to_idx: int) -> bool:
        """Move a track in the queue from from_idx to to_idx."""
        if 0 <= from_idx < len(self.queue) and 0 <= to_idx < len(self.queue):
            track = self.queue.pop(from_idx)
            self.queue.insert(to_idx, track)
            return True
        return False

    def play_previous(self) -> Optional[Dict]:
        """Play previous track or restart current track if >3s in."""
        if self._last_time_pos > 3.0:
            self.seek(-self._last_time_pos)
            return self.current_track
        elif self.history_stack:
            prev_track = self.history_stack.pop()
            self.current_track = prev_track
            self.is_playing = True
            self._last_time_pos = 0.0
            self._last_duration = prev_track.get("duration_sec", 0.0)
            self.send_command(["loadfile", prev_track["url"], "replace"])
            return prev_track
        else:
            self.seek(0)
            return self.current_track

    def add_to_queue(self, track: Dict):
        """Add track to manual queue. If nothing is playing, play immediately."""
        if not self.is_playing or not self.current_track:
            self.play(track)
        else:
            self.queue.append(track)

    def play_next_enqueue(self, track: Dict):
        """Insert track as the next song to be played (at head of manual queue)."""
        if not self.is_playing or not self.current_track:
            self.play(track)
        else:
            self.queue.insert(0, track)

    def play_next(self) -> Optional[Dict]:
        """
        Play the next track according to tier priority:
        1. Manual queue (user explicit queue)
        2. Context queue (playlist sequence if active)
        3. Radio queue (algorithmic recommendations if autoplay enabled)
        """
        next_track = None
        if self.queue:
            next_track = self.queue.pop(0)
        elif self.context_queue:
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

    def toggle_autoplay(self) -> bool:
        """Toggle autoplay/radio state."""
        self.autoplay = not self.autoplay
        return self.autoplay

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
                "eof": False
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
            "eof": eof
        }

    def close(self):
        """Clean shutdown."""
        try:
            if self.sock:
                self.send_command(["quit"])
                self.sock.close()
        except Exception:
            pass

        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=1.0)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass

        if os.path.exists(self.sock_path):
            try:
                os.unlink(self.sock_path)
            except OSError:
                pass
