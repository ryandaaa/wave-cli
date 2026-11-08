"""
Wave-CLI: Spotify-Style Terminal Music Player (Textual TUI)
Backward-compatibility shim re-exporting WaveApp, TrackRow, modals, and format utilities.
Temporary shim per R3 Step 5-7; to be removed in Step 9.
"""

import sys
import types
from typing import Any

from wave.cache.audio_cache import download_track_audio, is_track_cached
from wave.db import Database
from wave.player import Player
from wave.tui import WaveApp
from wave.tui.modals import (
    ConfirmModal,
    ImportPlaylistModal,
    NewPlaylistModal,
    PlaylistSelectModal,
    RenamePlaylistModal,
)
from wave.tui.textual_patches import (
    _orig_blank_init,
    _orig_style_init,
    _patched_blank_init,
    _patched_style_init,
    apply_textual_patches,
)
from wave.tui.widgets import TrackRow
from wave.util.format import format_duration, make_progress_bar, make_vol_bar
from wave.youtube import (
    ensure_yt_dlp,
    fetch_radio_mix,
    fetch_youtube_playlist,
    find_yt_dlp,
    is_playlist_url,
    search_youtube,
)


class _TuiCompatibilityModule(types.ModuleType):
    """Delegates test monkeypatching (e.g. tui.fetch_youtube_playlist) to active mixins."""

    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        if name in ("fetch_youtube_playlist", "search_youtube", "fetch_radio_mix", "is_playlist_url"):
            try:
                import wave.tui.mixins.search as _sm
                setattr(_sm, name, value)
            except (ImportError, AttributeError):
                pass
            try:
                import wave.youtube as _wy
                setattr(_wy, name, value)
            except (ImportError, AttributeError):
                pass


sys.modules[__name__].__class__ = _TuiCompatibilityModule

__all__ = [
    "WaveApp",
    "TrackRow",
    "NewPlaylistModal",
    "PlaylistSelectModal",
    "RenamePlaylistModal",
    "ConfirmModal",
    "ImportPlaylistModal",
    "make_progress_bar",
    "make_vol_bar",
    "format_duration",
    "fetch_youtube_playlist",
    "search_youtube",
    "is_playlist_url",
    "fetch_radio_mix",
    "find_yt_dlp",
    "ensure_yt_dlp",
    "is_track_cached",
    "download_track_audio",
    "Database",
    "Player",
    "_orig_blank_init",
    "_patched_blank_init",
    "_orig_style_init",
    "_patched_style_init",
    "apply_textual_patches",
]
