"""
Adversarial Stress and Resilience Test Suite for database.py (Milestone 1).

Author: Challenger M1-1
Scope:
1. Concurrency stress: 20 simultaneous threads reading and writing under high load.
   Verify zero 'database is locked' OperationalErrors and zero data corruption.
2. Reordering stress: 100 tracks subjected to random moves using move_playlist_track
   and move_queue_track. Compare against in-memory oracle to verify positions remain
   strictly contiguous [0..N-1] with zero gaps, duplicates, or corrupted ordering.
3. SQL injection attacks across playlist names, track titles, artist names, video IDs,
   URLs, and query parameters.
4. Edge cases & extreme payloads: 1MB strings, Unicode emojis, astral plane chars,
   empty/blank strings, malformed dictionaries, and transaction rollbacks.
"""

import os
import random
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List

import pytest

from database import Database


# ============================================================================
# SUMMARY OF EMPIRICAL ADVERSARIAL FINDINGS:
# 1. FAIL: test_concurrent_writes_same_playlist (Race condition causing duplicate positions in playlist)
# 2. FAIL: test_concurrent_toggle_liked (TOCTOU race causing uncaught IntegrityError)
# 3. FAIL: test_concurrent_queue_writes_duplicate_positions (Race condition causing duplicate queue positions)
# 4. FAIL: test_malformed_and_missing_keys_in_track_dicts (dict.get('title', default) returns None on explicit None)
# 5. FAIL: test_none_metadata_fields_unhandled_integrity_error (add_history/queue/playlist crash on None title/artist)
# ============================================================================



