"""
Wave-CLI MPV Player Controller
Shim module re-exporting Player from wave.player for backward compatibility.
Temporary shim per R3 Step 4; to be removed in Step 9.
"""

import sys
from wave.player import Player

sys.modules[__name__].Player = Player

__all__ = ["Player"]
