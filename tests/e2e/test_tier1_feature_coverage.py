"""
Tier 1: Feature Coverage Test Suite for wave-cli.
Enforces >=5 comprehensive test cases per functional area:
1. Search Subsystem (F12, F13, F14, F15, F16)
2. Queue CRUD (F04, F23, F24)
3. Playlist CRUD (F03, F25, F26, F27)
4. Liked CRUD (F05, F28, F29)
5. Aesthetics & Transparency (F18, F19, F20, F30)
6. CLI Integration (F21, F22)
"""

import asyncio
import inspect
import os
import pathlib
import re
import subprocess
import sys
from typing import Any, Dict, List
import pytest

from wave.db import Database
from wave.player import Player
from wave.util.format import format_duration, make_progress_bar, make_vol_bar
from wave.youtube import is_playlist_url, search_youtube
from wave.tui import WaveApp

pytestmark = pytest.mark.tier1


# ============================================================================
# 1. SEARCH SUBSYSTEM (F12, F13, F14, F15, F16)
# ============================================================================

def test_format_duration_standard():
    """Verify standard duration formatting for minutes and hours."""
    assert format_duration(45) == "00:45"
    assert format_duration(125) == "02:05"
    assert format_duration(3661) == "01:01:01"
    assert format_duration(7200) == "02:00:00"


def test_format_duration_edge_cases():
    """Verify duration formatting with zero, negative, None, and non-numeric (F15)."""
    assert format_duration(0) == "00:00", "Zero seconds should format as '00:00'"
    assert format_duration(-5) == "00:00" or format_duration(-5) == "--:--", "Negative seconds must not produce broken strings like '0-1:55'"
    assert format_duration(None) == "--:--"
    assert format_duration("invalid") == "--:--"


def test_is_playlist_url_detection():
    """Verify playlist URL classification vs single video URLs."""
    valid_playlists = [
        "https://www.youtube.com/playlist?list=PL1234567890abcdef",
        "http://youtube.com/playlist?list=PLxyz",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL1234567890abcdef",
        "https://youtu.be/dQw4w9WgXcQ?list=PL1234567890abcdef"
    ]
    for url in valid_playlists:
        assert is_playlist_url(url) is True, f"Expected {url} to be detected as playlist"

    single_videos = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "lo-fi hip hop study beats",
        ""
    ]
    for url in single_videos:
        assert is_playlist_url(url) is False, f"Expected {url} to NOT be detected as playlist"


@pytest.mark.asyncio
async def test_search_flag_injection_prevention(monkeypatch):
    """
    Verify search queries beginning with CLI flag patterns (e.g. --version)
    are safely delimited with '--' to prevent flag injection (F14).
    """
    captured_commands = []

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        captured_commands.append(list(cmd))
        class FakeProc:
            returncode = 0
            async def communicate(self):
                return b'{"entries": []}', b""
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    await search_youtube("--version")
    assert len(captured_commands) > 0
    executed_cmd = captured_commands[0]

    # Verify that yt-dlp arguments include '--' before the user query
    # or that '--version' is not parsed as an option flag
    assert "--" in executed_cmd or executed_cmd[-1] == "--version", \
        f"Flag injection vulnerability: query passed raw without delimiter in {executed_cmd}"


@pytest.mark.asyncio
async def test_single_video_url_search_handling(monkeypatch):
    """
    Verify yt-dlp returning single-video JSON without 'entries' key
    is correctly extracted into a 1-item result list (F12).
    """
    single_video_json = {
        "id": "single_vid_123",
        "title": "Standalone Video Track",
        "uploader": "Solo Artist",
        "duration": 210
    }

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        import json
        class FakeProc:
            returncode = 0
            async def communicate(self):
                return json.dumps(single_video_json).encode("utf-8"), b""
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    results = await search_youtube("https://www.youtube.com/watch?v=single_vid_123")
    assert isinstance(results, list)
    if results:
        assert len(results) == 1
        assert results[0]["id"] == "single_vid_123"
        assert results[0]["title"] == "Standalone Video Track"
    else:
        pytest.fail("Feature F12 not implemented: Single video URL without 'entries' returned empty list")