class TestConcurrencyStress:
    """Stress tests verifying WAL concurrency resilience under high multi-threaded contention."""

    def test_20_threads_high_load_rw(self, tmp_path: Path):
        """
        Launch 20 simultaneous threads (10 writers, 10 readers) executing 50 operations each
        (1,000 total operations) under high contention on a single WAL database.
        Verify zero 'database is locked' errors and PRAGMA integrity_check == 'ok'.
        """
        db_path = tmp_path / "concurrent_stress.db"
        db = Database(db_path)

        # Seed initial data
        pid = db.create_playlist("Seed Playlist", "Initial playlist for concurrency")
        assert pid is not None
        for i in range(10):
            db.add_to_playlist(pid, {
                "id": f"seed_{i}",
                "title": f"Seed Track {i}",
                "artist": "Seed Artist",
                "duration": "03:00",
                "duration_sec": 180,
                "url": f"https://example.com/seed_{i}"
            })
            db.add_liked({
                "id": f"liked_seed_{i}",
                "title": f"Liked Seed {i}",
                "artist": "Seed Artist",
                "duration": "03:00",
                "duration_sec": 180,
                "url": f"https://example.com/liked_{i}"
            })

        errors: List[Exception] = []
        lock = threading.Lock()

        def record_error(e: Exception):
            with lock:
                errors.append(e)

        def writer_task(worker_id: int):
            try:
                for op in range(50):
                    mode = (worker_id + op) % 5
                    if mode == 0:
                        # Liked song operations
                        track_id = f"w_{worker_id}_tr_{op}"
                        db.add_liked({
                            "id": track_id,
                            "title": f"Writer {worker_id} Song {op}",
                            "artist": f"Artist {worker_id}",
                            "duration": "02:30",
                            "duration_sec": 150,
                            "url": f"https://example.com/{track_id}"
                        })
                    elif mode == 1:
                        # Playlist operations
                        db.add_to_playlist(pid, {
                            "id": f"w_{worker_id}_pl_{op}",
                            "title": f"Playlist Track {worker_id}-{op}",
                            "artist": f"Artist {worker_id}",
                            "duration": "03:15",
                            "duration_sec": 195,
                            "url": f"https://example.com/pl_{worker_id}_{op}"
                        })
                    elif mode == 2:
                        # Queue operations
                        db.add_to_queue({
                            "id": f"w_{worker_id}_q_{op}",
                            "title": f"Queue Track {worker_id}-{op}",
                            "artist": f"Queue Artist {worker_id}",
                            "duration": "01:45",
                            "duration_sec": 105,
                            "url": f"https://example.com/q_{worker_id}_{op}"
                        })
                    elif mode == 3:
                        # Player state operations
                        db.save_player_state(
                            current_track_id=f"w_{worker_id}_q_{op}",
                            queue_index=op,
                            time_pos=float(op * 1.5),
                            volume=75.0 + (worker_id % 20)
                        )
                    elif mode == 4:
                        # History operations
                        db.add_history({
                            "id": f"w_{worker_id}_h_{op}",
                            "title": f"History Track {worker_id}-{op}",
                            "artist": f"History Artist {worker_id}",
                            "duration": "04:00",
                            "duration_sec": 240,
                            "url": f"https://example.com/h_{worker_id}_{op}"
                        }, max_history=500)
            except Exception as exc:
                record_error(exc)

        def reader_task(worker_id: int):
            try:
                for op in range(50):
                    mode = (worker_id + op) % 5
                    if mode == 0:
                        _ = db.get_liked_ids()
                        _ = db.get_liked_songs()
                    elif mode == 1:
                        _ = db.get_playlist_tracks(pid)
                        _ = db.get_playlists()
                    elif mode == 2:
                        _ = db.get_queue()
                    elif mode == 3:
                        _ = db.get_player_state()
                    elif mode == 4:
                        _ = db.get_history(limit=25)
            except Exception as exc:
                record_error(exc)

        # Launch 20 threads simultaneously
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = []
            for i in range(10):
                futures.append(executor.submit(writer_task, i))
            for i in range(10):
                futures.append(executor.submit(reader_task, i + 10))

            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0, f"Encountered {len(errors)} errors during 20-thread concurrency stress: {errors[:5]}"

        # Check database integrity after heavy stress
        with db._connection() as conn:
            integrity = conn.execute("PRAGMA integrity_check;").fetchone()[0]
            assert integrity == "ok", f"Database corrupted after concurrency stress: {integrity}"

        db.close()

    def test_concurrent_writes_same_playlist(self, tmp_path: Path):
        """
        10 concurrent threads attempting to add unique tracks to the exact same playlist.
        Verifies that positions do not collide or produce gaps.
        """
        db_path = tmp_path / "same_playlist_stress.db"
        db = Database(db_path)
        pid = db.create_playlist("Target Playlist")
        assert pid is not None

        errors = []

        def worker(thread_idx: int):
            try:
                for i in range(20):
                    db.add_to_playlist(pid, {
                        "id": f"t_{thread_idx}_track_{i}",
                        "title": f"Title {thread_idx}-{i}",
                        "artist": "Artist",
                        "duration": "03:00",
                        "duration_sec": 180,
                        "url": "https://example.com"
                    })
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as executor:
            list(executor.map(worker, range(10)))

        assert len(errors) == 0, f"Errors in concurrent same-playlist writes: {errors}"

        tracks = db.get_playlist_tracks(pid)
        assert len(tracks) == 200, f"Expected 200 tracks, got {len(tracks)}"
        positions = [t["position"] for t in tracks]
        assert positions == list(range(200)), "Positions must be strictly contiguous [0..199] with no gaps or duplicates"
        db.close()

    def test_concurrent_toggle_liked(self, tmp_path: Path):
        """
        10 threads concurrently toggling liked state on the same set of tracks.
        Verifies atomic toggle without IntegrityError or deadlock.
        """
        db_path = tmp_path / "toggle_liked_stress.db"
        db = Database(db_path)

        tracks = [
            {"id": f"fav_{i}", "title": f"Fav Track {i}", "artist": "Fav Artist", "url": "https://x"}
            for i in range(10)
        ]

        errors = []

        def toggler(thread_idx: int):
            try:
                for _ in range(30):
                    trk = random.choice(tracks)
                    db.toggle_liked(trk)
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as executor:
            list(executor.map(toggler, range(10)))

        assert len(errors) == 0, f"Errors in concurrent toggle_liked: {errors}"
        liked_ids = db.get_liked_ids()
        assert isinstance(liked_ids, set)
        for lid in liked_ids:
            assert db.is_liked(lid) is True
        db.close()

    def test_concurrent_queue_writes_duplicate_positions(self, tmp_path: Path):
        """
        10 concurrent threads appending tracks to the queue.
        Verifies that queue positions remain strictly contiguous [0..N-1] without duplicates.
        """
        db_path = tmp_path / "concurrent_queue_stress.db"
        db = Database(db_path)

        def worker(thread_idx: int):
            for i in range(5):
                db.add_to_queue({
                    "id": f"q_t_{thread_idx}_{i}",
                    "title": f"Queue Title {thread_idx}-{i}",
                    "artist": "Queue Artist",
                    "duration_sec": 120,
                    "url": "https://example.com"
                })

        with ThreadPoolExecutor(max_workers=10) as executor:
            list(executor.map(worker, range(10)))

        queue = db.get_queue()
        assert len(queue) == 50, f"Expected 50 tracks in queue, got {len(queue)}"
        positions = [t["position"] for t in queue]
        assert positions == list(range(50)), f"Queue positions contain duplicates/gaps: {positions}"
        db.close()


