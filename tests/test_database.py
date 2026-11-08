"""
Comprehensive unit test suite for wave-cli Database Architecture and Persistent CRUD Engine.
Verifies Interface Contract 1, WAL concurrency, FD leak prevention, zero-data-loss migrations,
and backward compatibility across all operations.
"""

import os
import stat
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List
import pytest

from wave.db import Database


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mem_db() -> Database:
    """Fixture providing an in-memory Database instance."""
    db = Database(":memory:")
    yield db
    db.close()


@pytest.fixture
def file_db(tmp_path: Path) -> Database:
    """Fixture providing a temporary file-based Database instance."""
    db_file = tmp_path / "test_library.db"
    db = Database(db_file)
    yield db
    db.close()


@pytest.fixture
def sample_tracks_list() -> List[Dict[str, Any]]:
    """Standardized realistic track fixtures."""
    return [
        {
            "id": f"trk_{i:03d}",
            "video_id": f"trk_{i:03d}",
            "title": f"Synth Track {i}",
            "artist": f"Artist {i % 5}",
            "duration": f"0{3 + (i % 3)}:30",
            "duration_sec": 210 + (i * 10),
            "url": f"https://www.youtube.com/watch?v=trk_{i:03d}",
            "source": "youtube",
            "thumbnail_url": f"https://img.youtube.com/vi/trk_{i:03d}/default.jpg",
        }
        for i in range(1, 11)
    ]


# ============================================================================
# 1. INITIALIZATION & CONFIGURATION
# ============================================================================

def test_init_memory_database():
    """Verify :memory: database persistence across calls and clean closure."""
    with Database(":memory:") as db:
        assert db._is_memory is True
        assert db.db_path == ":memory:"
        pl_id = db.create_playlist("Memory Playlist")
        assert pl_id is not None
        # Subsequent query on same instance retrieves the playlist
        playlists = db.get_playlists()
        assert len(playlists) == 1
        assert playlists[0]["name"] == "Memory Playlist"


def test_init_temp_file_database(tmp_path: Path):
    """Verify file-based DB creation with secure 0700 parent directory permissions."""
    custom_dir = tmp_path / "custom_store"
    db_file = custom_dir / "lib.db"
    assert not custom_dir.exists()

    db = Database(db_file)
    try:
        assert db_file.exists()
        assert custom_dir.exists()
        dir_mode = stat.S_IMODE(custom_dir.stat().st_mode)
        assert dir_mode == 0o700, f"Expected 0o700, got {oct(dir_mode)}"
    finally:
        db.close()


