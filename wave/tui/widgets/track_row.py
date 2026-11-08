"""
TrackRow widget for displaying track items in lists.
"""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.content import Content
from textual.widgets import Button, Label

from wave.cache.audio_cache import is_track_cached


class TrackRow(Horizontal):
    def __init__(self, idx: int, track: dict, is_selected: bool = False, is_playing: bool = False, is_liked: bool = False, is_radio: bool = False):
        classes = "track-row"
        if is_selected:
            classes += " row-selected"
        if is_playing:
            classes += " row-playing"
        if is_radio:
            classes += " row-radio"
        super().__init__(classes=classes, id=f"row-{idx}")
        self.idx = idx
        self.track = track
        self.is_liked = is_liked
        self.is_playing = is_playing
        self.is_radio = is_radio

    def compose(self) -> ComposeResult:
        if self.is_radio:
            yield Label(" ~R", classes="row-num", markup=False)
        else:
            yield Label(f"{self.idx + 1:02d}", classes="row-num", markup=False)
        play_lbl = Content("[ || ]") if self.is_playing else Content("[ > ]")
        yield Button(play_lbl, id=f"btn-row-play-{self.idx}", classes="row-play-btn")

        # Combined title & artist in a single flat label for max compactness & zero lag
        title = self.track.get("title", "Unknown Title")
        artist = self.track.get("artist")
        if artist and artist != "Unknown Artist" and artist not in title:
            title_text = f"{title} - {artist}"
        else:
            title_text = title
        yield Label(title_text, classes="row-title", markup=False)

        yield Button(Content("[ +Next ]"), id=f"btn-row-next-{self.idx}", classes="row-action-btn")
        yield Button(Content("[ +Q ]"), id=f"btn-row-q-{self.idx}", classes="row-action-btn")
        yield Button(Content("[ +PL ]"), id=f"btn-row-pl-{self.idx}", classes="row-action-btn")
        fav_lbl = Content("[ Liked ]") if self.is_liked else Content("[ Fav ]")
        fav_cls = "row-action-btn row-fav-btn" + (" is-liked" if self.is_liked else "")
        yield Button(fav_lbl, id=f"btn-row-fav-{self.idx}", classes=fav_cls)

        is_cached = is_track_cached(self.track.get("id", ""))
        cache_lbl = "[v]" if is_cached else "   "
        cache_cls = "row-cache-indicator" + (" is-cached" if is_cached else "")
        yield Label(cache_lbl, id=f"lbl-row-cache-{self.idx}", classes=cache_cls, markup=False)

        dur = self.track.get("duration", "--:--")
        yield Label(dur, classes="row-duration", markup=False)