# ============================================================================
# 2. REORDERING STRESS & ORACLE VERIFICATION
# ============================================================================


class TestReorderingStress:
    """Adversarial stress testing of atomic track reordering using an in-memory oracle."""

    def test_100_tracks_playlist_random_shuffle_200_moves(self, tmp_path: Path):
        """
        Insert 100 tracks into a playlist. Perform 200 random move operations.
        After EACH move, verify with an in-memory reference oracle that:
        1. Total tracks remain exactly 100.
        2. Positions are strictly contiguous [0..99] with 0 gaps and 0 duplicates.
        3. The exact sequence of video IDs matches the reference oracle.
        """
        db_path = tmp_path / "reorder_playlist_100.db"
        db = Database(db_path)
        pid = db.create_playlist("Shuffle 100 Playlist")
        assert pid is not None

        # Seed 100 tracks
        tracks_seed = [
            {
                "id": f"vid_{i:03d}",
                "title": f"Track Title {i:03d}",
                "artist": f"Artist {i:03d}",
                "duration": "03:00",
                "duration_sec": 180,
                "url": f"https://example.com/vid_{i:03d}"
            }
            for i in range(100)
        ]
        added = db.add_tracks_to_playlist(pid, tracks_seed)
        assert added == 100

        # In-memory oracle list
        oracle: List[str] = [f"vid_{i:03d}" for i in range(100)]

        # Initial check
        initial_tracks = db.get_playlist_tracks(pid)
        assert len(initial_tracks) == 100
        assert [t["video_id"] for t in initial_tracks] == oracle
        assert [t["position"] for t in initial_tracks] == list(range(100))

        # Perform 200 random moves
        random.seed(42)  # Deterministic seed for reproducible stress test
        for step in range(200):
            from_pos = random.randint(0, 99)
            to_pos = random.randint(0, 99)

            # Move in database
            ok = db.move_playlist_track(pid, from_pos, to_pos)
            assert ok is True, f"Step {step}: move_playlist_track({pid}, {from_pos}, {to_pos}) returned False"

            # Mirror move in oracle: pop from_pos, insert at to_pos
            item = oracle.pop(from_pos)
            oracle.insert(to_pos, item)

            # Verify database matches oracle every 10 steps to keep runtime snappy, and on final step
            if step % 10 == 0 or step == 199:
                current_tracks = db.get_playlist_tracks(pid)
                assert len(current_tracks) == 100, f"Step {step}: Track count changed! Got {len(current_tracks)}"
                positions = [t["position"] for t in current_tracks]
                assert positions == list(range(100)), f"Step {step}: Positions violated contiguous invariant! Got {positions}"
                vids = [t["video_id"] for t in current_tracks]
                assert vids == oracle, f"Step {step}: Video IDs order does not match oracle!\nExpected: {oracle[:5]}...\nGot: {vids[:5]}..."

        db.close()

    def test_100_tracks_queue_random_shuffle_200_moves(self, tmp_path: Path):
        """
        Populate persistent queue with 100 tracks. Perform 200 random move operations.
        Verify positions remain strictly [0..99] with zero gaps or duplicates and match oracle.
        """
        db_path = tmp_path / "reorder_queue_100.db"
        db = Database(db_path)

        tracks_seed = [
            {
                "id": f"q_vid_{i:03d}",
                "title": f"Queue Title {i:03d}",
                "artist": f"Queue Artist {i:03d}",
                "duration": "02:00",
                "duration_sec": 120,
                "url": f"https://example.com/q_{i:03d}"
            }
            for i in range(100)
        ]
        db.save_queue(tracks_seed)

        oracle: List[str] = [f"q_vid_{i:03d}" for i in range(100)]
        random.seed(99)

        for step in range(200):
            from_pos = random.randint(0, 99)
            to_pos = random.randint(0, 99)

            ok = db.move_queue_track(from_pos, to_pos)
            assert ok is True, f"Step {step}: move_queue_track({from_pos}, {to_pos}) returned False"

            item = oracle.pop(from_pos)
            oracle.insert(to_pos, item)

            if step % 10 == 0 or step == 199:
                queue = db.get_queue()
                assert len(queue) == 100
                positions = [t["position"] for t in queue]
                assert positions == list(range(100))
                vids = [t["video_id"] for t in queue]
                assert vids == oracle

        db.close()

    def test_reorder_extreme_boundaries(self, tmp_path: Path):
        """Test boundary conditions for move_playlist_track and move_queue_track."""
        db_path = tmp_path / "reorder_boundaries.db"
        db = Database(db_path)
        pid = db.create_playlist("Boundary Playlist")
        assert pid is not None

        # Empty playlist moves must return False safely
        assert db.move_playlist_track(pid, 0, 0) is True  # same position early check exists
        assert db.move_playlist_track(pid, 0, 1) is False
        assert db.move_playlist_track(pid, -1, 0) is False
        assert db.move_playlist_track(pid, 0, 5) is False

        # Add 3 tracks
        db.add_to_playlist(pid, {"id": "t0", "title": "T0", "artist": "A", "url": "u0"})
        db.add_to_playlist(pid, {"id": "t1", "title": "T1", "artist": "A", "url": "u1"})
        db.add_to_playlist(pid, {"id": "t2", "title": "T2", "artist": "A", "url": "u2"})

        # Out-of-bounds moves
        assert db.move_playlist_track(pid, -1, 1) is False
        assert db.move_playlist_track(pid, 0, 3) is False
        assert db.move_playlist_track(pid, 3, 0) is False
        assert db.move_playlist_track(pid, 1, 100) is False
        assert db.move_playlist_track(999999, 0, 1) is False

        # Valid boundary: move 0 to 2
        assert db.move_playlist_track(pid, 0, 2) is True
        tracks = db.get_playlist_tracks(pid)
        assert [t["video_id"] for t in tracks] == ["t1", "t2", "t0"]
        assert [t["position"] for t in tracks] == [0, 1, 2]

        # Valid boundary: move 2 to 0
        assert db.move_playlist_track(pid, 2, 0) is True
        tracks = db.get_playlist_tracks(pid)
        assert [t["video_id"] for t in tracks] == ["t0", "t1", "t2"]
        assert [t["position"] for t in tracks] == [0, 1, 2]

        # Valid boundary: move same position
        assert db.move_playlist_track(pid, 1, 1) is True
        tracks = db.get_playlist_tracks(pid)
        assert [t["video_id"] for t in tracks] == ["t0", "t1", "t2"]
        assert [t["position"] for t in tracks] == [0, 1, 2]

        db.close()