def test_init_xdg_data_home_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify $XDG_DATA_HOME environment variable sets the database path."""
    xdg_target = tmp_path / "xdg_share"
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_target))

    db = Database()
    try:
        expected_path = xdg_target / "wave-cli" / "library.db"
        assert db.db_path == expected_path
        assert expected_path.exists()
        dir_mode = stat.S_IMODE(expected_path.parent.stat().st_mode)
        assert dir_mode == 0o700
    finally:
        db.close()


def test_context_manager_support():
    """Verify Database supports 'with Database(...) as db:' context manager."""
    with Database(":memory:") as db:
        pl_id = db.create_playlist("Ctx PL")
        assert pl_id is not None
    # After exiting block, memory connection is closed
    with pytest.raises(sqlite3.OperationalError):
        db.get_playlists()


# ============================================================================
# 2. CONNECTION LIFECYCLE, PRAGMAS & FD LEAK PREVENTION
# ============================================================================

def test_connection_pragmas_wal_mode(file_db: Database):
    """Verify every file connection enforces WAL mode, NORMAL sync, foreign keys, and busy timeout."""
    with file_db._connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode;")
        journal_mode = cursor.fetchone()[0]
        cursor.execute("PRAGMA synchronous;")
        sync = cursor.fetchone()[0]
        cursor.execute("PRAGMA foreign_keys;")
        fk = cursor.fetchone()[0]
        cursor.execute("PRAGMA busy_timeout;")
        bt = cursor.fetchone()[0]

        assert journal_mode.lower() == "wal"
        assert sync == 1  # NORMAL
        assert fk == 1    # ON
        assert bt == 10000


def test_connection_no_file_descriptor_leak(file_db: Database):
    """Verify 200 consecutive database operations leak exactly zero file descriptors."""
    if not os.path.exists("/proc/self/fd"):
        pytest.skip("/proc/self/fd not supported on this platform")

    # Warm up connection
    file_db.get_playlists()
    initial_fds = len(os.listdir("/proc/self/fd"))

    for i in range(200):
        file_db.get_playlists()
        file_db.is_liked(f"vid_{i}")
        file_db.get_player_state()

    final_fds = len(os.listdir("/proc/self/fd"))
    assert final_fds == initial_fds, f"Leaked FDs: initial={initial_fds}, final={final_fds}"


def test_connection_rollback_on_uncaught_exception(file_db: Database):
    """Verify transaction automatically rolls back when an uncaught exception occurs."""
    pl_id = file_db.create_playlist("Rollback Test")
    assert pl_id is not None

    with pytest.raises(RuntimeError):
        with file_db._connection() as conn:
            conn.execute(
                "INSERT INTO playlist_tracks (playlist_id, video_id, title, artist, url, position) VALUES (?, ?, ?, ?, ?, ?)",
                (pl_id, "rb_01", "RB Title", "RB Artist", "http://rb.com", 0)
            )
            raise RuntimeError("Intentional error to trigger rollback")

    # Track was not committed
    tracks = file_db.get_playlist_tracks(pl_id)
    assert len(tracks) == 0


def test_row_factory_sqlite_row(mem_db: Database):
    """Verify connection row_factory is sqlite3.Row supporting dict access."""
    with mem_db._connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 AS col_a, 'hello' AS col_b;")
        row = cursor.fetchone()
        assert isinstance(row, sqlite3.Row)
        assert row["col_a"] == 1
        assert row["col_b"] == "hello"
        assert dict(row) == {"col_a": 1, "col_b": "hello"}


# ============================================================================
# 3. SCHEMA CREATION & ZERO-DATA-LOSS MIGRATION (v1 -> v2)
# ============================================================================

def test_fresh_schema_v2_creation(file_db: Database):
    """Verify a clean database creates all v2 tables, indexes, and sets user_version=2."""
    with file_db._connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA user_version;")
        assert cursor.fetchone()[0] == 2

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {r["name"] for r in cursor.fetchall()}
        expected_tables = {"playlists", "playlist_tracks", "liked_songs", "history", "queue_tracks", "player_state"}
        assert expected_tables.issubset(tables)

        cursor.execute("SELECT name FROM sqlite_master WHERE type='index';")
        indexes = {r["name"] for r in cursor.fetchall()}
        expected_indexes = {
            "idx_liked_songs_added", "idx_history_played_at", "idx_history_video_id",
            "idx_playlists_name", "idx_playlist_tracks_pos", "idx_playlist_tracks_vid",
            "idx_queue_tracks_pos", "idx_queue_tracks_vid"
        }
        assert expected_indexes.issubset(indexes)


def test_legacy_v1_to_v2_migration_preserves_all_data(tmp_path: Path):
    """
    Simulate legacy v1 schema with user_version=0, existing playlists, tracks,
    and history, and verify zero data loss when upgraded by Database.
    """
    db_path = tmp_path / "legacy_v1.db"

    # 1. Build legacy v1 schema manually
    conn = sqlite3.connect(str(db_path))
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
        );
    """)
    conn.execute("""
        CREATE TABLE history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL,
            title TEXT NOT NULL,
            artist TEXT NOT NULL,
            duration TEXT,
            duration_sec INTEGER,
            url TEXT NOT NULL,
            played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
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
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(playlist_id, video_id),
            FOREIGN KEY(playlist_id) REFERENCES playlists(id) ON DELETE CASCADE
        );
    """)

    # Populate legacy rows
    conn.execute("INSERT INTO playlists (id, name, created_at) VALUES (1, 'V1 Synth', '2026-01-01 10:00:00');")
    conn.execute("INSERT INTO playlists (id, name, created_at) VALUES (2, 'V1 Chill', '2026-01-02 11:00:00');")

    # Playlist 1 tracks inserted in reverse order to verify ROW_NUMBER contiguous backfill
    conn.execute("""
        INSERT INTO playlist_tracks (id, playlist_id, video_id, title, artist, duration, duration_sec, url, added_at)
        VALUES (10, 1, 'vid_01', 'Song 1', 'Artist A', '03:00', 180, 'http://yt.com/1', '2026-01-01 10:01:00');
    """)
    conn.execute("""
        INSERT INTO playlist_tracks (id, playlist_id, video_id, title, artist, duration, duration_sec, url, added_at)
        VALUES (11, 1, 'vid_02', 'Song 2', 'Artist B', '04:00', 240, 'http://yt.com/2', '2026-01-01 10:02:00');
    """)
    conn.execute("""
        INSERT INTO playlist_tracks (id, playlist_id, video_id, title, artist, duration, duration_sec, url, added_at)
        VALUES (12, 1, 'vid_03', 'Song 3', 'Artist C', '02:30', 150, 'http://yt.com/3', '2026-01-01 10:03:00');
    """)

    # Playlist 2 tracks
    conn.execute("""
        INSERT INTO playlist_tracks (id, playlist_id, video_id, title, artist, duration, duration_sec, url, added_at)
        VALUES (20, 2, 'vid_20', 'Chill 1', 'Artist Z', '05:00', 300, 'http://yt.com/20', '2026-01-02 11:05:00');
    """)

    conn.execute("""
        INSERT INTO liked_songs (id, title, artist, duration, duration_sec, url, added_at)
        VALUES ('liked_01', 'Loved Song', 'Artist L', '03:15', 195, 'http://yt.com/l', '2026-01-01 12:00:00');
    """)
    conn.execute("""
        INSERT INTO history (id, video_id, title, artist, duration, duration_sec, url, played_at)
        VALUES (1, 'hist_01', 'History Song', 'Artist H', '03:30', 210, 'http://yt.com/h', '2026-01-01 13:00:00');
    """)
    conn.commit()
    conn.close()

    # 2. Open with new Database manager — automatically runs migration
    migrated_db = Database(db_path)
    try:
        # Check user_version
        with migrated_db._connection() as c:
            ver = c.execute("PRAGMA user_version;").fetchone()[0]
            assert ver == 2

        # Check playlists preserved and updated_at backfilled
        pls = migrated_db.get_playlists()
        assert len(pls) == 2
        p1 = [p for p in pls if p["id"] == 1][0]
        assert p1["name"] == "V1 Synth"
        assert p1["count"] == 3
        assert p1["total_duration_sec"] == 180 + 240 + 150
        assert p1["created_at"] == "2026-01-01 10:00:00"
        assert p1["updated_at"] is not None

        # Check playlist tracks preserved and position backfilled contiguously
        p1_tracks = migrated_db.get_playlist_tracks(1)
        assert len(p1_tracks) == 3
        assert [t["position"] for t in p1_tracks] == [0, 1, 2]
        assert [t["video_id"] for t in p1_tracks] == ["vid_01", "vid_02", "vid_03"]

        p2_tracks = migrated_db.get_playlist_tracks(2)
        assert len(p2_tracks) == 1
        assert p2_tracks[0]["position"] == 0
        assert p2_tracks[0]["video_id"] == "vid_20"

        # Check liked songs and history preserved
        liked = migrated_db.get_liked_songs()
        assert len(liked) == 1
        assert liked[0]["id"] == "liked_01"
        assert liked[0]["source"] == "youtube"

        history = migrated_db.get_history()
        assert len(history) == 1
        assert history[0]["id"] == "hist_01"
        assert history[0]["source"] == "youtube"

        # Check new tables exist and are empty
        assert migrated_db.get_queue() == []
        state = migrated_db.get_player_state()
        assert state["queue_index"] == 0
    finally:
        migrated_db.close()


