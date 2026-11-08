"""
Tier 2: Boundary & Corner Cases Test Suite for wave-cli.
Covers adversarial inputs, edge conditions, resource constraints, and resilience:
- Empty playlist operations
- SQL injection & special character resistance
- Extreme string lengths
- Invalid URLs & malformed inputs
- Missing / dead socket resilience
- Multi-threaded concurrent database access (WAL mode)
- Legacy database migration (v1 -> v2)
- File descriptor leak prevention
- IPC framing & coalesced packet handling
- Duration and seek boundary clamping
"""

import concurrent.futures
import inspect
import json
import os
import pathlib
import socket
import sqlite3
import threading
import time
from typing import Any, Dict, List
import pytest

from wave.db import Database
from wave.player import Player
from wave.util.format import format_duration
from wave.youtube import is_playlist_url

pytestmark = pytest.mark.tier2


# ============================================================================
# 1. EMPTY ENTITY & BOUNDARY OPERATIONS
# ============================================================================

def test_empty_playlist_operations(db):
    """Verify operations on empty playlists and nonexistent IDs behave safely."""
    pl_id = db.create_playlist("Empty List")
    assert pl_id is not None

    # Getting tracks from empty playlist returns empty list
    tracks = db.get_playlist_tracks(pl_id)
    assert tracks == []

    # Removing from empty playlist returns False
    removed = db.remove_from_playlist(pl_id, "nonexistent_vid")
    assert removed is False

    # Renaming empty playlist works
    renamed = db.rename_playlist(pl_id, "Still Empty")
    assert renamed is True

    # Deleting empty playlist works
    deleted = db.delete_playlist(pl_id)
    assert deleted is True

    # Querying non-existent playlist ID returns None
    assert db.get_playlist(999999) is None
    assert db.get_playlist_tracks(999999) == []


def test_empty_queue_operations():
    """Verify queue operations when queue is completely empty."""
    p = Player(sock_path="/tmp/nonexistent.sock")
    assert len(p.queue) == 0

    # play_next on empty queue returns None
    next_track = p.play_next()
    assert next_track is None

    # play_previous on empty queue without history returns None or current
    prev_track = p.play_previous()
    assert prev_track is None or prev_track == p.current_track


# ============================================================================
# 2. SQL INJECTION & SPECIAL CHARACTERS
# ============================================================================

def test_sql_injection_and_special_characters(db, db_adapter):
    """
    Verify parameterized queries prevent SQL injection across playlist names,
    track titles, artists, and URLs.
    """
    adversarial_names = [
        "Rock'; DROP TABLE playlists; --",
        'Quotes "Double" and \'Single\' and \\Backslashes\\',
        "Unicode \u0000 Null and \n Newlines \t Tabs",
        "Emoji & Foreign: 🎵 日本語 Басс Español"
    ]

    created_ids = []
    for name in adversarial_names:
        pl_id = db.create_playlist(name)
        assert pl_id is not None
        created_ids.append(pl_id)

    # Verify playlists table is completely intact
    all_pls = db.get_playlists()
    assert len(all_pls) >= len(adversarial_names)

    # Add track with SQL injection payload in title and artist
    evil_track = {
        "id": "evil_trk_1",
        "title": "'); DELETE FROM liked_songs; SELECT ('1",
        "artist": "Dr. Hacker --",
        "duration": "03:33",
        "duration_sec": 213,
        "url": "https://www.youtube.com/watch?v=evil_trk_1"
    }

    db_adapter.add_liked(db, evil_track)
    assert db.is_liked("evil_trk_1") is True

    liked_songs = db.get_liked_songs()
    assert any(s["id"] == "evil_trk_1" for s in liked_songs)


def test_extreme_string_lengths(db, db_adapter):
    """
    Verify system handles extreme string lengths (10,000+ chars)
    without crashing or database truncation.
    """
    giant_name = "LongPlaylist_" + ("A" * 10000)
    pl_id = db.create_playlist(giant_name)
    assert pl_id is not None

    retrieved = db.get_playlist(pl_id)
    assert retrieved is not None
    assert len(retrieved["name"]) >= 10000

    giant_track = {
        "id": "giant_trk",
        "title": "Title_" + ("T" * 5000),
        "artist": "Artist_" + ("A" * 5000),
        "duration": "99:99",
        "duration_sec": 9999,
        "url": "https://www.youtube.com/watch?v=giant_trk"
    }
    db.add_to_playlist(pl_id, giant_track)
    tracks = db.get_playlist_tracks(pl_id)
    assert len(tracks) == 1
    assert len(tracks[0]["title"]) >= 5000