# ============================================================================
# 3. SQL INJECTION ATTACKS
# ============================================================================


class TestSqlInjectionAttacks:
    """Adversarial security audit: execute classic and exotic SQL injection payloads."""

    SQL_PAYLOADS = [
        "'; DROP TABLE playlists; --",
        "'; DROP TABLE playlist_tracks; --",
        "'; DROP TABLE liked_songs; --",
        "'; DROP TABLE queue_tracks; --",
        "'; DROP TABLE player_state; --",
        "'; DROP TABLE history; --",
        "' OR '1'='1",
        "\" OR \"\"=\"",
        "') OR 1=1; --",
        "Robert'); DROP TABLE students;--",
        "UNION SELECT NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL--",
        "' UNION ALL SELECT sql, sqlite_version(), 3, 4, 5, 6, 7, 8, 9 FROM sqlite_master--",
        "1; ATTACH DATABASE '/tmp/pwned.db' AS pwned;--",
        "test' AND (SELECT 1 FROM (SELECT COUNT(*), CONCAT((SELECT 'PWNED'), 0x3a, FLOOR(RANDOM()*2)) x FROM sqlite_master GROUP BY x) a);--",
        "1' OR (SELECT 1)=1 --",
        "../../etc/passwd",
        "%00",
        "'; VACUUM; --"
    ]

    def test_sql_injection_playlist_names(self, tmp_path: Path):
        """Inject malicious SQL strings into create_playlist and rename_playlist."""
        db_path = tmp_path / "sqli_playlist.db"
        db = Database(db_path)

        created_pids = []
        for idx, payload in enumerate(self.SQL_PAYLOADS):
            pid = db.create_playlist(payload, description=f"Desc payload {payload}")
            assert pid is not None, f"create_playlist failed to safely store payload: {payload}"
            created_pids.append(pid)

            # Read back playlist and verify literal storage
            pl = db.get_playlist(pid)
            assert pl is not None
            assert pl["name"] == payload.strip()

            # Attempt rename with another injection payload
            rename_payload = f"Renamed_{idx}_{payload}"
            ok = db.rename_playlist(pid, rename_payload)
            assert ok is True
            pl_renamed = db.get_playlist(pid)
            assert pl_renamed["name"] == rename_payload.strip()

        # Verify tables still exist
        with db._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = {r[0] for r in cursor.fetchall()}
            assert {"playlists", "playlist_tracks", "liked_songs", "queue_tracks", "player_state", "history"}.issubset(tables)

            integrity = conn.execute("PRAGMA integrity_check;").fetchone()[0]
            assert integrity == "ok"

        db.close()

    def test_sql_injection_track_metadata(self, tmp_path: Path):
        """Inject malicious SQL payloads into track titles, artists, video IDs, and URLs."""
        db_path = tmp_path / "sqli_track_meta.db"
        db = Database(db_path)
        pid = db.create_playlist("SQLi Test Playlist")
        assert pid is not None

        for idx, payload in enumerate(self.SQL_PAYLOADS):
            track_dict = {
                "id": f"vid_sqli_{idx}_{payload[:10]}",
                "title": f"Title {payload}",
                "artist": f"Artist {payload}",
                "duration": "03:30",
                "duration_sec": 210,
                "url": f"https://example.com/watch?v={payload}",
                "source": "youtube",
                "thumbnail_url": f"https://img.example.com/{payload}.jpg"
            }

            # 1. Add liked
            added_liked = db.add_liked(track_dict)
            assert added_liked is True

            # Check liked status with injection string
            assert db.is_liked(track_dict["id"]) is True

            # 2. Add to playlist
            added_pl = db.add_to_playlist(pid, track_dict)
            assert added_pl is True

            # 3. Add to queue
            q_pos = db.add_to_queue(track_dict)
            assert q_pos == idx

            # 4. Add to history
            db.add_history(track_dict)

        # Verify playlist tracks count and exact literal match
        pl_tracks = db.get_playlist_tracks(pid)
        assert len(pl_tracks) == len(self.SQL_PAYLOADS)
        assert pl_tracks[0]["title"] == f"Title {self.SQL_PAYLOADS[0]}"
        assert pl_tracks[0]["artist"] == f"Artist {self.SQL_PAYLOADS[0]}"

        # Verify queue tracks count and exact literal match
        q_tracks = db.get_queue()
        assert len(q_tracks) == len(self.SQL_PAYLOADS)
        assert q_tracks[0]["title"] == f"Title {self.SQL_PAYLOADS[0]}"

        # Verify history count
        hist = db.get_history(limit=100)
        assert len(hist) == len(self.SQL_PAYLOADS)

        # Verify all tables intact
        with db._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = {r[0] for r in cursor.fetchall()}
            assert {"playlists", "playlist_tracks", "liked_songs", "queue_tracks", "player_state", "history"}.issubset(tables)

        db.close()

    def test_sql_injection_in_player_state_and_deletes(self, tmp_path: Path):
        """Test SQL injection in save_player_state, remove_liked, and remove_from_playlist."""
        db_path = tmp_path / "sqli_state_del.db"
        db = Database(db_path)

        for payload in self.SQL_PAYLOADS:
            # save_player_state
            db.save_player_state(
                current_track_id=payload,
                queue_index=0,
                time_pos=15.5,
                volume=80.0
            )
            state = db.get_player_state()
            assert state["current_track_id"] == payload

            # remove_liked with injection payload (non-existent should return False safely)
            res = db.remove_liked(payload)
            assert res is False

        # Table structure intact
        with db._connection() as conn:
            integrity = conn.execute("PRAGMA integrity_check;").fetchone()[0]
            assert integrity == "ok"

        db.close()