def test_migration_idempotent(file_db: Database):
    """Verify running migrations repeatedly does not error or modify schema."""
    with file_db._connection() as conn:
        # Calling migration runner a second time
        file_db._run_migrations(conn)
        cursor = conn.cursor()
        cursor.execute("PRAGMA user_version;")
        assert cursor.fetchone()[0] == 2


# ============================================================================
# 4. PLAYLISTS CRUD
# ============================================================================

def test_playlist_create_and_read(mem_db: Database):
    """Verify creating and retrieving playlists."""
    pl_id = mem_db.create_playlist("Chill Synth", "Relaxing electronic beats")
    assert pl_id is not None

    meta = mem_db.get_playlist(pl_id)
    assert meta["id"] == pl_id
    assert meta["name"] == "Chill Synth"
    assert meta["description"] == "Relaxing electronic beats"
    assert meta["created_at"] is not None
    assert meta["updated_at"] is not None

    all_pls = mem_db.get_playlists()
    assert len(all_pls) == 1
    assert all_pls[0]["name"] == "Chill Synth"
    assert all_pls[0]["count"] == 0
    assert all_pls[0]["total_duration_sec"] == 0


def test_playlist_empty_name_rejected(mem_db: Database):
    """Verify empty or whitespace-only playlist names are rejected."""
    assert mem_db.create_playlist("") is None
    assert mem_db.create_playlist("   ") is None
    assert len(mem_db.get_playlists()) == 0


