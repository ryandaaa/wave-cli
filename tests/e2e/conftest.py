"""
E2E specific fixtures and test helpers for wave-cli.
Supports contract-driven verification across database, player, search, and TUI.
"""

import inspect
import pathlib
from typing import Any, Dict, List, Optional, Set
import pytest

from wave.db import Database
from wave.player import Player


@pytest.fixture
def db(isolated_env: pathlib.Path) -> Database:
    """
    Returns an isolated Database instance.
    Supports both Contract 1 (Database(db_path=...)) and legacy Database()
    while guaranteeing storage remains in the transient test directory.
    """
    sig = inspect.signature(Database.__init__)
    if "db_path" in sig.parameters:
        db_file = isolated_env / ".local" / "share" / "wave-cli" / "library.db"
        return Database(db_path=str(db_file))
    return Database()


class DatabaseAdapter:
    """
    Contract-aware helper that bridges Contract 1 requirements with implementation.
    If the underlying Database implementation does not yet support Contract 1 methods
    (e.g., toggle_liked, get_liked_ids, persistent queue), this adapter provides
    clear diagnostics or fallback checks.
    """
    @staticmethod
    def add_liked(db: Database, track: Dict[str, Any]) -> bool:
        sig = inspect.signature(db.add_liked)
        if len(sig.parameters) <= 2:
            return db.add_liked(track)
        else:
            return db.add_liked(
                video_id=track["id"],
                title=track.get("title", ""),
                artist=track.get("artist", ""),
                duration=track.get("duration", "--:--"),
                duration_sec=track.get("duration_sec", 0),
                url=track.get("url", "")
            )

    @staticmethod
    def add_history(db: Database, track: Dict[str, Any]) -> None:
        sig = inspect.signature(db.add_history)
        if len(sig.parameters) <= 3:
            db.add_history(track)
        else:
            db.add_history(
                video_id=track["id"],
                title=track.get("title", ""),
                artist=track.get("artist", ""),
                duration=track.get("duration", "--:--"),
                duration_sec=track.get("duration_sec", 0),
                url=track.get("url", "")
            )


@pytest.fixture
def db_adapter() -> DatabaseAdapter:
    return DatabaseAdapter()


@pytest.fixture
def connected_player(mock_mpv_socket) -> Player:
    """
    Returns a Player instance connected to the running MockMpvServer UNIX socket.
    Avoids spawning actual mpv binaries while exercising genuine socket IPC.
    """
    p = Player(sock_path=mock_mpv_socket.sock_path)
    # Connect directly to mock socket
    assert p._connect_socket() is True
    yield p
    p.close()