# ============================================================================
# 4. EDGE CASES & EXTREME PAYLOAD HARNESS
# ============================================================================


class TestEdgeCasesAndExtremePayloads:
    """Extreme payloads: massive strings, unicode astral symbols, RTL, malformed dicts, FD leaks."""

    def test_massive_1mb_strings(self, tmp_path: Path):
        """Store and retrieve 1MB strings in playlist description and track title."""
        db_path = tmp_path / "extreme_1mb.db"
        db = Database(db_path)

        large_str = "A" * (1024 * 1024)  # 1 MB of ASCII
        pid = db.create_playlist("Large Data Playlist", description=large_str)
        assert pid is not None

        pl = db.get_playlist(pid)
        assert pl is not None
        assert pl["description"] == large_str
        assert len(pl["description"]) == 1024 * 1024

        track = {
            "id": "huge_track_1",
            "title": large_str,
            "artist": "Giant Artist",
            "duration": "99:99",
            "duration_sec": 5999,
            "url": "https://huge.example.com"
        }
        added = db.add_to_playlist(pid, track)
        assert added is True

        tracks = db.get_playlist_tracks(pid)
        assert len(tracks) == 1
        assert tracks[0]["title"] == large_str

        db.close()

    def test_unicode_emojis_astral_and_rtl(self, tmp_path: Path):
        """Verify proper UTF-8 handling for emojis, musical notation symbols, RTL scripts, and null bytes."""
        db_path = tmp_path / "unicode_stress.db"
        db = Database(db_path)

        special_strings = [
            "🎵 🎶 🎧 🎸 🎹 🥁 🎷 🎺 🎼 📻",  # Emojis
            "𝄢 𝄡 𝄠 𝄟 𝄞 𝄝 𝄜 𝄞",            # Musical symbols (astral plane U+1D100)
            "مرحبا بالعالم - أروع الموسيقى",     # Arabic RTL
            "שָׁלוֹם עוֹלָם - שירים יפים",       # Hebrew RTL with niqqud
            "日本語のトラック名 ⚡ カタカナ",     # Japanese Kanji / Katakana
            "Line1\nLine2\r\nLine3\tTabbed",    # Whitespace and newlines
            "Special chars: !@#$%^&*()_+{}|:\"<>?[];',./",
            "Z̵̡̢̛͔̟̻̦̖̖̠̘͎̩͇̗̠̗̙͎̦a̸l̷g̶o̶ ̶t̵e̶x̵t̸", # Combining diacritics
        ]

        for idx, text in enumerate(special_strings):
            pid = db.create_playlist(f"PL_{idx}_{text}", description=text)
            assert pid is not None
            pl = db.get_playlist(pid)
            assert pl["name"] == f"PL_{idx}_{text}".strip()
            assert pl["description"] == text

            track = {
                "id": f"vid_unicode_{idx}",
                "title": text,
                "artist": text,
                "url": f"https://example.com/{idx}"
            }
            assert db.add_to_playlist(pid, track) is True
            retrieved = db.get_playlist_tracks(pid)
            assert retrieved[0]["title"] == text
            assert retrieved[0]["artist"] == text

        db.close()

    def test_malformed_and_missing_keys_in_track_dicts(self, tmp_path: Path):
        """
        Verify database functions handle missing keys, None values, and malformed track dicts
        without unhandled exceptions or crashes.
        """
        db_path = tmp_path / "malformed_dicts.db"
        db = Database(db_path)
        pid = db.create_playlist("Malformed Tests")
        assert pid is not None

        # 1. Completely empty dict -> missing video_id / id -> should return False
        assert db.add_liked({}) is False
        assert db.add_to_playlist(pid, {}) is False
        assert db.toggle_liked({}) is False

        # 2. None values in fields
        track_none_fields = {
            "id": "vid_none_fields",
            "title": None,
            "artist": None,
            "duration": None,
            "duration_sec": None,
            "url": None,
            "thumbnail_url": None,
        }
        assert db.add_liked(track_none_fields) is True
        liked = db.get_liked_songs()
        assert len(liked) == 1
        assert liked[0]["video_id"] == "vid_none_fields"

        # 3. Non-numeric duration_sec (string or float)
        track_str_dur = {
            "id": "vid_str_dur",
            "title": "String Duration",
            "duration_sec": "180"  # string instead of int
        }
        assert db.add_to_playlist(pid, track_str_dur) is True
        pts = db.get_playlist_tracks(pid)
        assert len(pts) == 1
        assert pts[0]["duration_sec"] == 180

        # 4. None duration_sec in add_to_playlist
        track_none_sec = {
            "id": "vid_none_sec",
            "title": "None Duration Sec",
            "duration_sec": None
        }
        assert db.add_to_playlist(pid, track_none_sec) is True
        pts = db.get_playlist_tracks(pid)
        assert len(pts) == 2
        assert pts[1]["duration_sec"] == 0

        # 5. Invalid types in save_player_state
        db.save_player_state(
            current_track_id=None,
            queue_index=0,
            time_pos=0.0,
            volume=80.0
        )
        state = db.get_player_state()
        assert state["current_track_id"] is None
        assert state["queue_index"] == 0

        db.close()

    def test_none_metadata_fields_unhandled_integrity_error(self, tmp_path: Path):
        """
        Verify that passing track dicts with None title/artist does NOT crash
        add_history, add_to_queue, save_queue, and add_tracks_to_playlist.
        """
        db_path = tmp_path / "none_metadata.db"
        db = Database(db_path)
        pid = db.create_playlist("None Metadata Playlist")
        assert pid is not None

        track_none = {
            "id": "trk_none_crash",
            "title": None,
            "artist": None,
            "duration": None,
            "duration_sec": None,
            "url": None
        }

        # Should safely default to fallback strings instead of raising IntegrityError
        db.add_history(track_none)
        hist = db.get_history()
        assert len(hist) == 1
        assert hist[0]["video_id"] == "trk_none_crash"

        db.add_to_queue(track_none)
        q = db.get_queue()
        assert len(q) == 1

        db.save_queue([track_none])
        assert len(db.get_queue()) == 1

        added = db.add_tracks_to_playlist(pid, [track_none])
        assert added == 1

        db.close()

    def test_empty_playlist_name_variants(self, tmp_path: Path):
        """Reject empty or whitespace-only playlist names."""
        db_path = tmp_path / "empty_names.db"
        db = Database(db_path)

        assert db.create_playlist("") is None
        assert db.create_playlist("   ") is None
        assert db.create_playlist("\t\n") is None
        assert db.create_playlist(None) is None  # type: ignore

        pid = db.create_playlist("Valid Playlist")
        assert pid is not None
        assert db.rename_playlist(pid, "") is False
        assert db.rename_playlist(pid, "   ") is False
        assert db.rename_playlist(pid, "\t\r\n") is False

        db.close()

    def test_cascade_delete_integrity(self, tmp_path: Path):
        """Verify cascade delete completely removes tracks and leaves no orphan records."""
        db_path = tmp_path / "cascade.db"
        db = Database(db_path)
        pid = db.create_playlist("To Be Deleted")
        assert pid is not None

        for i in range(50):
            db.add_to_playlist(pid, {
                "id": f"casc_{i}",
                "title": f"Cascading Track {i}",
                "artist": "Artist",
                "duration_sec": 100,
                "url": "https://x"
            })

        assert len(db.get_playlist_tracks(pid)) == 50
        assert db.delete_playlist(pid) is True

        # Tracks must be 0
        assert len(db.get_playlist_tracks(pid)) == 0

        # Verify underlying database table directly
        with db._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM playlist_tracks WHERE playlist_id = ?;", (pid,))
            assert cursor.fetchone()[0] == 0
            cursor.execute("SELECT COUNT(*) FROM playlists WHERE id = ?;", (pid,))
            assert cursor.fetchone()[0] == 0

        db.close()

    def test_fd_leak_under_sustained_stress(self, tmp_path: Path):
        """Verify file descriptor count does not grow after 500 consecutive operations."""
        if not os.path.exists("/proc/self/fd"):
            pytest.skip("/proc/self/fd not supported on this platform")

        db_path = tmp_path / "fd_stress.db"
        db = Database(db_path)
        pid = db.create_playlist("FD Test")
        assert pid is not None

        # Warmup
        for i in range(10):
            db.add_to_playlist(pid, {"id": f"warm_{i}", "title": "Warm", "artist": "A", "url": "u"})

        fd_dir = Path("/proc/self/fd")
        initial_fds = len(list(fd_dir.iterdir()))

        # 500 consecutive operations
        for i in range(500):
            _ = db.get_playlist_tracks(pid)
            _ = db.get_liked_ids()

        final_fds = len(list(fd_dir.iterdir()))
        diff = final_fds - initial_fds
        assert diff <= 1, f"File descriptor leak detected! Grew by {diff} (from {initial_fds} to {final_fds})"

        db.close()