def test_playlist_duplicate_name_returns_existing_id(mem_db: Database):
    """Verify creating duplicate playlist name returns the existing ID without creating extra rows."""
    id1 = mem_db.create_playlist("Synth Wave")
    id2 = mem_db.create_playlist("Synth Wave")
    assert id1 == id2
    assert len(mem_db.get_playlists()) == 1


def test_playlist_rename(mem_db: Database):
    """Verify renaming a playlist updates its name and updated_at timestamp."""
    pl_id = mem_db.create_playlist("Old Name")
    time.sleep(0.01)

    assert mem_db.rename_playlist(pl_id, "New Name") is True
    pl = mem_db.get_playlist(pl_id)
    assert pl["name"] == "New Name"

    # Reject empty new name
    assert mem_db.rename_playlist(pl_id, "") is False
    assert mem_db.rename_playlist(pl_id, "   ") is False

    # Reject renaming to an already taken name
    id2 = mem_db.create_playlist("Second List")
    assert mem_db.rename_playlist(pl_id, "Second List") is False

    # Reject non-existent ID
    assert mem_db.rename_playlist(9999, "Non Existent") is False


def test_playlist_delete_with_cascading_tracks(mem_db: Database, sample_tracks_list: List[Dict]):
    """Verify deleting a playlist removes it and cascades to all tracks."""
    pl_id = mem_db.create_playlist("Delete Me")
    mem_db.add_to_playlist(pl_id, sample_tracks_list[0])
    mem_db.add_to_playlist(pl_id, sample_tracks_list[1])
    assert len(mem_db.get_playlist_tracks(pl_id)) == 2

    assert mem_db.delete_playlist(pl_id) is True
    assert mem_db.get_playlist(pl_id) is None
    assert mem_db.get_playlist_tracks(pl_id) == []

    # Deleting non-existent returns False
    assert mem_db.delete_playlist(9999) is False


# ============================================================================
# 5. PLAYLIST TRACKS CRUD & ATOMIC REORDERING
# ============================================================================

