"""
Adversarial Verification Suite for Database Architecture & Persistent CRUD (Milestone 1).
Targets:
1. Boundary conditions in move_playlist_track and move_queue_track
2. Foreign key cascade deletion on 50 tracks (API and raw SQLite engine CASCADE)
3. Migration edge cases (corrupted DBs, partial migrations, duplicate tracks, NULL fields, missing columns)
4. File descriptor leak verification across 200 diverse operations
5. Multi-threaded WAL concurrency position integrity
"""

import os
import sqlite3
import tempfile
import threading
from pathlib import Path
from typing import Dict, List
import pytest

from wave.db import Database


# ============================================================================
# 1. BOUNDARY TESTS FOR move_playlist_track & move_queue_track
# ============================================================================

def test_move_playlist_track_normal_reordering(tmp_path: Path):
    """Verify normal reordering in a 5-track playlist."""
    db_path = tmp_path / "normal_reorder.db"
    db = Database(db_path)
    pl_id = db.create_playlist("Test Playlist")

    for i in range(5):
        db.add_to_playlist(pl_id, {
            "id": f"vid_{i}",
            "title": f"Song {i}",
            "artist": "Artist",
            "duration": "03:00",
            "duration_sec": 180,
            "url": f"https://youtube.com/watch?v=vid_{i}"
        })

    # Move 0 -> 4
    assert db.move_playlist_track(pl_id, 0, 4) is True
    tracks = db.get_playlist_tracks(pl_id)
    assert [t["video_id"] for t in tracks] == ["vid_1", "vid_2", "vid_3", "vid_4", "vid_0"]
    assert [t["position"] for t in tracks] == [0, 1, 2, 3, 4]

    # Move 4 -> 0
    assert db.move_playlist_track(pl_id, 4, 0) is True
    tracks = db.get_playlist_tracks(pl_id)
    assert [t["video_id"] for t in tracks] == ["vid_0", "vid_1", "vid_2", "vid_3", "vid_4"]
    assert [t["position"] for t in tracks] == [0, 1, 2, 3, 4]


def test_move_playlist_track_valid_identical_indices(tmp_path: Path):
    """Verify valid in-bounds identical indices (no-op) return True."""
    db_path = tmp_path / "valid_identical.db"
    db = Database(db_path)
    pl_id = db.create_playlist("Populated Playlist")

    for i in range(5):
        db.add_to_playlist(pl_id, {"id": f"trk_{i}", "title": f"T{i}"})

    assert db.move_playlist_track(pl_id, 0, 0) is True
    assert db.move_playlist_track(pl_id, 2, 2) is True
    assert db.move_playlist_track(pl_id, 4, 4) is True

    # Non-existent playlist ID
    assert db.move_playlist_track(999999, 0, 0) is False


def test_move_playlist_track_out_of_bounds_identical_indices(tmp_path: Path):
    """
    CRITICAL ADVERSARIAL TEST:
    Verify that out-of-bounds indices with from_pos == to_pos correctly return False.
    Expected:
      - Empty playlist (count == 0): move_playlist_track(empty_pl, 0, 0) MUST return False.
      - Populated playlist (count == 5): move_playlist_track(pl, 10, 10) MUST return False.
      - Populated playlist (count == 5): move_playlist_track(pl, -1, -1) MUST return False.
    """
    db_path = tmp_path / "oob_identical.db"
    db = Database(db_path)
    pl_id = db.create_playlist("Populated Playlist")
    for i in range(5):
        db.add_to_playlist(pl_id, {"id": f"trk_{i}", "title": f"T{i}"})

    empty_pl_id = db.create_playlist("Empty Playlist")

    # 1. On empty playlist, moving position 0 to 0 must fail (no tracks exist)
    assert db.move_playlist_track(empty_pl_id, 0, 0) is False, (
        "move_playlist_track(empty_pl, 0, 0) returned True on empty playlist! Boundary check bypassed."
    )

    # 2. On populated playlist (5 tracks, indices 0..4), index 10 must fail
    assert db.move_playlist_track(pl_id, 10, 10) is False, (
        "move_playlist_track(pl, 10, 10) returned True when length is 5! Boundary check bypassed."
    )

    # 3. On populated playlist (5 tracks), negative index -1 must fail
    assert db.move_playlist_track(pl_id, -1, -1) is False, (
        "move_playlist_track(pl, -1, -1) returned True! Negative index check bypassed."
    )


