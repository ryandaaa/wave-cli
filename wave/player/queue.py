"""
Wave MPV Player Queue Mixin.
Handles in-memory manual playback queue operations.
"""

from typing import Dict, Optional


class PlayerQueueMixin:
    def add_to_queue(self, track: Dict):
        """Add track to manual queue. If nothing is playing, play immediately."""
        if not self.is_playing or not self.current_track:
            self.play(track)
        else:
            self.queue.append(track)

    def play_next_enqueue(self, track: Dict):
        """Insert track as the next song to be played (at head of manual queue)."""
        if not self.is_playing or not self.current_track:
            self.play(track)
        else:
            self.queue.insert(0, track)

    def remove_from_queue(self, idx: int) -> Optional[Dict]:
        """Remove a track at index from the queue."""
        if 0 <= idx < len(self.queue):
            return self.queue.pop(idx)
        return None

    def clear_queue(self) -> None:
        """Clear all tracks from the queue."""
        self.queue.clear()

    def move_queue(self, from_idx: int, to_idx: int) -> bool:
        """Move a track in the queue from from_idx to to_idx."""
        if 0 <= from_idx < len(self.queue) and 0 <= to_idx < len(self.queue):
            track = self.queue.pop(from_idx)
            self.queue.insert(to_idx, track)
            return True
        return False


QueueMixin = PlayerQueueMixin

__all__ = ["PlayerQueueMixin", "QueueMixin"]