def test_playlist_track_add_default_and_out_of_bounds(mem_db: Database, sample_tracks_list: List[Dict]):
    """Verify adding tracks at default, negative, and out-of-bounds positions."""
    pl_id = mem_db.create_playlist("Tracks Test")

    # Default position (end of list)
    assert mem_db.add_to_playlist(pl_id, sample_tracks_list[0]) is True
    assert mem_db.add_to_playlist(pl_id, sample_tracks_list[1]) is True
    assert [t["position"] for t in mem_db.get_playlist_tracks(pl_id)] == [0, 1]

    # Insert at position 0 (shifts 0 and 1 to 1 and 2)
    assert mem_db.add_to_playlist(pl_id, sample_tracks_list[2], position=0) is True
    tracks = mem_db.get_playlist_tracks(pl_id)
    assert len(tracks) == 3
    assert [t["video_id"] for t in tracks] == [sample_tracks_list[2]["id"], sample_tracks_list[0]["id"], sample_tracks_list[1]["id"]]
    assert [t["position"] for t in tracks] == [0, 1, 2]

    # Negative position clamps to 0
    assert mem_db.add_to_playlist(pl_id, sample_tracks_list[3], position=-5) is True
    tracks = mem_db.get_playlist_tracks(pl_id)
    assert tracks[0]["video_id"] == sample_tracks_list[3]["id"]
    assert [t["position"] for t in tracks] == [0, 1, 2, 3]

    # Position greater than count appends to end
    assert mem_db.add_to_playlist(pl_id, sample_tracks_list[4], position=999) is True
    tracks = mem_db.get_playlist_tracks(pl_id)
    assert tracks[-1]["video_id"] == sample_tracks_list[4]["id"]
    assert tracks[-1]["position"] == 4


def test_playlist_track_unique_constraint_rollback(mem_db: Database, sample_tracks_list: List[Dict]):
    """Verify adding duplicate track returns False and preserves contiguous positions."""
    pl_id = mem_db.create_playlist("Unique Test")
    mem_db.add_to_playlist(pl_id, sample_tracks_list[0])
    mem_db.add_to_playlist(pl_id, sample_tracks_list[1])

    # Attempt to re-add sample_tracks_list[0] at position 0
    added = mem_db.add_to_playlist(pl_id, sample_tracks_list[0], position=0)
    assert added is False

    # Invariants: 2 tracks remain, positions remain [0, 1]
    tracks = mem_db.get_playlist_tracks(pl_id)
    assert len(tracks) == 2
    assert [t["position"] for t in tracks] == [0, 1]


def test_playlist_batch_add_tracks(mem_db: Database, sample_tracks_list: List[Dict]):
    """Verify batch track insertion assigns contiguous positions and skips duplicates."""
    pl_id = mem_db.create_playlist("Batch Test")
    # Add initial track
    mem_db.add_to_playlist(pl_id, sample_tracks_list[0])

    # Batch add 5 tracks, including duplicate sample_tracks_list[0]
    count = mem_db.add_tracks_to_playlist(pl_id, sample_tracks_list[:5])
    assert count == 4  # 4 new tracks added

    tracks = mem_db.get_playlist_tracks(pl_id)
    assert len(tracks) == 5
    assert [t["position"] for t in tracks] == [0, 1, 2, 3, 4]


def test_playlist_remove_track_by_position(mem_db: Database, sample_tracks_list: List[Dict]):
    """Verify removing track by position shifts subsequent positions down contiguously."""
    pl_id = mem_db.create_playlist("Remove Pos Test")
    for trk in sample_tracks_list[:5]:
        mem_db.add_to_playlist(pl_id, trk)

    # Remove track at position 2
    assert mem_db.remove_from_playlist(pl_id, position=2) is True
    tracks = mem_db.get_playlist_tracks(pl_id)
    assert len(tracks) == 4
    assert [t["position"] for t in tracks] == [0, 1, 2, 3]
    assert [t["video_id"] for t in tracks] == [
        sample_tracks_list[0]["id"],
        sample_tracks_list[1]["id"],
        sample_tracks_list[3]["id"],
        sample_tracks_list[4]["id"]
    ]

    # Remove head (position 0)
    assert mem_db.remove_from_playlist(pl_id, position=0) is True
    tracks = mem_db.get_playlist_tracks(pl_id)
    assert [t["position"] for t in tracks] == [0, 1, 2]
    assert tracks[0]["video_id"] == sample_tracks_list[1]["id"]

    # Remove out of bounds position returns False
    assert mem_db.remove_from_playlist(pl_id, position=99) is False
    assert mem_db.remove_from_playlist(pl_id, position=-1) is False


