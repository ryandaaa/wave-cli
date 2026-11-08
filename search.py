"""
Temporary backward-compatibility shim for search module.
Re-exports from wave.youtube and wave.util.format.
"""

from wave.util.format import format_duration
from wave.youtube import (
    ensure_yt_dlp,
    fetch_radio_mix,
    fetch_youtube_playlist,
    find_yt_dlp,
    is_playlist_url,
    search_youtube,
)

__all__ = [
    "format_duration",
    "find_yt_dlp",
    "ensure_yt_dlp",
    "is_playlist_url",
    "fetch_youtube_playlist",
    "search_youtube",
    "fetch_radio_mix",
]
