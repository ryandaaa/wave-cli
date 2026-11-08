"""
WaveApp mixins package.
"""

from wave.tui.mixins.navigation import NavigationMixin
from wave.tui.mixins.sidebar import SidebarMixin
from wave.tui.mixins.tracklist import TracklistMixin
from wave.tui.mixins.search import SearchMixin
from wave.tui.mixins.playback import PlaybackMixin
from wave.tui.mixins.queue_ops import QueueOpsMixin
from wave.tui.mixins.likes import LikesMixin
from wave.tui.mixins.playlists import PlaylistsMixin
from wave.tui.mixins.modes import ModesMixin
from wave.tui.mixins.caching import CachingMixin
from wave.tui.mixins.buttons import ButtonsMixin
from wave.tui.mixins.ticker import TickerMixin

__all__ = [
    "NavigationMixin",
    "SidebarMixin",
    "TracklistMixin",
    "SearchMixin",
    "PlaybackMixin",
    "QueueOpsMixin",
    "LikesMixin",
    "PlaylistsMixin",
    "ModesMixin",
    "CachingMixin",
    "ButtonsMixin",
    "TickerMixin",
]