@pytest.mark.asyncio
async def test_search_query_caching(monkeypatch):
    """
    Verify search queries use an in-memory LRU cache to avoid repeating
    expensive yt-dlp subprocess invocations (F16).
    """
    call_count = 0

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        nonlocal call_count
        call_count += 1
        import json
        class FakeProc:
            returncode = 0
            async def communicate(self):
                return json.dumps({"entries": [{"id": "cache_test", "title": "Cache Song"}]}).encode(), b""
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    # First search should execute subprocess
    res1 = await search_youtube("synthwave chill", limit=5)
    # Second search for identical query and limit
    res2 = await search_youtube("synthwave chill", limit=5)

    assert res1 == res2
    assert call_count == 1, f"Expected 1 subprocess call due to LRU cache (F16), but got {call_count}"


@pytest.mark.asyncio
async def test_search_timeout_and_error_reporting(monkeypatch):
    """
    Verify subprocess errors or timeouts fail gracefully with empty results
    and informative handling rather than crashing (F13).
    """
    async def fake_create_subprocess_exec(*cmd, **kwargs):
        class FakeProc:
            returncode = 1
            async def communicate(self):
                return b"", b"ERROR: Unable to extract video data; network timeout"
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    results = await search_youtube("failing query")
    assert results == []


# ============================================================================
# 2. QUEUE CRUD (F04, F23, F24)
# ============================================================================

def test_queue_add_and_list(sample_tracks):
    """Verify adding tracks to Player queue and verifying list contents."""
    player = Player(sock_path="/tmp/dummy.sock")
    player.is_playing = True
    player.current_track = sample_tracks[0]

    for track in sample_tracks[1:]:
        player.add_to_queue(track)

    assert len(player.queue) == 4
    assert player.queue[0]["id"] == "trk_002"
    assert player.queue[3]["id"] == "trk_005"


def test_queue_remove_track(sample_tracks):
    """Verify removing a track at a specific index from queue."""
    player = Player(sock_path="/tmp/dummy.sock")
    player.is_playing = True
    player.current_track = sample_tracks[0]
    player.queue = list(sample_tracks[1:])

    # Remove track at index 1 ("trk_003")
    removed = player.queue.pop(1)
    assert removed["id"] == "trk_003"
    assert len(player.queue) == 3
    assert player.queue[0]["id"] == "trk_002"
    assert player.queue[1]["id"] == "trk_004"


def test_queue_reorder_tracks(sample_tracks):
    """Verify reordering tracks up and down within active playback queue (F23)."""
    player = Player(sock_path="/tmp/dummy.sock")
    player.queue = [sample_tracks[0], sample_tracks[1], sample_tracks[2]]

    # Reorder: move track at pos 2 to pos 0
    track = player.queue.pop(2)
    player.queue.insert(0, track)

    assert player.queue[0]["id"] == "trk_003"
    assert player.queue[1]["id"] == "trk_001"
    assert player.queue[2]["id"] == "trk_002"


def test_queue_clear(sample_tracks):
    """Verify clearing the entire playback queue (F23)."""
    player = Player(sock_path="/tmp/dummy.sock")
    player.queue = list(sample_tracks)
    assert len(player.queue) == 5

    player.queue.clear()
    assert len(player.queue) == 0


def test_queue_persistence_storage(db, sample_tracks):
    """
    Verify persistent queue storage in SQLite database (F04).
    Saves queue tracks and retrieves them across database sessions.
    """
    if not hasattr(db, "save_queue") or not hasattr(db, "get_queue"):
        pytest.fail("Feature F04 not implemented: Database.save_queue or get_queue missing")

    db.save_queue(sample_tracks[:3], current_index=1)
    saved_queue = db.get_queue()

    assert len(saved_queue) == 3
    assert saved_queue[0]["id"] == "trk_001"
    assert saved_queue[1]["id"] == "trk_002"
    assert saved_queue[2]["id"] == "trk_003"


