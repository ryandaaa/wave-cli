"""
Wave-CLI Database Subsystem.
Modular SQLite persistence layer organized via composable mixins.
"""

from .connection import ConnectionMixin
from .schema import SchemaMixin
from .liked import LikedMixin
from .playlists import PlaylistsMixin
from .queue import QueueMixin
from .state import StateMixin
from .history import HistoryMixin


class Database(
    ConnectionMixin,
    SchemaMixin,
    LikedMixin,
    PlaylistsMixin,
    QueueMixin,
    StateMixin,
    HistoryMixin,
):
    """Production-grade SQLite database manager for wave-cli."""
    pass


__all__ = [
    "Database",
    "ConnectionMixin",
    "SchemaMixin",
    "LikedMixin",
    "PlaylistsMixin",
    "QueueMixin",
    "StateMixin",
    "HistoryMixin",
]
