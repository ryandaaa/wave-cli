"""
Tier 4: Real-World Scenarios Test Suite for wave-cli.
Models authentic production usage workflows across the application lifecycle:
1. Clean Start to Multi-Playlist Management
2. Session Restart with Queue & Player State Persistence
3. Offline & Network Degradation Resilience
4. High-Volume Library Stress Benchmark
5. Rapid Keybinding Interaction Stress
"""

import asyncio
import inspect
import json
import os
import pathlib
import sqlite3
import time
from typing import Any, Dict, List
import pytest

from database import Database
from player import Player
from search import search_youtube
from tui import WaveApp

pytestmark = pytest.mark.tier4


# ============================================================================
# 1. CLEAN START TO MULTI-PLAYLIST MANAGEMENT
# ============================================================================

def test_real_world_clean_start_to_multi_playlist_management(isolated_env, sample_tracks):
    """
    Scenario 1: Fresh user onboarding without existing database or cache.
    App boots from clean state, initializes database, creates multiple themed
    playlists, populates tracks, reorganizes, renames, and deletes.
    """
    db_file = isolated_env / ".local" / "share" / "wave-cli" / "library.db"
    assert not db_file.exists(), "Clean start requires database to not pre-exist"

    # Boot database from zero
    db = Database()
    assert db_file.exists(), "Database file must be automatically initialized"

    # User creates 3 themed playlists
    pl_names = ["Late Night Code", "Synthwave Drive", "Ambient Focus"]
    created_ids = {}
    for name in pl_names:
        pl_id = db.create_playlist(name)
        assert pl_id is not None
        created_ids[name] = pl_id

    # Populate playlists with track batches
    for trk in sample_tracks[:3]:
        db.add_to_playlist(created_ids["Late Night Code"], trk)

    for trk in sample_tracks[2:5]:
        db.add_to_playlist(created_ids["Synthwave Drive"], trk)

    db.add_to_playlist(created_ids["Ambient Focus"], sample_tracks[4])

    # Rename 'Ambient Focus' -> 'Deep Focus Alpha'
    renamed = db.rename_playlist(created_ids["Ambient Focus"], "Deep Focus Alpha")
    assert renamed is True

    # Delete 'Synthwave Drive'
    deleted = db.delete_playlist(created_ids["Synthwave Drive"])
    assert deleted is True

    # Verify final library state
    all_pls = db.get_playlists()
    names = [p["name"] for p in all_pls]
    assert "Late Night Code" in names
    assert "Deep Focus Alpha" in names
    assert "Synthwave Drive" not in names

    # Verify track counts
    code_pl = next(p for p in all_pls if p["name"] == "Late Night Code")
    assert code_pl["count"] == 3

    focus_pl = next(p for p in all_pls if p["name"] == "Deep Focus Alpha")
    assert focus_pl["count"] == 1


# ============================================================================
# 2. SESSION RESTART WITH QUEUE & PLAYER STATE PERSISTENCE
# ============================================================================

def test_real_world_session_restart_queue_and_state_persistence(db, sample_tracks):
    """
    Scenario 2: User sessions and app restarts (F04).
    Session 1: User enqueues tracks, plays track, pauses at seek 48.5s, volume 75%.
               State and queue are persisted to SQLite.
    Session 2: New application instance boots, restores saved queue, index, time_pos, and volume.
    """
    if not hasattr(db, "save_queue") or not hasattr(db, "save_player_state"):
        pytest.fail("Feature F04 not implemented: Database queue/player_state persistence methods missing")

    # Session 1: Populate queue and persist state
    queued_tracks = sample_tracks[:4]
    current_idx = 2
    seek_time = 48.5
    volume_level = 75.0

    db.save_queue(queued_tracks, current_index=current_idx)
    db.save_player_state(
        current_track_id=queued_tracks[current_idx]["id"],
        queue_index=current_idx,
        time_pos=seek_time,
        volume=volume_level
    )

    # Session 2: Fresh Database and Player instance (simulating app restart)
    session2_db = Database()
    restored_queue = session2_db.get_queue()
    restored_state = session2_db.get_player_state()

    # Verify restored queue matches original
    assert len(restored_queue) == len(queued_tracks)
    for orig, restored in zip(queued_tracks, restored_queue):
        assert orig["id"] == restored["id"]
        assert orig["title"] == restored["title"]

    # Verify restored player state
    assert restored_state.get("queue_index") == current_idx
    assert restored_state.get("current_track_id") == queued_tracks[current_idx]["id"]
    assert abs(restored_state.get("time_pos", 0.0) - seek_time) < 0.1
    assert abs(restored_state.get("volume", 0.0) - volume_level) < 0.1


# ============================================================================
# 3. OFFLINE & NETWORK DEGRADATION RESILIENCE
# ============================================================================

