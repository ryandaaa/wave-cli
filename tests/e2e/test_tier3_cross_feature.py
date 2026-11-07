"""
Tier 3: Cross-Feature Combinations Test Suite for wave-cli.
Verifies multi-feature interactions, end-to-end data pipelines, and reactive synchronization:
- Search -> Play -> Like -> Add to Playlist -> Verify in Liked & Playlist -> Reorder -> Play from Queue
- Cross-View Liked Synchronization
- Playlist Lifecycle with Foreign Key Cascade Integrity
- Playback Queue & History Recording Pipeline
- Socket Error Recovery Loop
"""

import asyncio
import json
import os
import pathlib
import time
from typing import Any, Dict, List
import pytest

from database import Database
from player import Player

pytestmark = pytest.mark.tier3


def test_full_streaming_user_journey(db, db_adapter, mock_mpv_socket, sample_tracks):
    """
    Complete end-to-end user streaming cycle:
    1. Search results retrieved (sample_tracks)
    2. User plays Track 0
    3. User likes Track 0
    4. User creates playlist 'Synthwave Essentials'
    5. User adds Track 0 and Track 1 to playlist
    6. User verifies Track 0 in Liked songs
    7. User verifies playlist tracks
    8. User reorders playlist (moves Track 1 to pos 0)
    9. User enqueues Track 2
    10. User plays next from Queue -> Player transitions cleanly
    """
    # 1. Search tracks
    tracks = sample_tracks
    assert len(tracks) >= 3

    # 2. Player plays Track 0
    player = Player(sock_path=mock_mpv_socket.sock_path)
    assert player._connect_socket() is True
    player.play(tracks[0])
    assert player.is_playing is True
    assert player.current_track["id"] == "trk_001"
    assert mock_mpv_socket.loaded_file == tracks[0]["url"]

    # 3. User likes Track 0
    liked = db_adapter.add_liked(db, tracks[0])
    assert liked is True
    assert db.is_liked("trk_001") is True

    # 4. User creates playlist
    pl_id = db.create_playlist("Synthwave Essentials")
    assert pl_id is not None

    # 5. User adds Track 0 and Track 1 to playlist
    db.add_to_playlist(pl_id, tracks[0])
    db.add_to_playlist(pl_id, tracks[1])

    # 6. User verifies Track 0 in Liked songs
    liked_songs = db.get_liked_songs()
    assert any(s["id"] == "trk_001" for s in liked_songs)

    # 7. User verifies playlist tracks
    pl_tracks = db.get_playlist_tracks(pl_id)
    assert len(pl_tracks) == 2
    assert pl_tracks[0]["id"] == "trk_001"
    assert pl_tracks[1]["id"] == "trk_002"

    # 8. User reorders playlist (if move_playlist_track implemented)
    if hasattr(db, "move_playlist_track"):
        db.move_playlist_track(pl_id, from_pos=1, to_pos=0)
        reordered = db.get_playlist_tracks(pl_id)
        assert reordered[0]["id"] == "trk_002"
        assert reordered[1]["id"] == "trk_001"

    # 9. User enqueues Track 2
    player.add_to_queue(tracks[2])
    assert len(player.queue) == 1
    assert player.queue[0]["id"] == "trk_003"

    # 10. User plays next from Queue
    next_track = player.play_next()
    assert next_track["id"] == "trk_003"
    assert player.current_track["id"] == "trk_003"
    assert mock_mpv_socket.loaded_file == tracks[2]["url"]
    assert len(player.queue) == 0

    player.close()


def test_cross_view_liked_synchronization(db, db_adapter, sample_tracks):
    """
    Verify like status synchronization across disparate views (F28, F29):
    Search -> Liked view -> Queue view -> Player Bar -> Unlike
    """
    target = sample_tracks[1]
    video_id = target["id"]

    # Initially unliked
    assert db.is_liked(video_id) is False

    # Like from Search view
    if hasattr(db, "toggle_liked"):
        state = db.toggle_liked(target)
        assert state is True
    else:
        db_adapter.add_liked(db, target)

    assert db.is_liked(video_id) is True

    # Liked view should contain the song
    liked_list = db.get_liked_songs()
    assert any(s["id"] == video_id for s in liked_list)

    # Fast O(1) set lookup should contain the song (F05)
    if hasattr(db, "get_liked_ids"):
        liked_ids = db.get_liked_ids()
        assert video_id in liked_ids

    # Unlike from Player Bar / Queue view
    if hasattr(db, "toggle_liked"):
        state2 = db.toggle_liked(target)
        assert state2 is False
    else:
        db.remove_liked(video_id)

    assert db.is_liked(video_id) is False
    liked_list_after = db.get_liked_songs()
    assert not any(s["id"] == video_id for s in liked_list_after)