def test_playlist_remove_track_by_video_id(mem_db: Database, sample_tracks_list: List[Dict]):
    """Verify removing track by video_id string (backward compatibility)."""
    pl_id = mem_db.create_playlist("Remove Vid Test")
    for trk in sample_tracks_list[:3]:
        mem_db.add_to_playlist(pl_id, trk)

    assert mem_db.remove_from_playlist(pl_id, sample_tracks_list[1]["id"]) is True
    tracks = mem_db.get_playlist_tracks(pl_id)
    assert len(tracks) == 2
    assert [t["video_id"] for t in tracks] == [sample_tracks_list[0]["id"], sample_tracks_list[2]["id"]]
    assert [t["position"] for t in tracks] == [0, 1]

    # Non-existent video_id returns False
    assert mem_db.remove_from_playlist(pl_id, "non_existent_vid") is False


def test_playlist_atomic_reorder_all_scenarios(mem_db: Database, sample_tracks_list: List[Dict]):
    """
    Verify single-statement atomic track reordering across:
    1. Head to tail (0 -> 4)
    2. Tail to head (4 -> 0)
    3. Adjacent forward (1 -> 2)
    4. Adjacent backward (2 -> 1)
    5. Same position (no-op)
    6. Boundary violations
    """
    pl_id = mem_db.create_playlist("Reorder Matrix")
    for trk in sample_tracks_list[:5]:
        mem_db.add_to_playlist(pl_id, trk)

    orig_ids = [t["id"] for t in sample_tracks_list[:5]]

    # 1. Head to tail (0 -> 4)
    assert mem_db.move_playlist_track(pl_id, from_pos=0, to_pos=4) is True
    tracks = mem_db.get_playlist_tracks(pl_id)
    assert [t["video_id"] for t in tracks] == [orig_ids[1], orig_ids[2], orig_ids[3], orig_ids[4], orig_ids[0]]
    assert [t["position"] for t in tracks] == [0, 1, 2, 3, 4]

    # 2. Tail to head (4 -> 0)
    assert mem_db.move_playlist_track(pl_id, from_pos=4, to_pos=0) is True
    tracks = mem_db.get_playlist_tracks(pl_id)
    assert [t["video_id"] for t in tracks] == orig_ids
    assert [t["position"] for t in tracks] == [0, 1, 2, 3, 4]

    # 3. Adjacent forward (1 -> 2)
    assert mem_db.move_playlist_track(pl_id, from_pos=1, to_pos=2) is True
    tracks = mem_db.get_playlist_tracks(pl_id)
    assert [t["video_id"] for t in tracks] == [orig_ids[0], orig_ids[2], orig_ids[1], orig_ids[3], orig_ids[4]]
    assert [t["position"] for t in tracks] == [0, 1, 2, 3, 4]

    # 4. Adjacent backward (2 -> 1)
    assert mem_db.move_playlist_track(pl_id, from_pos=2, to_pos=1) is True
    tracks = mem_db.get_playlist_tracks(pl_id)
    assert [t["video_id"] for t in tracks] == orig_ids

    # 5. Same position (no-op)
    assert mem_db.move_playlist_track(pl_id, from_pos=2, to_pos=2) is True
    tracks = mem_db.get_playlist_tracks(pl_id)
    assert [t["video_id"] for t in tracks] == orig_ids

    # 6. Boundary violations
    assert mem_db.move_playlist_track(pl_id, from_pos=-1, to_pos=2) is False
    assert mem_db.move_playlist_track(pl_id, from_pos=1, to_pos=10) is False
    assert mem_db.move_playlist_track(pl_id, from_pos=10, to_pos=1) is False
    assert mem_db.move_playlist_track(9999, from_pos=0, to_pos=1) is False