# ============================================================================
# 3. INVALID URLS & SEARCH INPUTS
# ============================================================================

def test_invalid_and_malformed_urls():
    """Verify URL detection correctly rejects malformed or non-YouTube URLs."""
    invalid_urls = [
        "ftp://youtube.com/playlist?list=123",
        "http:///missing-domain",
        "https://notyoutube.com/playlist?list=123",
        "just a search term with playlist in it",
        "https://youtube.com/watch",
        ""
    ]
    for url in invalid_urls:
        assert is_playlist_url(url) is False


def test_duration_boundary_values():
    """Verify duration formatter behaves predictably with extreme boundary numbers."""
    assert format_duration(0) == "00:00"
    assert format_duration(59) == "00:59"
    assert format_duration(60) == "01:00"
    assert format_duration(3599) == "59:59"
    assert format_duration(3600) == "01:00:00"
    # Negative duration must not be negative string
    res_neg = format_duration(-1)
    assert res_neg in ("00:00", "--:--")


# ============================================================================
# 4. MISSING / DEAD SOCKET RESILIENCE
# ============================================================================

def test_missing_and_dead_socket_resilience():
    """
    Verify Player gracefully handles nonexistent or dead UNIX sockets
    without unhandled socket exceptions or crashes.
    """
    dead_sock = f"/tmp/wave-dead-{os.getpid()}-{int(time.time()*1000)}.sock"
    p = Player(sock_path=dead_sock)

    # Command on dead socket should return None
    res = p.send_command(["get_property", "time-pos"])
    assert res is None

    # Status on dead socket should return inactive dict
    status = p.get_status()
    assert isinstance(status, dict)
    assert status.get("active") is False

    # Transport controls should not raise uncaught exceptions
    p.toggle_pause()
    p.seek(10)
    p.set_volume(5)
    p.stop()


# ============================================================================
# 5. CONCURRENT DATABASE ACCESS (WAL MODE) (F01)
# ============================================================================

def test_concurrent_database_writes_wal_mode(db, db_adapter, sample_tracks):
    """
    Verify SQLite WAL mode allows concurrent threads to perform writes and reads
    simultaneously without 'database is locked' errors (F01).
    """
    num_threads = 8
    operations_per_thread = 20
    errors = []

    def worker_task(thread_id: int):
        try:
            # Each thread creates its own Database instance referencing same DB file
            thread_db = Database()
            for i in range(operations_per_thread):
                pl_name = f"Thread_{thread_id}_PL_{i}"
                pl_id = thread_db.create_playlist(pl_name)
                track = {
                    "id": f"t_{thread_id}_{i}",
                    "title": f"Song {i}",
                    "artist": f"Artist {thread_id}",
                    "duration": "03:00",
                    "duration_sec": 180,
                    "url": f"https://www.youtube.com/watch?v=t_{thread_id}_{i}"
                }
                thread_db.add_to_playlist(pl_id, track)
                db_adapter.add_liked(thread_db, track)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker_task, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    if errors:
        pytest.fail(f"Concurrent database writes failed with errors: {errors}")

    playlists = db.get_playlists()
    assert len(playlists) >= num_threads * operations_per_thread


# ============================================================================
# 6. DATABASE MIGRATION V1 -> V2 (F02)
# ============================================================================

