"""
Wave MPV Player Controller.
Re-exports Player composed from IPC, playback, queue, modes, and status mixins.
"""

from wave.player.ipc import IpcMixin
from wave.player.modes import ModesMixin
from wave.player.playback import PlaybackMixin
from wave.player.queue import PlayerQueueMixin, QueueMixin
from wave.player.status import StatusMixin


class Player(IpcMixin, PlaybackMixin, QueueMixin, ModesMixin, StatusMixin):
    """
    MPV Player Controller via UNIX Domain Socket JSON IPC.
    Composed of modular mixins with 100% attribute and API backward compatibility.
    """
    pass


__all__ = [
    "Player",
    "IpcMixin",
    "PlaybackMixin",
    "QueueMixin",
    "PlayerQueueMixin",
    "ModesMixin",
    "StatusMixin",
]