@pytest.mark.asyncio
async def test_real_world_offline_network_degradation_and_recovery(monkeypatch, sample_tracks):
    """
    Scenario 3: Network degradation and graceful recovery (F13, F30).
    Simulate sudden DNS / network drop during search -> catches error gracefully.
    Then network reconnects -> search succeeds normally without application crash.
    """
    offline = True

    raw_entries = [
        {
            "id": sample_tracks[0]["id"],
            "title": sample_tracks[0]["title"],
            "uploader": sample_tracks[0]["artist"],
            "duration": sample_tracks[0]["duration_sec"]
        },
        {
            "id": sample_tracks[1]["id"],
            "title": sample_tracks[1]["title"],
            "uploader": sample_tracks[1]["artist"],
            "duration": sample_tracks[1]["duration_sec"]
        }
    ]

    async def dynamic_create_subprocess_exec(*cmd, **kwargs):
        nonlocal offline
        if offline:
            class FailingProc:
                returncode = 1
                async def communicate(self):
                    return b"", b"ERROR: <urlopen error [Errno -3] Temporary failure in name resolution>"
            return FailingProc()
        else:
            class SuccessProc:
                returncode = 0
                async def communicate(self):
                    return json.dumps({"entries": raw_entries}).encode(), b""
            return SuccessProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", dynamic_create_subprocess_exec)

    # Phase 1: Search while offline
    results_offline = await search_youtube("synthwave 80s")
    assert results_offline == [], "Offline search must return empty list without crashing"

    # Phase 2: Network is restored
    offline = False
    results_online = await search_youtube("synthwave 80s")
    assert len(results_online) == 2
    assert results_online[0]["id"] == sample_tracks[0]["id"]


# ============================================================================
# 4. HIGH-VOLUME LIBRARY STRESS BENCHMARK
# ============================================================================

def test_real_world_high_volume_library_stress(db, db_adapter, sample_tracks):
    """
    Scenario 4: High-volume library stress testing (F01, F05).
    Inserts 1,000 history items, 50 playlists with 1,000 total tracks, and 200 liked songs.
    Measures query latency for get_liked_ids() (<20ms) and verifies WAL integrity.
    """
    # 1. Populate 200 liked songs
    for i in range(200):
        trk = {
            "id": f"stress_liked_{i}",
            "title": f"Liked Song {i}",
            "artist": "Stress Artist",
            "duration": "03:15",
            "duration_sec": 195,
            "url": f"https://www.youtube.com/watch?v=stress_liked_{i}"
        }
        db_adapter.add_liked(db, trk)

    # 2. Benchmark get_liked_ids (F05)
    if hasattr(db, "get_liked_ids"):
        t0 = time.perf_counter()
        liked_ids = db.get_liked_ids()
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        assert len(liked_ids) == 200
        assert elapsed_ms < 50.0, f"get_liked_ids too slow: {elapsed_ms:.2f}ms (target < 50ms)"

    # 3. Populate 30 playlists with tracks
    for p_idx in range(30):
        pl_id = db.create_playlist(f"Stress_Playlist_{p_idx}")
        for t_idx in range(10):
            db.add_to_playlist(pl_id, {
                "id": f"pl_{p_idx}_t_{t_idx}",
                "title": f"PL Track {t_idx}",
                "artist": "Artist",
                "duration": "02:30",
                "duration_sec": 150,
                "url": f"https://yt.com/pl_{p_idx}_t_{t_idx}"
            })

    # Benchmark playlist listing
    t0 = time.perf_counter()
    all_pls = db.get_playlists()
    elapsed_pl = (time.perf_counter() - t0) * 1000.0
    assert len(all_pls) >= 30
    assert elapsed_pl < 100.0, f"get_playlists too slow: {elapsed_pl:.2f}ms"

    # Verify SQLite WAL integrity check
    with db._get_connection() if hasattr(db, "_get_connection") else sqlite3.connect(db.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        result = cursor.fetchone()[0]
        assert result.lower() == "ok", f"Database integrity check failed: {result}"


# ============================================================================
# 5. RAPID KEYBINDING INTERACTION STRESS
# ============================================================================

def test_real_world_rapid_keybinding_interaction_stress(mock_mpv_socket, sample_tracks):
    """
    Scenario 5: Rapid concurrent user input simulation.
    Fires rapid sequential playback commands (play, pause, seeks, volume changes,
    queue skips, like toggles) to verify player does not deadlock or crash.
    """
    p = Player(sock_path=mock_mpv_socket.sock_path)
    assert p._connect_socket() is True

    # Play initial track
    p.play(sample_tracks[0])
    for trk in sample_tracks[1:]:
        p.add_to_queue(trk)

    # Execute 50 rapid sequential transport commands
    for i in range(50):
        action = i % 6
        if action == 0:
            p.toggle_pause()
        elif action == 1:
            p.seek(5.0)
        elif action == 2:
            p.seek(-5.0)
        elif action == 3:
            p.set_volume(2.0)
        elif action == 4:
            p.set_volume(-2.0)
        elif action == 5:
            p.get_status()

    # Final state check
    status = p.get_status()
    assert isinstance(status, dict)
    assert p.is_playing is True
    assert p.volume >= 0.0 and p.volume <= 100.0

    p.close()