def test_database_migration_v1_to_v2_data_preservation(tmp_path, monkeypatch):
    """
    Verify that an existing legacy v1 database (user_version = 0) is upgraded
    to v2 without losing records and with position column added (F02).
    """
    legacy_dir = tmp_path / "legacy_test"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    db_file = legacy_dir / "library.db"

    # Manually create legacy v1 schema (without position, user_version = 0)
    with sqlite3.connect(db_file) as conn:
        conn.execute("PRAGMA user_version = 0;")
        conn.execute("""
            CREATE TABLE liked_songs (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                artist TEXT NOT NULL,
                duration TEXT,
                duration_sec INTEGER,
                url TEXT NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE playlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE playlist_tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                playlist_id INTEGER NOT NULL,
                video_id TEXT NOT NULL,
                title TEXT NOT NULL,
                artist TEXT NOT NULL,
                duration TEXT,
                duration_sec INTEGER,
                url TEXT NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(playlist_id, video_id)
            )
        """)
        conn.execute("""
            INSERT INTO playlists (id, name) VALUES (1, 'Legacy Playlist')
        """)
        conn.execute("""
            INSERT INTO playlist_tracks (playlist_id, video_id, title, artist, duration, duration_sec, url)
            VALUES (1, 'leg_01', 'Legacy Song 1', 'Old Artist', '03:00', 180, 'https://yt.com/1')
        """)
        conn.execute("""
            INSERT INTO playlist_tracks (playlist_id, video_id, title, artist, duration, duration_sec, url)
            VALUES (1, 'leg_02', 'Legacy Song 2', 'Old Artist', '04:00', 240, 'https://yt.com/2')
        """)
        conn.commit()

    # Sandboxed HOME pointing to legacy_dir
    monkeypatch.setenv("HOME", str(legacy_dir))
    data_dir = legacy_dir / ".local" / "share" / "wave-cli"
    data_dir.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy(db_file, data_dir / "library.db")

    # Instantiate Database - should trigger migration runner
    migrated_db = Database()

    # Verify user_version is 2
    with migrated_db._get_connection() if hasattr(migrated_db, "_get_connection") else sqlite3.connect(data_dir / "library.db") as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA user_version;")
        version = cursor.fetchone()[0]
        if version < 2:
            pytest.fail(f"Feature F02 not implemented: user_version is {version}, expected >= 2")

        # Verify playlist and tracks are intact
        cursor.execute("SELECT name FROM playlists WHERE id = 1;")
        pl_row = cursor.fetchone()
        assert pl_row[0] == "Legacy Playlist"

        cursor.execute("SELECT video_id, position FROM playlist_tracks WHERE playlist_id = 1 ORDER BY id ASC;")
        tracks = cursor.fetchall()
        assert len(tracks) == 2
        assert tracks[0][0] == "leg_01"
        assert tracks[1][0] == "leg_02"


# ============================================================================
# 7. FILE DESCRIPTOR LEAK RESILIENCE (F06)
# ============================================================================

def test_database_connection_cleanup_no_fd_leaks(db):
    """
    Verify rapid queries do not leak file descriptors (F06).
    """
    initial_fd_count = len(os.listdir("/proc/self/fd"))

    for i in range(100):
        db.get_playlists()
        db.is_liked(f"test_{i}")

    final_fd_count = len(os.listdir("/proc/self/fd"))
    # Leaking connections would cause fd count to increase by ~100
    assert final_fd_count - initial_fd_count < 10, \
        f"File descriptor leak detected: grew from {initial_fd_count} to {final_fd_count}"


# ============================================================================
# 8. IPC STREAM FRAMING & COALESCED MESSAGES (F09)
# ============================================================================

def test_player_ipc_line_buffered_coalesced_json(tmp_path):
    """
    Verify player socket parser handles multiple JSON messages received in a single chunk (F09).
    """
    sock_path = str(tmp_path / "framing_test.sock")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(sock_path)
    server.listen(1)

    received_data = []

    def server_thread():
        try:
            conn, _ = server.accept()
            # Wait for client command
            data = conn.recv(1024)
            # Send two responses coalesced in single packet
            packet = b'{"error":"success","data":"first"}\n{"error":"success","data":"second"}\n'
            conn.sendall(packet)
            conn.close()
        except OSError:
            pass

    t = threading.Thread(target=server_thread, daemon=True)
    t.start()

    p = Player(sock_path=sock_path)
    resp = p.send_command(["get_property", "time-pos"])
    assert resp is not None
    assert "error" in resp

    server.close()
    if os.path.exists(sock_path):
        os.unlink(sock_path)