def test_playlist_full_lifecycle_cascade_integrity(db, sample_tracks):
    """
    Verify complete playlist lifecycle with foreign key cascade integrity:
    Create -> Populate -> Reorder -> Rename -> Remove track -> Delete playlist
    """
    # Create
    pl_id = db.create_playlist("Full Lifecycle Test")
    assert pl_id is not None

    # Populate 4 tracks
    for trk in sample_tracks[:4]:
        db.add_to_playlist(pl_id, trk)

    tracks = db.get_playlist_tracks(pl_id)
    assert len(tracks) == 4

    # Reorder (F03/F27)
    if hasattr(db, "move_playlist_track"):
        db.move_playlist_track(pl_id, from_pos=3, to_pos=1)
        tracks = db.get_playlist_tracks(pl_id)
        assert tracks[1]["id"] == sample_tracks[3]["id"]

    # Rename (F25)
    db.rename_playlist(pl_id, "Renamed Energy Mix")
    pl = db.get_playlist(pl_id)
    assert pl["name"] == "Renamed Energy Mix"

    # Remove track at index 0
    db.remove_from_playlist(pl_id, tracks[0]["id"])
    assert len(db.get_playlist_tracks(pl_id)) == 3

    # Delete playlist
    deleted = db.delete_playlist(pl_id)
    assert deleted is True

    # Confirm playlist is gone
    assert db.get_playlist(pl_id) is None
    # Confirm cascade deletion of tracks
    assert len(db.get_playlist_tracks(pl_id)) == 0


def test_playback_queue_and_history_lifecycle(db, db_adapter, mock_mpv_socket, sample_tracks):
    """
    Verify queue navigation, history recording, seeking, and queue clearing:
    Queue tracks -> Play -> Seek -> Volume -> Skip next -> Prev -> Clear
    """
    p = Player(sock_path=mock_mpv_socket.sock_path)
    assert p._connect_socket() is True

    # Start playback
    p.play(sample_tracks[0])
    db_adapter.add_history(db, sample_tracks[0])

    # Enqueue two tracks
    p.add_to_queue(sample_tracks[1])
    p.add_to_queue(sample_tracks[2])
    assert len(p.queue) == 2

    # Relative seek +15s
    p.seek(15.0)
    assert mock_mpv_socket.received_commands[-1] == ["seek", 15.0, "relative"]

    # Volume change
    p.set_volume(10.0)
    assert p.volume == 90.0

    # Advance track (play_next)
    next_trk = p.play_next()
    assert next_trk["id"] == sample_tracks[1]["id"]
    db_adapter.add_history(db, sample_tracks[1])
    assert len(p.queue) == 1

    # Play previous track
    prev_trk = p.play_previous()
    assert prev_trk is not None

    # Clear remaining queue
    p.queue.clear()
    assert len(p.queue) == 0

    # History verification
    history = db.get_history(limit=10)
    assert len(history) >= 2
    assert history[0]["id"] == sample_tracks[1]["id"]

    p.close()


def test_socket_failure_and_recovery_loop(tmp_path, sample_tracks):
    """
    Verify player handles socket disconnect, attempts command,
    and seamlessly reconnects when socket becomes available again.
    """
    sock_path = str(tmp_path / "recon_test.sock")
    p = Player(sock_path=sock_path)

    # Initial command fails cleanly without crash
    res = p.send_command(["get_property", "time-pos"])
    assert res is None

    # Now start server
    from tests.conftest import MockMpvServer
    server = MockMpvServer(sock_path)
    server.start()
    time.sleep(0.05)

    try:
        # Reconnect on command
        res2 = p.send_command(["get_property", "duration"])
        assert res2 is not None
        assert res2.get("error") == "success"
    finally:
        server.stop()
        p.close()