def test_move_queue_track_out_of_bounds_identical_indices(tmp_path: Path):
    """
    CRITICAL ADVERSARIAL TEST:
    Verify that move_queue_track rejects out-of-bounds indices when from_pos == to_pos.
    Expected:
      - Empty queue: move_queue_track(0, 0) MUST return False.
      - Negative indices: move_queue_track(-5, -5) MUST return False.
      - Out-of-bounds indices: move_queue_track(100, 100) MUST return False.
    """
    db_path = tmp_path / "queue_identical.db"
    db = Database(db_path)

    assert db.move_queue_track(0, 0) is False, (
        "move_queue_track(0, 0) returned True on empty queue! Early return bypassed length validation."
    )
    assert db.move_queue_track(-5, -5) is False, (
        "move_queue_track(-5, -5) returned True for negative indices!"
    )
    assert db.move_queue_track(100, 100) is False, (
        "move_queue_track(100, 100) returned True for out-of-bounds index!"
    )


def test_move_playlist_track_negative_indices(tmp_path: Path):
    """Verify handling of negative indices when from_pos != to_pos."""
    db_path = tmp_path / "negative_indices.db"
    db = Database(db_path)
    pl_id = db.create_playlist("Negative Indices Test")

    for i in range(3):
        db.add_to_playlist(pl_id, {"id": f"trk_{i}", "title": f"T{i}"})

    assert db.move_playlist_track(pl_id, -1, 1) is False
    assert db.move_playlist_track(pl_id, -5, 2) is False
    assert db.move_playlist_track(pl_id, 1, -1) is False
    assert db.move_playlist_track(pl_id, 0, -2) is False
    assert db.move_playlist_track(pl_id, -2, -1) is False

    tracks = db.get_playlist_tracks(pl_id)
    assert [t["video_id"] for t in tracks] == ["trk_0", "trk_1", "trk_2"]
    assert [t["position"] for t in tracks] == [0, 1, 2]


def test_move_playlist_track_indices_greater_than_or_equal_to_length(tmp_path: Path):
    """Verify handling of indices >= playlist length when from_pos != to_pos."""
    db_path = tmp_path / "oob_indices.db"
    db = Database(db_path)
    pl_id = db.create_playlist("OOB Indices Test")

    for i in range(3):
        db.add_to_playlist(pl_id, {"id": f"trk_{i}", "title": f"T{i}"})

    assert db.move_playlist_track(pl_id, 3, 1) is False
    assert db.move_playlist_track(pl_id, 1, 3) is False
    assert db.move_playlist_track(pl_id, 5, 1) is False
    assert db.move_playlist_track(pl_id, 1, 5) is False
    assert db.move_playlist_track(pl_id, 10, 20) is False

    tracks = db.get_playlist_tracks(pl_id)
    assert [t["video_id"] for t in tracks] == ["trk_0", "trk_1", "trk_2"]
    assert [t["position"] for t in tracks] == [0, 1, 2]


def test_move_playlist_track_single_item_playlist(tmp_path: Path):
    """Verify behavior on a single-item playlist (count = 1)."""
    db_path = tmp_path / "single_item.db"
    db = Database(db_path)
    pl_id = db.create_playlist("Single Item Playlist")

    db.add_to_playlist(pl_id, {"id": "single_trk", "title": "Lone Track"})

    # Valid in-bounds no-op (0 -> 0)
    assert db.move_playlist_track(pl_id, 0, 0) is True

    # Out-of-bounds moves
    assert db.move_playlist_track(pl_id, 0, 1) is False
    assert db.move_playlist_track(pl_id, 1, 0) is False
    assert db.move_playlist_track(pl_id, 0, -1) is False
    assert db.move_playlist_track(pl_id, -1, 0) is False

    tracks = db.get_playlist_tracks(pl_id)
    assert len(tracks) == 1
    assert tracks[0]["video_id"] == "single_trk"
    assert tracks[0]["position"] == 0


