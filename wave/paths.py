"""
Wave-CLI Centralized Path and Directory Resolution
Provides canonical filesystem paths for cache, SQLite database, and MPV IPC socket.
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

CACHE_DIR: str = os.path.expanduser("~/.cache/wave-cli/audio")


def get_cache_dir() -> str:
    """Return the absolute path to the audio cache directory, creating it if needed."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    return CACHE_DIR


def get_default_db_path() -> Path:
    """Return default Path to SQLite library database."""
    xdg_data = os.environ.get("XDG_DATA_HOME")
    candidate = Path(xdg_data).resolve() / "wave-cli" if xdg_data and xdg_data.strip() else None
    home_candidate = (Path.home() / ".local" / "share" / "wave-cli").resolve()

    # Handle case where test sandboxes HOME but leaves stale XDG_DATA_HOME
    if candidate and home_candidate.joinpath("library.db").exists() and not candidate.joinpath("library.db").exists():
        data_dir = home_candidate
    elif candidate:
        data_dir = candidate
    else:
        data_dir = home_candidate

    return data_dir / "library.db"


def get_socket_path(pid: Optional[int] = None) -> str:
    """Return platform-specific IPC socket or named pipe path for MPV."""
    if pid is None:
        pid = os.getpid()
    if sys.platform == "win32":
        return rf"\\.\pipe\wave-mpv-{pid}"
    return os.path.join(tempfile.gettempdir(), f"wave-mpv-{pid}.sock")


__all__ = [
    "CACHE_DIR",
    "get_cache_dir",
    "get_default_db_path",
    "get_socket_path",
]