# ============================================================================
# 6. LIKED SONGS (FAVORITES) CRUD
# ============================================================================

def test_liked_crud_and_fast_lookup(mem_db: Database, sample_tracks_list: List[Dict]):
    """Verify Contract 1 dict-based liked operations and fast O(1) Set lookup."""
    t0 = sample_tracks_list[0]
    t1 = sample_tracks_list[1]

    assert mem_db.get_liked_ids() == set()
    assert mem_db.is_liked(t0["id"]) is False

    # Add liked
    assert mem_db.add_liked(t0) is True
    assert mem_db.is_liked(t0["id"]) is True
    assert mem_db.get_liked_ids() == {t0["id"]}

    # Re-adding returns False
    assert mem_db.add_liked(t0) is False

    # Add second track
    assert mem_db.add_liked(t1) is True
    liked_ids = mem_db.get_liked_ids()
    assert isinstance(liked_ids, set)
    assert liked_ids == {t0["id"], t1["id"]}

    # List liked songs
    liked = mem_db.get_liked_songs()
    assert len(liked) == 2
    assert liked[0]["id"] == t1["id"]  # ordered by added_at DESC

    # Remove liked
    assert mem_db.remove_liked(t0["id"]) is True
    assert mem_db.is_liked(t0["id"]) is False
    assert mem_db.get_liked_ids() == {t1["id"]}

    # Remove non-existent returns False
    assert mem_db.remove_liked("non_existent") is False


def test_liked_atomic_toggle(mem_db: Database, sample_tracks_list: List[Dict]):
    """Verify atomic toggle_liked method (True if liked, False if unliked)."""
    track = sample_tracks_list[0]

    # First toggle: liked -> True
    state1 = mem_db.toggle_liked(track)
    assert state1 is True
    assert mem_db.is_liked(track["id"]) is True

    # Second toggle: unliked -> False
    state2 = mem_db.toggle_liked(track)
    assert state2 is False
    assert mem_db.is_liked(track["id"]) is False


def test_liked_legacy_calling_convention(mem_db: Database):
    """Verify backward compatibility with legacy 6-argument positional call."""
    added = mem_db.add_liked(
        "leg_vid_01",
        "Legacy Title",
        "Legacy Artist",
        "03:45",
        225,
        "https://yt.com/leg"
    )
    assert added is True
    assert mem_db.is_liked("leg_vid_01") is True
    songs = mem_db.get_liked_songs()
    assert len(songs) == 1
    assert songs[0]["title"] == "Legacy Title"


# ============================================================================
# 7. PLAYBACK QUEUE & PLAYER STATE
# ============================================================================

def test_queue_persistence_full_lifecycle(mem_db: Database, sample_tracks_list: List[Dict]):
    """Verify saving, loading, appending, reordering, and clearing active queue."""
    queued = sample_tracks_list[:4]

    # 1. Save queue
    mem_db.save_queue(queued, current_index=2)
    saved = mem_db.get_queue()
    assert len(saved) == 4
    assert [t["position"] for t in saved] == [0, 1, 2, 3]
    assert [t["id"] for t in saved] == [t["id"] for t in queued]

    state = mem_db.get_player_state()
    assert state["queue_index"] == 2

    # 2. Add to queue
    new_trk = sample_tracks_list[4]
    new_pos = mem_db.add_to_queue(new_trk)
    assert new_pos == 4
    assert len(mem_db.get_queue()) == 5

    # 3. Move queue track (0 -> 3)
    assert mem_db.move_queue_track(0, 3) is True
    q_moved = mem_db.get_queue()
    assert q_moved[3]["id"] == queued[0]["id"]
    assert [t["position"] for t in q_moved] == [0, 1, 2, 3, 4]

    # 4. Remove from queue (position 1)
    assert mem_db.remove_from_queue(1) is True
    q_removed = mem_db.get_queue()
    assert len(q_removed) == 4
    assert [t["position"] for t in q_removed] == [0, 1, 2, 3]

    # 5. Clear queue
    mem_db.clear_queue()
    assert mem_db.get_queue() == []
    reset_state = mem_db.get_player_state()
    assert reset_state["queue_index"] == 0
    assert reset_state["current_track_id"] is None