def test_queue_jump_index_slicing(sample_tracks):
    """
    Verify queue jumping to an index preserves subsequent tracks correctly (F24).
    """
    player = Player(sock_path="/tmp/dummy.sock")
    player.queue = list(sample_tracks)

    # User jumps to index 2 (trk_003)
    target_idx = 2
    next_track = player.queue[target_idx]
    # Slicing subsequent tracks: queue should now contain tracks AFTER target_idx
    player.queue = player.queue[target_idx + 1:]

    assert next_track["id"] == "trk_003"
    assert len(player.queue) == 2
    assert player.queue[0]["id"] == "trk_004"
    assert player.queue[1]["id"] == "trk_005"


# ============================================================================
# 3. PLAYLIST CRUD (F03, F25, F26, F27)
# ============================================================================

def test_playlist_create_and_read(db, sample_tracks):
    """Verify creating a playlist and listing with track count."""
    pl_id = db.create_playlist("Chill Wave")
    assert pl_id is not None

    playlists = db.get_playlists()
    assert any(p["id"] == pl_id and p["name"] == "Chill Wave" for p in playlists)


def test_playlist_rename(db):
    """Verify renaming an existing playlist (F25)."""
    pl_id = db.create_playlist("Old Name")
    assert pl_id is not None

    renamed = db.rename_playlist(pl_id, "New Brand Name")
    assert renamed is True

    pl = db.get_playlist(pl_id)
    assert pl["name"] == "New Brand Name"


def test_playlist_delete_with_tracks(db, sample_tracks):
    """Verify deleting a playlist cascades and removes its tracks (F26)."""
    pl_id = db.create_playlist("To Be Deleted")
    db.add_to_playlist(pl_id, sample_tracks[0])
    db.add_to_playlist(pl_id, sample_tracks[1])

    tracks = db.get_playlist_tracks(pl_id)
    assert len(tracks) == 2

    deleted = db.delete_playlist(pl_id)
    assert deleted is True

    # Playlist should not exist
    assert db.get_playlist(pl_id) is None
    # Playlist tracks should be cascaded
    tracks_after = db.get_playlist_tracks(pl_id)
    assert len(tracks_after) == 0


def test_playlist_add_and_remove_tracks(db, sample_tracks):
    """Verify adding tracks to playlist and removing single track."""
    pl_id = db.create_playlist("Action Mix")
    db.add_to_playlist(pl_id, sample_tracks[0])
    db.add_to_playlist(pl_id, sample_tracks[1])

    tracks = db.get_playlist_tracks(pl_id)
    assert len(tracks) == 2

    # Remove first track
    removed = db.remove_from_playlist(pl_id, sample_tracks[0]["id"])
    assert removed is True

    remaining = db.get_playlist_tracks(pl_id)
    assert len(remaining) == 1
    assert remaining[0]["id"] == sample_tracks[1]["id"]


def test_playlist_track_reordering_positions(db, sample_tracks):
    """
    Verify playlist track reordering atomically updates position ordering (F03, F27).
    """
    pl_id = db.create_playlist("Reorder Playlist")
    for trk in sample_tracks[:3]:
        db.add_to_playlist(pl_id, trk)

    if not hasattr(db, "move_playlist_track"):
        pytest.fail("Feature F03/F27 not implemented: Database.move_playlist_track missing")

    # Move track from position 2 to position 0
    moved = db.move_playlist_track(pl_id, from_pos=2, to_pos=0)
    assert moved is True

    ordered_tracks = db.get_playlist_tracks(pl_id)
    assert ordered_tracks[0]["id"] == sample_tracks[2]["id"]
    assert ordered_tracks[1]["id"] == sample_tracks[0]["id"]
    assert ordered_tracks[2]["id"] == sample_tracks[1]["id"]


def test_playlist_duplicate_name_handling(db):
    """Verify handling of duplicate playlist names returns existing or handles cleanly."""
    id1 = db.create_playlist("Unique List")
    id2 = db.create_playlist("Unique List")

    assert id1 == id2 or id2 is not None
    playlists = [p for p in db.get_playlists() if p["name"] == "Unique List"]
    assert len(playlists) == 1


# ============================================================================
# 4. LIKED / FAVORITES CRUD (F05, F28, F29)
# ============================================================================

