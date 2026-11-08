"""
Unit tests for Audio Caching Engine & Offline Playback Support.
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from wave.cache import (
    CACHE_DIR,
    get_cache_dir,
    get_cached_audio_path,
    is_track_cached,
    is_downloading,
    get_cache_size_bytes,
    get_cache_size_str,
    clear_audio_cache,
)
from wave.player import Player


@pytest.fixture
def temp_cache_dir(tmp_path, monkeypatch):
    test_cache = tmp_path / "wave_test_cache"
    monkeypatch.setattr("wave.cache.audio_cache.CACHE_DIR", str(test_cache))
    return test_cache


def test_cache_directory_creation(temp_cache_dir):
    assert not os.path.exists(temp_cache_dir)
    res = get_cache_dir()
    assert os.path.exists(res)
    assert os.path.isdir(res)


def test_cached_audio_path_validation(temp_cache_dir):
    get_cache_dir()

    # 1. Non-existent track
    assert get_cached_audio_path("fake_id_123") is None
    assert is_track_cached("fake_id_123") is False

    # 2. Corrupt / incomplete file (< 50KB)
    small_file = temp_cache_dir / "small_id.opus"
    small_file.write_bytes(b"x" * 1024)  # 1 KB
    assert get_cached_audio_path("small_id") is None
    assert is_track_cached("small_id") is False

    # 3. Valid cached file (> 50KB)
    valid_file = temp_cache_dir / "valid_id.opus"
    valid_file.write_bytes(b"x" * 60_000)  # ~60 KB
    cached_path = get_cached_audio_path("valid_id")
    assert cached_path is not None
    assert cached_path == str(valid_file)
    assert is_track_cached("valid_id") is True


def test_cache_size_and_clear(temp_cache_dir):
    get_cache_dir()
    file1 = temp_cache_dir / "vid1.opus"
    file2 = temp_cache_dir / "vid2.opus"
    file1.write_bytes(b"a" * 1_000_000)
    file2.write_bytes(b"b" * 2_000_000)

    assert get_cache_size_bytes() == 3_000_000
    size_str = get_cache_size_str()
    assert "MB" in size_str

    cleared = clear_audio_cache()
    assert cleared == 2
    assert get_cache_size_bytes() == 0


def test_player_offline_routing(temp_cache_dir, monkeypatch):
    get_cache_dir()
    valid_file = temp_cache_dir / "offline_vid.opus"
    valid_file.write_bytes(b"x" * 60_000)

    player = Player(sock_path="/tmp/test_player_offline.sock")
    sent_commands = []
    player.send_command = lambda cmd: sent_commands.append(cmd) or {"data": True}

    # 1. Play cached track -> loads local file, sets is_offline=True
    cached_track = {"id": "offline_vid", "title": "Offline Song", "artist": "Artist"}
    player.play(cached_track)
    assert player.is_offline is True
    load_cmds = [cmd for cmd in sent_commands if cmd[0] == "loadfile"]
    assert len(load_cmds) == 1
    assert load_cmds[0] == ["loadfile", str(valid_file), "replace"]

    status = player.get_status()
    assert status["is_offline"] is True

    # 2. Play non-cached track -> loads YouTube stream URL, sets is_offline=False
    online_track = {"id": "online_vid", "title": "Online Song", "artist": "Artist", "url": "https://youtu.be/online_vid"}
    player.play(online_track)
    assert player.is_offline is False
    load_cmds = [cmd for cmd in sent_commands if cmd[0] == "loadfile"]
    assert len(load_cmds) == 2
    assert load_cmds[1] == ["loadfile", "https://youtu.be/online_vid", "replace"]

    status2 = player.get_status()
    assert status2["is_offline"] is False
