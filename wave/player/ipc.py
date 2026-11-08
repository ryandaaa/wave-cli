"""
Wave MPV IPC Mixin.
Handles MPV process lifecycle, UNIX domain socket IPC, and command dispatching.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from typing import Dict, List, Optional
from wave.paths import get_socket_path
from wave.youtube import find_yt_dlp


class IpcMixin:
    def __init__(
        self,
        sock_path: Optional[str] = None,
        volume: float = 80.0,
        autoplay: bool = True,
        repeat_mode: str = "OFF",
        shuffle: bool = False,
    ):
        if sock_path:
            self.sock_path = sock_path
        elif sys.platform == "win32":
            self.sock_path = rf"\\.\pipe\wave-mpv-{os.getpid()}"
        else:
            self.sock_path = os.path.join(tempfile.gettempdir(), f"wave-mpv-{os.getpid()}.sock")
        self.proc: Optional[subprocess.Popen] = None
        self.sock: Optional[socket.socket] = None
        self.pipe = None
        self.current_track: Optional[Dict] = None
        self.queue: List[Dict] = []           # Manual User Queue (Tier 1)
        self.context_queue: List[Dict] = []   # Playlist/Liked Queue (Tier 2)
        self.full_context_list: List[Dict] = [] # Original full list for Repeat/Shuffle
        self.radio_queue: List[Dict] = []     # Algorithmic Radio Queue (Tier 3)
        self.history_stack: List[Dict] = []
        self.session_played_ids: set = set()
        self.volume: float = float(volume)
        self.autoplay: bool = bool(autoplay)
        self.repeat_mode: str = str(repeat_mode) if repeat_mode in ("OFF", "ALL", "ONE") else "OFF"
        self.shuffle: bool = bool(shuffle)
        self.is_playing: bool = False
        self.is_paused: bool = False
        self.is_offline: bool = False
        self._last_time_pos: float = 0.0
        self._last_duration: float = 0.0

    def _ensure_running(self):
        """Ensure mpv process is alive, restart if crashed."""
        if not self.proc or self.proc.poll() is not None:
            self.start()

    def start(self):
        """Start mpv process in background with JSON IPC server."""
        if sys.platform != "win32" and os.path.exists(self.sock_path):
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
            "--ytdl-format=bestaudio/best",
            f"--volume={int(self.volume)}",
            "--msg-level=all=no",
        ]

        self.proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Wait until socket/pipe is created
        for _ in range(30):
            if sys.platform == "win32":
                if self._connect_socket():
                    return
            elif os.path.exists(self.sock_path):
                break
            time.sleep(0.1)

        self._connect_socket()

    def _connect_socket(self) -> bool:
        if sys.platform == "win32":
            try:
                self.pipe = open(self.sock_path, "r+b", buffering=0)
                return True
            except OSError:
                self.pipe = None
                return False
        else:
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
        if sys.platform == "win32":
            if not self.pipe:
                if not self._connect_socket():
                    return None
            for attempt in range(2):
                try:
                    payload = json.dumps({"command": cmd_list}).encode("utf-8") + b"\n"
                    self.pipe.write(payload)
                    while True:
                        line = self.pipe.readline()
                        if not line:
                            break
                        try:
                            res = json.loads(line.decode("utf-8", errors="ignore").strip())
                            if "error" in res:
                                return res
                        except json.JSONDecodeError:
                            continue
                except OSError:
                    self.pipe = None
                    if attempt == 0 and self._connect_socket():
                        continue
                    return None
            return None

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

    def close(self):
        """Clean shutdown."""
        try:
            if self.sock:
                self.send_command(["quit"])
                self.sock.close()
        except Exception:
            pass
        self.sock = None

        if hasattr(self, "pipe") and self.pipe:
            try:
                self.send_command(["quit"])
                self.pipe.close()
            except Exception:
                pass
            self.pipe = None

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
