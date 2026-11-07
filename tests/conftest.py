"""
Root pytest configuration and isolated fixtures for wave-cli tests.
Guarantees zero mutation to production environment and user files.
"""

import asyncio
import json
import os
import pathlib
import socket
import sys
import tempfile
import threading
import time
from typing import Any, Dict, Generator, List, Optional
import pytest

# Ensure wave-cli project root is on sys.path
PROJECT_ROOT = pathlib.Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """
    Sandboxes HOME, XDG_DATA_HOME, and XDG_RUNTIME_DIR to transient directories.
    Prevents any modification of ~/.local/share/wave-cli/library.db.
    """
    data_dir = tmp_path / ".local" / "share" / "wave-cli"
    data_dir.mkdir(parents=True, exist_ok=True)
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / ".local" / "share"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime_dir))

    return tmp_path


@pytest.fixture
def sample_tracks() -> List[Dict[str, Any]]:
    """Standardized realistic track fixtures for streaming tests."""
    return [
        {
            "id": "trk_001",
            "title": "Midnight City Wave",
            "artist": "Synth Artist A",
            "duration": "04:03",
            "duration_sec": 243,
            "url": "https://www.youtube.com/watch?v=trk_001"
        },
        {
            "id": "trk_002",
            "title": "Neon Horizon",
            "artist": "Retro Producer B",
            "duration": "03:15",
            "duration_sec": 195,
            "url": "https://www.youtube.com/watch?v=trk_002"
        },
        {
            "id": "trk_003",
            "title": "Cyber Chill Resonance",
            "artist": "Lo-Fi Master C",
            "duration": "02:45",
            "duration_sec": 165,
            "url": "https://www.youtube.com/watch?v=trk_003"
        },
        {
            "id": "trk_004",
            "title": "Sunset Drive Bassline",
            "artist": "Electronic Collective D",
            "duration": "05:12",
            "duration_sec": 312,
            "url": "https://www.youtube.com/watch?v=trk_004"
        },
        {
            "id": "trk_005",
            "title": "Digital Rain Echoes",
            "artist": "Ambient Soundscapes E",
            "duration": "01:58",
            "duration_sec": 118,
            "url": "https://www.youtube.com/watch?v=trk_005"
        }
    ]


class MockMpvServer:
    """
    Lightweight UNIX Domain Socket server simulating mpv JSON IPC protocol.
    Provides realistic responses without spawning external mpv process or requiring audio hardware.
    """
    def __init__(self, sock_path: str):
        self.sock_path = sock_path
        self.server_sock: Optional[socket.socket] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.received_commands: List[List[Any]] = []
        self.time_pos = 12.0
        self.duration = 240.0
        self.paused = False
        self.idle = False
        self.volume = 80.0
        self.loaded_file: Optional[str] = None

    def start(self):
        if os.path.exists(self.sock_path):
            try:
                os.unlink(self.sock_path)
            except OSError:
                pass

        self.server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_sock.bind(self.sock_path)
        self.server_sock.listen(5)
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def _run_loop(self):
        while self.running and self.server_sock:
            try:
                self.server_sock.settimeout(0.2)
                conn, _ = self.server_sock.accept()
            except (socket.timeout, OSError):
                continue

            conn_thread = threading.Thread(target=self._handle_client, args=(conn,), daemon=True)
            conn_thread.start()

    def _handle_client(self, conn: socket.socket):
        buffer = ""
        conn.settimeout(1.0)
        try:
            while self.running:
                data = conn.recv(4096)
                if not data:
                    break
                buffer += data.decode("utf-8")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        req = json.loads(line)
                        cmd = req.get("command", [])
                        self.received_commands.append(cmd)
                        resp = self._dispatch_cmd(cmd)
                        conn.sendall(json.dumps(resp).encode("utf-8") + b"\n")
                    except Exception as err:
                        conn.sendall(json.dumps({"error": str(err)}).encode("utf-8") + b"\n")
        except (socket.timeout, OSError):
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _dispatch_cmd(self, cmd: List[Any]) -> Dict[str, Any]:
        if not cmd:
            return {"error": "empty command"}
        name = cmd[0]

        if name == "loadfile":
            self.loaded_file = cmd[1] if len(cmd) > 1 else None
            self.idle = False
            return {"error": "success"}

        elif name == "stop":
            self.idle = True
            self.time_pos = 0.0
            return {"error": "success"}

        elif name == "cycle" and len(cmd) > 1 and cmd[1] == "pause":
            self.paused = not self.paused
            return {"error": "success"}

        elif name == "seek":
            delta = float(cmd[1]) if len(cmd) > 1 else 0.0
            mode = cmd[2] if len(cmd) > 2 else "relative"
            if mode == "relative":
                self.time_pos = max(0.0, min(self.duration, self.time_pos + delta))
            elif mode == "absolute":
                self.time_pos = max(0.0, min(self.duration, delta))
            return {"error": "success"}

        elif name == "set_property":
            prop = cmd[1] if len(cmd) > 1 else ""
            val = cmd[2] if len(cmd) > 2 else None
            if prop == "volume":
                self.volume = float(val)
            return {"error": "success"}

        elif name == "get_property":
            prop = cmd[1] if len(cmd) > 1 else ""
            if prop == "time-pos":
                return {"error": "success", "data": self.time_pos}
            elif prop == "duration":
                return {"error": "success", "data": self.duration}
            elif prop == "pause":
                return {"error": "success", "data": self.paused}
            elif prop == "idle-active":
                return {"error": "success", "data": self.idle}
            return {"error": "property unavailable", "data": None}

        elif name == "quit":
            self.running = False
            return {"error": "success"}

        return {"error": "success"}

    def stop(self):
        self.running = False
        if self.server_sock:
            try:
                self.server_sock.close()
            except OSError:
                pass
            self.server_sock = None
        if os.path.exists(self.sock_path):
            try:
                os.unlink(self.sock_path)
            except OSError:
                pass


@pytest.fixture
def mock_mpv_socket(tmp_path: pathlib.Path) -> Generator[MockMpvServer, None, None]:
    """Provides a running MockMpvServer over an isolated UNIX domain socket."""
    sock_path = str(tmp_path / "runtime" / f"mpv-test-{os.getpid()}-{int(time.time()*1000)}.sock")
    server = MockMpvServer(sock_path)
    server.start()
    time.sleep(0.05)  # Allow socket to bind
    yield server
    server.stop()
