"""
Unit tests for Two-Tier Queue & Smart Radio Recommendations.
"""

import pytest
from wave.player import Player
from wave.youtube import fetch_radio_mix


def test_play_next_enqueue_priority():
    player = Player(sock_path="/tmp/test_priority.sock", volume=80.0, autoplay=True)
    player.send_command = lambda cmd: {"data": True}

    t_playing = {"id": "p0", "title": "Playing Now", "artist": "Artist 0"}
    t_q1 = {"id": "q1", "title": "Queue 1", "artist": "Artist 1"}
    t_q2 = {"id": "q2", "title": "Queue 2", "artist": "Artist 2"}
    t_next = {"id": "next1", "title": "Play Next Song", "artist": "Artist Next"}
    t_context = {"id": "c1", "title": "Playlist Next", "artist": "Artist Context"}
    t_radio = {"id": "r1", "title": "Radio Mix Song", "artist": "Artist Radio"}

    # Simulate active track
    player.is_playing = True
    player.current_track = t_playing
    player.session_played_ids.add("p0")

    # Regular queue appends
    player.add_to_queue(t_q1)
    player.add_to_queue(t_q2)
    assert len(player.queue) == 2

    # Play Next inserts at head (index 0)
    player.play_next_enqueue(t_next)
    assert len(player.queue) == 3
    assert player.queue[0]["id"] == "next1"
    assert player.queue[1]["id"] == "q1"
    assert player.queue[2]["id"] == "q2"

    # Context and Radio queues populated
    player.context_queue = [t_context]
    player.radio_queue = [t_radio]

    # Priority 1: Manual queue (t_next first, then t_q1, then t_q2)
    res1 = player.play_next()
    assert res1["id"] == "next1"
    res2 = player.play_next()
    assert res2["id"] == "q1"
    res3 = player.play_next()
    assert res3["id"] == "q2"

    # Priority 2: Context queue (t_context)
    res4 = player.play_next()
    assert res4["id"] == "c1"

    # Priority 3: Radio queue (t_radio)
    res5 = player.play_next()
    assert res5["id"] == "r1"

    # Priority 4: All queues empty -> player stops
    res6 = player.play_next()
    assert res6 is None
    assert player.is_playing is False


def test_autoplay_toggle():
    player = Player(sock_path="/tmp/test_toggle.sock", autoplay=True)
    player.send_command = lambda cmd: {"data": True}
    player.is_playing = True
    player.current_track = {"id": "x"}
    player.radio_queue = [{"id": "r"}]

    # When autoplay is True, picks from radio
    assert player.autoplay is True
    res = player.play_next()
    assert res["id"] == "r"

    # Toggle off
    player.toggle_autoplay()
    assert player.autoplay is False
    player.radio_queue = [{"id": "r2"}]
    # With autoplay False and no manual/context queue, it stops
    res2 = player.play_next()
    assert res2 is None
