"""
Wave MPV Player Modes Mixin.
Handles repeat mode cycling, shuffle toggling, and autoplay state.
"""

import random


class ModesMixin:
    def toggle_repeat(self) -> str:
        """Cycle repeat mode: OFF -> ALL -> ONE -> OFF."""
        if self.repeat_mode == "OFF":
            self.repeat_mode = "ALL"
        elif self.repeat_mode == "ALL":
            self.repeat_mode = "ONE"
        else:
            self.repeat_mode = "OFF"
        return self.repeat_mode

    def toggle_shuffle(self) -> bool:
        """Toggle shuffle mode. Randomizes upcoming context queue if enabled."""
        self.shuffle = not self.shuffle
        if self.shuffle and self.context_queue:
            random.shuffle(self.context_queue)
        elif not self.shuffle and self.full_context_list and self.current_track:
            cur_id = self.current_track.get("id")
            found = False
            rest = []
            for t in self.full_context_list:
                if found:
                    rest.append(t)
                elif t.get("id") == cur_id:
                    found = True
            if rest:
                self.context_queue = rest
        return self.shuffle

    def toggle_autoplay(self) -> bool:
        """Toggle autoplay/radio state."""
        self.autoplay = not self.autoplay
        return self.autoplay


__all__ = ["ModesMixin"]
