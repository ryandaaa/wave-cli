"""
Unit tests for direct YouTube Playlist Import and Interactive Confirmation.
"""

import pytest
from wave.youtube import is_playlist_url
from wave.tui import WaveApp
from wave.tui.modals import ImportPlaylistModal
from wave.db import Database


def test_is_playlist_url_detection():
    # Valid playlist URLs
    assert is_playlist_url("https://www.youtube.com/playlist?list=PLrAlq_h698vgq4fRia3H5xVpC5L-_e_W7") is True
    assert is_playlist_url("https://music.youtube.com/playlist?list=PLrAlq_h698vgq4fRia3H5xVpC5L-_e_W7") is True
    assert is_playlist_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLrAlq_h698vgq4fRia3H5xVpC5L-_e_W7") is True
    assert is_playlist_url("youtube.com/playlist?list=PL12345") is True

    # Invalid / plain video / general search
    assert is_playlist_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is False
    assert is_playlist_url("illenium all that really matters") is False
    assert is_playlist_url("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M") is False


@pytest.mark.asyncio
async def test_import_playlist_custom_name(tmp_path, monkeypatch):
    test_db_path = tmp_path / "test_import.db"
    db = Database(test_db_path)

    mock_tracks = [
        {"id": "v1", "title": "Track 1", "artist": "Artist 1", "duration": "03:30", "duration_sec": 210, "url": "https://youtu.be/v1"},
        {"id": "v2", "title": "Track 2", "artist": "Artist 2", "duration": "04:15", "duration_sec": 255, "url": "https://youtu.be/v2"},
    ]

    async def fake_fetch(url, limit=150):
        return "Original YouTube Title", mock_tracks

    monkeypatch.setattr("wave.tui.mixins.search.fetch_youtube_playlist", fake_fetch)

    app = WaveApp()
    app.db = db

    async with app.run_test() as pilot:
        await pilot.pause(0.1)
        worker = app.import_youtube_playlist("https://youtube.com/playlist?list=PL123", custom_name="Koleksi Santai")
        await worker.wait()
        await pilot.pause(0.2)

        playlists = db.get_playlists()
        assert len(playlists) == 1
        assert playlists[0]["name"] == "Koleksi Santai"
        assert playlists[0]["count"] == 2

        tracks = db.get_playlist_tracks(playlists[0]["id"])
        assert len(tracks) == 2
        assert tracks[0]["title"] == "Track 1"
        assert tracks[1]["title"] == "Track 2"

        # Current view should be updated directly to this playlist
        assert app.current_view == f"PLAYLIST:{playlists[0]['id']}"


@pytest.mark.asyncio
async def test_import_playlist_fallback_name(tmp_path, monkeypatch):
    test_db_path = tmp_path / "test_import_fallback.db"
    db = Database(test_db_path)

    mock_tracks = [
        {"id": "v3", "title": "Track 3", "artist": "Artist 3", "duration": "02:50", "duration_sec": 170, "url": "https://youtu.be/v3"}
    ]

    async def fake_fetch(url, limit=150):
        return "YouTube Best Hits", mock_tracks

    monkeypatch.setattr("wave.tui.mixins.search.fetch_youtube_playlist", fake_fetch)

    app = WaveApp()
    app.db = db

    async with app.run_test() as pilot:
        await pilot.pause(0.1)
        worker = app.import_youtube_playlist("https://youtube.com/playlist?list=PL456", custom_name="")
        await worker.wait()
        await pilot.pause(0.2)

        playlists = db.get_playlists()
        assert len(playlists) == 1
        assert playlists[0]["name"] == "YouTube Best Hits"
        assert playlists[0]["count"] == 1
