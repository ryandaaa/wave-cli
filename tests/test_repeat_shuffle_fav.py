"""
Unit tests for Fav Now Playing, Repeat Modes (ONE, ALL), and Shuffle.
"""

import pytest
from player import Player
from database import Database
from tui import WaveApp


def test_toggle_repeat_cycle():
    player = Player(sock_path="/tmp/test_rep.sock")
    assert player.repeat_mode == "OFF"

    assert player.toggle_repeat() == "ALL"
    assert player.repeat_mode == "ALL"

    assert player.toggle_repeat() == "ONE"
    assert player.repeat_mode == "ONE"

    assert player.toggle_repeat() == "OFF"
    assert player.repeat_mode == "OFF"


def test_repeat_one_behavior():
    player = Player(sock_path="/tmp/test_rep_one.sock", repeat_mode="ONE")
    player.send_command = lambda cmd: {"data": True}

    t1 = {"id": "song_1", "title": "Song 1"}
    t2 = {"id": "song_2", "title": "Song 2"}

    player.is_playing = True
    player.current_track = t1
    player.context_queue = [t2]

    # When EOF occurs with repeat_mode="ONE", it MUST replay the same track
    res_eof = player.play_next(is_eof=True)
    assert res_eof["id"] == "song_1"
    assert player.current_track["id"] == "song_1"
    assert len(player.context_queue) == 1

    # When user manually clicks next (is_eof=False), it MUST skip to next track
    res_manual = player.play_next(is_eof=False)
    assert res_manual["id"] == "song_2"
    assert player.current_track["id"] == "song_2"
    assert len(player.context_queue) == 0


def test_repeat_all_playlist_loop():
    player = Player(sock_path="/tmp/test_rep_all.sock", repeat_mode="ALL")
    player.send_command = lambda cmd: {"data": True}

    t1 = {"id": "s1", "title": "Song 1"}
    t2 = {"id": "s2", "title": "Song 2"}
    t3 = {"id": "s3", "title": "Song 3"}

    playlist = [t1, t2, t3]
    player.full_context_list = list(playlist)
    player.context_queue = [t2, t3]
    player.is_playing = True
    player.current_track = t1

    # Play t2
    res2 = player.play_next()
    assert res2["id"] == "s2"

    # Play t3 (last in upcoming queue)
    res3 = player.play_next()
    assert res3["id"] == "s3"
    assert len(player.context_queue) == 0

    # With repeat_mode="ALL", the next play MUST loop back to start of playlist (t1)
    res_loop = player.play_next()
    assert res_loop is not None
    assert res_loop["id"] == "s1"
    assert len(player.context_queue) == 2  # remaining are t2, t3


def test_toggle_shuffle():
    player = Player(sock_path="/tmp/test_shuf.sock")
    assert player.shuffle is False

    t_list = [{"id": f"s{i}", "title": f"Song {i}"} for i in range(20)]
    player.full_context_list = list(t_list)
    player.context_queue = list(t_list[1:])
    player.current_track = t_list[0]

    # Toggle shuffle ON
    assert player.toggle_shuffle() is True
    assert player.shuffle is True
    assert len(player.context_queue) == 19

    # Toggle shuffle OFF
    assert player.toggle_shuffle() is False
    assert player.shuffle is False
    # Should restore original sequence order
    assert [t["id"] for t in player.context_queue] == [f"s{i}" for i in range(1, 20)]


def test_player_state_persistence_repeat_shuffle(tmp_path):
    db_path = tmp_path / "test_state_rs.db"
    db = Database(db_path)

    # Save state with repeat_mode="ONE" and shuffle=True
    db.save_player_state(
        current_track_id="test_vid",
        queue_index=0,
        time_pos=12.5,
        volume=95.0,
        autoplay=False,
        repeat_mode="ONE",
        shuffle=True
    )

    state = db.get_player_state()
    assert state["volume"] == 95.0
    assert state["autoplay"] is False
    assert state["repeat_mode"] == "ONE"
    assert state["shuffle"] is True


@pytest.mark.asyncio
async def test_fav_now_playing_tui(tmp_path):
    db_path = tmp_path / "test_fav_tui.db"
    db = Database(db_path)

    app = WaveApp()
    app.db = db

    test_track = {"id": "fav_test_vid", "title": "Fav Test Song", "artist": "Artist", "duration": "03:00", "duration_sec": 180, "url": "https://youtu.be/fav"}
    app.player.current_track = test_track
    app.player.is_playing = True

    async with app.run_test() as pilot:
        await pilot.pause(0.1)

        assert db.is_liked("fav_test_vid") is False

        # Trigger fav now playing
        app.action_toggle_like_now_playing()
        await pilot.pause(0.2)

        assert db.is_liked("fav_test_vid") is True
        liked = db.get_liked_songs()
        assert len(liked) == 1
        assert liked[0]["id"] == "fav_test_vid"

        # Toggle again -> should remove
        app.action_toggle_like_now_playing()
        await pilot.pause(0.2)
        assert db.is_liked("fav_test_vid") is False