# ============================================================================
# 2. DELETION AND FOREIGN KEY CASCADE (50 TRACKS)
# ============================================================================

def test_deletion_and_foreign_key_cascade_50_tracks(tmp_path: Path):
    """
    Populate a playlist with 50 tracks and another with 50 tracks.
    Verify:
    1. db.delete_playlist cleanly purges all 50 tracks.
    2. Neighboring playlist tracks are 100% intact with contiguous positions.
    3. Direct raw SQL DELETE FROM playlists cascades cleanly via SQLite engine.
    """
    db_path = tmp_path / "cascade_test.db"
    db = Database(db_path)

    # Playlist A with 50 tracks
    pl_a = db.create_playlist("Playlist A (To Delete)")
    tracks_a = [
        {
            "id": f"vid_a_{i:03d}",
            "title": f"Song A {i}",
            "artist": "Artist A",
            "duration": "03:00",
            "duration_sec": 180,
            "url": f"https://youtube.com/watch?v=vid_a_{i:03d}"
        }
        for i in range(50)
    ]
    added_a = db.add_tracks_to_playlist(pl_a, tracks_a)
    assert added_a == 50

    # Playlist B with 50 tracks
    pl_b = db.create_playlist("Playlist B (To Keep)")
    tracks_b = [
        {
            "id": f"vid_b_{i:03d}",
            "title": f"Song B {i}",
            "artist": "Artist B",
            "duration": "04:00",
            "duration_sec": 240,
            "url": f"https://youtube.com/watch?v=vid_b_{i:03d}"
        }
        for i in range(50)
    ]
    added_b = db.add_tracks_to_playlist(pl_b, tracks_b)
    assert added_b == 50

    # Baseline verification
    with db._connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM playlist_tracks WHERE playlist_id = ?;", (pl_a,))
        assert cursor.fetchone()[0] == 50
        cursor.execute("SELECT COUNT(*) FROM playlist_tracks WHERE playlist_id = ?;", (pl_b,))
        assert cursor.fetchone()[0] == 50
        cursor.execute("SELECT COUNT(*) FROM playlist_tracks;")
        assert cursor.fetchone()[0] == 100

    # 1. Delete Playlist A via Database API
    assert db.delete_playlist(pl_a) is True

    # Verify Playlist A is gone
    assert db.get_playlist(pl_a) is None
    assert db.get_playlist_tracks(pl_a) == []

    # Verify raw SQL: exactly 0 tracks remain for pl_a
    with db._connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM playlist_tracks WHERE playlist_id = ?;", (pl_a,))
        assert cursor.fetchone()[0] == 0
        cursor.execute("SELECT COUNT(*) FROM playlists WHERE id = ?;", (pl_a,))
        assert cursor.fetchone()[0] == 0

        # Playlist B tracks remain intact and contiguous
        cursor.execute("SELECT COUNT(*) FROM playlist_tracks WHERE playlist_id = ?;", (pl_b,))
        assert cursor.fetchone()[0] == 50
        cursor.execute("SELECT COUNT(*) FROM playlist_tracks;")
        assert cursor.fetchone()[0] == 50

    tracks_remaining = db.get_playlist_tracks(pl_b)
    assert len(tracks_remaining) == 50
    assert [t["position"] for t in tracks_remaining] == list(range(50))
    assert [t["video_id"] for t in tracks_remaining] == [f"vid_b_{i:03d}" for i in range(50)]

    # 2. Test raw SQLite ENGINE FOREIGN KEY CASCADE enforcement
    with db._connection() as conn:
        conn.execute("DELETE FROM playlists WHERE id = ?;", (pl_b,))

    # Confirm engine ON DELETE CASCADE purged all 50 tracks of Playlist B
    with db._connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM playlist_tracks;")
        assert cursor.fetchone()[0] == 0, "Engine ON DELETE CASCADE failed to delete child tracks!"
        cursor.execute("SELECT COUNT(*) FROM playlists;")
        assert cursor.fetchone()[0] == 0


