"""
Wave-CLI Offline Audio Cache Manager
Shim module re-exporting from wave.cache.audio_cache for backward compatibility.
Temporary shim per R3 Step 2; to be removed in Step 9.
"""

import sys
from wave.cache.audio_cache import *
import wave.cache.audio_cache as _audio_cache

# Direct sys.modules alias ensures test monkeypatching (e.g.
# monkeypatch.setattr("audio_cache.CACHE_DIR", ...)) directly
# alters the active variable in wave.cache.audio_cache.
sys.modules[__name__] = _audio_cache