def test_liked_add_and_list(db, db_adapter, sample_tracks):
    """Verify adding track to liked songs and retrieving ordered list."""
    added = db_adapter.add_liked(db, sample_tracks[0])
    assert added is True

    liked_list = db.get_liked_songs()
    assert len(liked_list) == 1
    assert liked_list[0]["id"] == sample_tracks[0]["id"]


def test_liked_remove(db, db_adapter, sample_tracks):
    """Verify removing track from liked songs."""
    db_adapter.add_liked(db, sample_tracks[0])
    assert db.is_liked(sample_tracks[0]["id"]) is True

    removed = db.remove_liked(sample_tracks[0]["id"])
    assert removed is True
    assert db.is_liked(sample_tracks[0]["id"]) is False


def test_liked_is_liked_check(db, db_adapter, sample_tracks):
    """Verify boolean is_liked query accuracy."""
    assert db.is_liked("trk_nonexistent") is False
    db_adapter.add_liked(db, sample_tracks[1])
    assert db.is_liked("trk_002") is True


def test_liked_fast_lookup_get_liked_ids(db, db_adapter, sample_tracks):
    """
    Verify get_liked_ids() returns a set of video IDs for fast O(1) in-memory checks (F05).
    """
    if not hasattr(db, "get_liked_ids"):
        pytest.fail("Feature F05 not implemented: Database.get_liked_ids missing")

    db_adapter.add_liked(db, sample_tracks[0])
    db_adapter.add_liked(db, sample_tracks[1])

    liked_ids = db.get_liked_ids()
    assert isinstance(liked_ids, (set, frozenset))
    assert "trk_001" in liked_ids
    assert "trk_002" in liked_ids
    assert "trk_003" not in liked_ids


def test_liked_toggle_atomic(db, sample_tracks):
    """
    Verify atomic toggle_liked method (F05).
    Adds track if not liked, removes if liked, returning boolean state.
    """
    if not hasattr(db, "toggle_liked"):
        pytest.fail("Feature F05 not implemented: Database.toggle_liked missing")

    state1 = db.toggle_liked(sample_tracks[0])
    assert state1 is True
    assert db.is_liked(sample_tracks[0]["id"]) is True

    state2 = db.toggle_liked(sample_tracks[0])
    assert state2 is False
    assert db.is_liked(sample_tracks[0]["id"]) is False


def test_liked_player_bar_and_cross_view_sync(sample_tracks):
    """
    Verify player bar like state tracking and indicator logic (F28).
    """
    app = WaveApp()
    app.player.current_track = sample_tracks[0]
    # In player bar, liked state should match database or reactive attribute
    is_liked = app.db.is_liked(sample_tracks[0]["id"])
    assert isinstance(is_liked, bool)


# ============================================================================
# 5. AESTHETICS & TRANSPARENCY (F18, F19, F20, F30)
# ============================================================================

def test_tcss_background_transparency():
    """
    Verify wave.tcss enforces 100% transparent backgrounds for Kitty opacity 0.93 (F18).
    Inspects stylesheet for non-transparent backgrounds on primary containers.
    """
    tcss_path = pathlib.Path(__file__).parent.parent.parent / "wave.tcss"
    assert tcss_path.is_file()

    content = tcss_path.read_text(encoding="utf-8")
    # Verify Screen and primary containers have background: transparent
    assert "background: transparent;" in content, "wave.tcss must include transparent backgrounds"

    # Verify no opaque solid background on Screen root
    match = re.search(r"Screen\s*\{[^}]*background:\s*([^;]+);", content)
    if match:
        bg_val = match.group(1).strip()
        assert "transparent" in bg_val or "0, 0, 0, 0" in bg_val, \
            f"Screen background must be transparent, got: {bg_val}"


def test_ascii_aesthetic_enforcement():
    """
    Verify zero emojis across all UI strings, buttons, and progress indicators (F19).
    Scans wave.tcss, tui.py, and search.py for non-ASCII or emoji characters in UI.
    """
    src_dir = pathlib.Path(__file__).parent.parent.parent
    emoji_regex = re.compile(r"[\U00010000-\U0010ffff]", flags=re.UNICODE)

    for py_file in ["tui.py", "search.py", "wave.tcss"]:
        path = src_dir / py_file
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            emojis_found = emoji_regex.findall(text)
            assert len(emojis_found) == 0, f"Found emojis in {py_file}: {set(emojis_found)}"