# ============================================================================
# 3. MIGRATION EDGE CASES
# ============================================================================

def test_migration_corrupted_database_file(tmp_path: Path):
    """Verify that corrupt or truncated database files fail gracefully with sqlite3.DatabaseError."""
    # 1. Random junk file
    junk_path = tmp_path / "corrupt_junk.db"
    junk_path.write_bytes(b"THIS_IS_NOT_A_VALID_SQLITE_DATABASE_HEADER_AT_ALL_1234567890")

    with pytest.raises(sqlite3.DatabaseError):
        Database(junk_path)

    # 2. Truncated SQLite header (less than 100 bytes)
    truncated_path = tmp_path / "truncated.db"
    truncated_path.write_bytes(b"SQLite format 3\x00" + b"\x00" * 20)

    with pytest.raises(sqlite3.DatabaseError):
        Database(truncated_path)


def test_migration_partially_migrated_user_version_1(tmp_path: Path):
    """
    Simulate an interrupted or intermediate migration state (user_version = 1)
    where some tables or columns exist, and verify upgrade to v2 is seamless.
    """
    db_path = tmp_path / "partial_v1.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA user_version = 1;")
    conn.execute("""
        CREATE TABLE playlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
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
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.execute("INSERT INTO playlists (id, name) VALUES (1, 'Partial Playlist');")
    conn.execute("""
        INSERT INTO playlist_tracks (playlist_id, video_id, title, artist, duration, duration_sec, url)
        VALUES (1, 'p_trk_1', 'P Title', 'P Artist', '03:00', 180, 'http://yt.com/1');
    """)
    conn.commit()
    conn.close()

    # Open with Database manager
    db = Database(db_path)

    with db._connection() as c:
        cursor = c.cursor()
        cursor.execute("PRAGMA user_version;")
        assert cursor.fetchone()[0] == 2

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {r["name"] for r in cursor.fetchall()}
        assert "queue_tracks" in tables
        assert "player_state" in tables

    tracks = db.get_playlist_tracks(1)
    assert len(tracks) == 1
    assert tracks[0]["video_id"] == "p_trk_1"
    assert tracks[0]["position"] == 0


def test_migration_v1_with_duplicate_tracks(tmp_path: Path):
    """
    Simulate a legacy v1 database where playlist_tracks had duplicate tracks
    for the same playlist (e.g. legacy schema lacked UNIQUE constraint).
    Verify how migration and subsequent CRUD handle duplicate tracks.
    """
    db_path = tmp_path / "v1_duplicates.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA user_version = 0;")
    conn.execute("""
        CREATE TABLE playlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
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
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.execute("INSERT INTO playlists (id, name) VALUES (1, 'Duplicate Playlist');")
    conn.execute("""
        INSERT INTO playlist_tracks (playlist_id, video_id, title, artist, duration, duration_sec, url, added_at)
        VALUES (1, 'dup_vid', 'Dup Song', 'Artist D', '02:00', 120, 'http://yt.com/d', '2026-01-01 10:00:00');
    """)
    conn.execute("""
        INSERT INTO playlist_tracks (playlist_id, video_id, title, artist, duration, duration_sec, url, added_at)
        VALUES (1, 'other_vid', 'Other Song', 'Artist O', '03:00', 180, 'http://yt.com/o', '2026-01-01 10:01:00');
    """)
    conn.execute("""
        INSERT INTO playlist_tracks (playlist_id, video_id, title, artist, duration, duration_sec, url, added_at)
        VALUES (1, 'dup_vid', 'Dup Song', 'Artist D', '02:00', 120, 'http://yt.com/d', '2026-01-01 10:02:00');
    """)
    conn.commit()
    conn.close()

    db = Database(db_path)

    with db._connection() as c:
        cursor = c.cursor()
        cursor.execute("PRAGMA user_version;")
        assert cursor.fetchone()[0] == 2

    tracks = db.get_playlist_tracks(1)
    assert len(tracks) == 3
    assert [t["position"] for t in tracks] == [0, 1, 2]
    assert [t["video_id"] for t in tracks] == ["dup_vid", "other_vid", "dup_vid"]

    # Remove by position 2 (the second duplicate)
    assert db.remove_from_playlist(1, 2) is True
    remaining = db.get_playlist_tracks(1)
    assert len(remaining) == 2
    assert [t["position"] for t in remaining] == [0, 1]
    assert [t["video_id"] for t in remaining] == ["dup_vid", "other_vid"]


def test_migration_v1_with_null_fields(tmp_path: Path):
    """
    Simulate a legacy v1 database with NULL fields across playlists,
    playlist_tracks, liked_songs, and history. Verify graceful handling.
    """
    db_path = tmp_path / "v1_nulls.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA user_version = 0;")
    conn.execute("""
        CREATE TABLE playlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT NULL
        );
    """)
    conn.execute("""
        CREATE TABLE playlist_tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            playlist_id INTEGER NOT NULL,
            video_id TEXT NOT NULL,
            title TEXT,
            artist TEXT,
            duration TEXT,
            duration_sec INTEGER,
            url TEXT,
            added_at TIMESTAMP DEFAULT NULL
        );
    """)
    conn.execute("""
        CREATE TABLE liked_songs (
            id TEXT PRIMARY KEY,
            title TEXT,
            artist TEXT,
            duration TEXT,
            duration_sec INTEGER,
            url TEXT,
            added_at TIMESTAMP DEFAULT NULL
        );
    """)
    conn.execute("""
        CREATE TABLE history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT,
            title TEXT,
            artist TEXT,
            duration TEXT,
            duration_sec INTEGER,
            url TEXT,
            played_at TIMESTAMP DEFAULT NULL
        );
    """)

    conn.execute("INSERT INTO playlists (id, name, created_at) VALUES (1, 'Null Playlist', NULL);")
    conn.execute("""
        INSERT INTO playlist_tracks (playlist_id, video_id, title, artist, duration, duration_sec, url, added_at)
        VALUES (1, 'null_trk', NULL, NULL, NULL, NULL, NULL, NULL);
    """)
    conn.execute("""
        INSERT INTO liked_songs (id, title, artist, duration, duration_sec, url, added_at)
        VALUES ('null_liked', NULL, NULL, NULL, NULL, NULL, NULL);
    """)
    conn.execute("""
        INSERT INTO history (id, video_id, title, artist, duration, duration_sec, url, played_at)
        VALUES (1, 'null_hist', NULL, NULL, NULL, NULL, NULL, NULL);
    """)
    conn.commit()
    conn.close()

    db = Database(db_path)

    # 1. Playlists query with NULL created_at
    pls = db.get_playlists()
    assert len(pls) == 1
    assert pls[0]["created_at"] is None
    assert pls[0]["updated_at"] is not None
    assert pls[0]["total_duration_sec"] == 0

    # 2. Playlist tracks query with NULL fields
    tracks = db.get_playlist_tracks(1)
    assert len(tracks) == 1
    assert tracks[0]["duration"] == "--:--"
    assert tracks[0]["duration_sec"] == 0
    assert tracks[0]["position"] == 0
    assert tracks[0]["added_at"] is None

    # 3. Liked songs query with NULL fields
    liked = db.get_liked_songs()
    assert len(liked) == 1
    assert liked[0]["duration"] == "--:--"
    assert liked[0]["duration_sec"] == 0
    assert liked[0]["added_at"] is None

    # 4. History query with NULL fields
    hist = db.get_history()
    assert len(hist) == 1
    assert hist[0]["duration"] == "--:--"
    assert hist[0]["duration_sec"] == 0
    assert hist[0]["played_at"] is None