def test_player_state_persistence(mem_db: Database):
    """Verify persisting and retrieving player playback state singleton."""
    # Initial state defaults
    default_state = mem_db.get_player_state()
    assert default_state["current_track_id"] is None
    assert default_state["queue_index"] == 0
    assert default_state["time_pos"] == 0.0
    assert default_state["volume"] == 80.0

    # Save state
    mem_db.save_player_state(
        current_track_id="trk_playing",
        queue_index=3,
        time_pos=145.2,
        volume=92.5
    )

    restored = mem_db.get_player_state()
    assert restored["current_track_id"] == "trk_playing"
    assert restored["queue_index"] == 3
    assert abs(restored["time_pos"] - 145.2) < 0.01
    assert abs(restored["volume"] - 92.5) < 0.01
    assert restored["updated_at"] is not None


# ============================================================================
# 8. HISTORY LOGGING & PRUNING
# ============================================================================

def test_history_logging_and_pruning(mem_db: Database):
    """Verify playback history logging and automatic pruning to max_history."""
    # Add tracks using dict format
    for i in range(25):
        mem_db.add_history(
            {"id": f"h_trk_{i:02d}", "title": f"History {i}", "artist": "Artist"},
            max_history=15
        )

    history = mem_db.get_history(limit=50)
    assert len(history) == 15
    # Most recently played track is first
    assert history[0]["id"] == "h_trk_24"
    assert history[-1]["id"] == "h_trk_10"

    # Verify clear history
    mem_db.clear_history()
    assert mem_db.get_history() == []


def test_history_legacy_calling_convention(mem_db: Database):
    """Verify backward compatibility with legacy positional add_history."""
    mem_db.add_history(
        "leg_h_01",
        "Legacy Song",
        "Legacy Artist",
        "02:45",
        165,
        "https://yt.com/h"
    )
    history = mem_db.get_history()
    assert len(history) == 1
    assert history[0]["id"] == "leg_h_01"
    assert history[0]["title"] == "Legacy Song"


# ============================================================================
# 9. MULTI-THREADED CONCURRENCY (WAL MODE)
# ============================================================================

def test_concurrent_readers_and_writers_wal(file_db: Database, sample_tracks_list: List[Dict]):
    """
    Stress test multi-threaded concurrency under WAL mode.
    Spawns concurrent writer and reader threads performing rapid operations.
    Guarantees no 'database is locked' operational errors occur.
    """
    errors: List[Exception] = []
    num_threads = 6
    ops_per_thread = 20

    def writer_task(thread_id: int):
        try:
            for i in range(ops_per_thread):
                pl_id = file_db.create_playlist(f"pl_th_{thread_id}_{i}")
                file_db.add_to_playlist(pl_id, sample_tracks_list[i % len(sample_tracks_list)])
                file_db.add_liked(sample_tracks_list[i % len(sample_tracks_list)])
        except Exception as e:
            errors.append(e)

    def reader_task(thread_id: int):
        try:
            for _ in range(ops_per_thread):
                _ = file_db.get_playlists()
                _ = file_db.get_liked_ids()
                _ = file_db.get_player_state()
        except Exception as e:
            errors.append(e)

    threads = [
        threading.Thread(target=writer_task, args=(i,), daemon=True)
        for i in range(num_threads)
    ] + [
        threading.Thread(target=reader_task, args=(i,), daemon=True)
        for i in range(num_threads)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert len(errors) == 0, f"Concurrency errors encountered: {errors}"
    assert len(file_db.get_playlists()) >= num_threads * ops_per_thread