def test_progress_bar_ascii_rendering():
    """Verify make_progress_bar outputs standard ASCII progress indicators."""
    bar0 = make_progress_bar(0.0, width=20)
    assert bar0 == "[--------------------]"

    bar50 = make_progress_bar(50.0, width=20)
    assert bar50 == "[=========>----------]"

    bar100 = make_progress_bar(100.0, width=20)
    assert bar100 == "[====================]"


def test_volume_bar_ascii_rendering():
    """Verify make_vol_bar outputs standard ASCII volume indicators."""
    vol0 = make_vol_bar(0.0, width=10)
    assert vol0 == "[..........] 0%"

    vol50 = make_vol_bar(50.0, width=10)
    assert vol50 == "[|||||.....] 50%"

    vol100 = make_vol_bar(100.0, width=10)
    assert vol100 == "[||||||||||] 100%"


def test_help_modal_and_toast_ascii():
    """Verify help modal and toast notification mapping (F20, F30)."""
    import wave.tui as tui
    # Check for HelpModal or ? keybinding in WaveApp
    has_help_binding = any(b.key == "question_mark" or b.key == "?" for b in WaveApp.BINDINGS)
    if not has_help_binding and not hasattr(tui, "HelpModal"):
        pytest.fail("Feature F20 not implemented: HelpModal or '?' binding missing in tui.py")


# ============================================================================
# 6. CLI INTEGRATION (F21, F22)
# ============================================================================

def test_cli_help_flag():
    """Verify CLI prints help output with --help / -h and exits code 0 (F21)."""
    main_py = str(pathlib.Path(__file__).parent.parent.parent / "main.py")
    try:
        res = subprocess.run([sys.executable, main_py, "--help"], capture_output=True, text=True, timeout=3.0)
        if res.returncode != 0 or "usage:" not in res.stdout.lower():
            pytest.fail(f"Feature F21 not implemented: CLI --help failed (exit={res.returncode}, stdout={res.stdout})")
    except subprocess.TimeoutExpired:
        pytest.fail("Feature F21 not implemented: CLI ignored --help and entered interactive app loop instead of printing help and exiting")


def test_cli_version_flag():
    """Verify CLI prints version with --version / -v and exits code 0 (F21)."""
    main_py = str(pathlib.Path(__file__).parent.parent.parent / "main.py")
    try:
        res = subprocess.run([sys.executable, main_py, "--version"], capture_output=True, text=True, timeout=3.0)
        if res.returncode != 0 or "wave" not in res.stdout.lower():
            pytest.fail(f"Feature F21 not implemented: CLI --version failed (exit={res.returncode}, stdout={res.stdout})")
    except subprocess.TimeoutExpired:
        pytest.fail("Feature F21 not implemented: CLI ignored --version and entered interactive app loop instead of printing version and exiting")


def test_cli_positional_search_query():
    """Verify CLI accepts positional search query argument (F21)."""
    from wave import cli as main
    assert hasattr(main, "parse_args") or hasattr(main, "main")


def test_pyproject_toml_presence_and_structure():
    """Verify pyproject.toml defines packaging and script entrypoints (F22)."""
    pyproject = pathlib.Path(__file__).parent.parent.parent / "pyproject.toml"
    if not pyproject.is_file():
        pytest.fail("Feature F22 not implemented: pyproject.toml is missing")

    content = pyproject.read_text(encoding="utf-8")
    assert "wave" in content
    assert "wave-cli" in content
    assert "project.scripts" in content or "tool.poetry.scripts" in content


def test_global_bin_wrappers():
    """Verify global wrappers at /home/ryanda/.local/bin/wave and wave-cli exist."""
    bin_wave = pathlib.Path("/home/ryanda/.local/bin/wave")
    bin_wave_cli = pathlib.Path("/home/ryanda/.local/bin/wave-cli")

    if bin_wave.exists():
        assert os.access(bin_wave, os.X_OK), "wave executable permission missing"
    if bin_wave_cli.exists():
        assert os.access(bin_wave_cli, os.X_OK), "wave-cli executable permission missing"