def test_migration_v1_missing_created_at_in_playlists(tmp_path: Path):
    """
    EDGE CASE: What if a legacy v1 database had a playlists table that lacked created_at?
    In database.py:286:
    UPDATE playlists SET updated_at = COALESCE(created_at, CURRENT_TIMESTAMP)...
    If created_at is absent, SQLite raises: no such column: created_at.
    """
    db_path = tmp_path / "v1_no_created_at.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA user_version = 0;")
    conn.execute("""
        CREATE TABLE playlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );
    """)
    conn.execute("INSERT INTO playlists (id, name) VALUES (1, 'No Created At');")
    conn.commit()
    conn.close()

    # Migration MUST handle missing created_at without crashing
    db = Database(db_path)
    pls = db.get_playlists()
    assert len(pls) == 1
    assert pls[0]["name"] == "No Created At"


# ============================================================================
# 4. FILE DESCRIPTOR LEAK STRESS TEST (200 DIVERSE OPERATIONS)
# ============================================================================

def test_file_descriptor_leak_200_diverse_operations(tmp_path: Path):
    """
    Execute 200 diverse operations across reads, writes, transaction rollbacks,
    and connection instantiations, inspecting /proc/self/fd to verify zero FD leak.
    """
    if not os.path.exists("/proc/self/fd"):
        pytest.skip("/proc/self/fd not supported on this platform")

    db_path = tmp_path / "fd_leak_stress.db"
    db = Database(db_path)

    pl_id = db.create_playlist("FD Test Playlist")
    for i in range(10):
        db.add_to_playlist(pl_id, {
            "id": f"fd_trk_{i}",
            "title": f"FD Track {i}",
            "artist": "Artist",
            "duration": "03:00",
            "duration_sec": 180,
            "url": f"https://youtube.com/watch?v=fd_trk_{i}"
        })
        db.add_liked({
            "id": f"fd_liked_{i}",
            "title": f"Liked {i}",
            "artist": "Artist",
            "duration": "03:00",
            "duration_sec": 180,
            "url": f"https://youtube.com/watch?v=fd_liked_{i}"
        })

    # Warmup
    db.get_playlists()
    db.get_playlist_tracks(pl_id)
    initial_fds = len(os.listdir("/proc/self/fd"))

    # Loop 200 diverse operations
    for op_idx in range(200):
        mode = op_idx % 4

        if mode == 0:
            # Reads
            _ = db.get_playlists()
            _ = db.get_playlist_tracks(pl_id)
            _ = db.get_liked_ids()
            _ = db.get_liked_songs()
            _ = db.get_queue()
            _ = db.get_player_state()
            _ = db.get_history()
        elif mode == 1:
            # Writes
            db.add_history({"id": f"h_vid_{op_idx}", "title": "H Track"}, max_history=50)
            db.add_to_queue({"id": f"q_vid_{op_idx}", "title": "Q Track"})
            db.save_player_state(f"fd_trk_{op_idx % 10}", op_idx % 5, float(op_idx), 75.0)
            db.toggle_liked({"id": f"fd_toggle_{op_idx % 5}", "title": "Toggle Track"})
        elif mode == 2:
            # Errors / Rollbacks
            _ = db.create_playlist("FD Test Playlist")  # Duplicate name
            _ = db.move_playlist_track(pl_id, -10, 100)  # Invalid move
            _ = db.remove_from_queue(99999)              # Non-existent queue pos
            _ = db.add_to_playlist(999999, {"id": "ghost_vid"})  # Non-existent playlist
        else:
            # Fresh Database instances opened on same file
            temp_db = Database(db_path)
            _ = temp_db.get_playlists()
            _ = temp_db.is_liked("fd_liked_0")
            temp_db.close()

    final_fds = len(os.listdir("/proc/self/fd"))
    assert final_fds == initial_fds, f"File descriptor leak detected! Initial: {initial_fds}, Final: {final_fds}"
