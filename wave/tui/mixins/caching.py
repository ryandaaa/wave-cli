"""
Background offline audio cache download mixin for WaveApp.
"""
from typing import Dict, List

from textual import work

from wave.cache.audio_cache import download_track_audio, is_track_cached

class CachingMixin:

    async def _auto_cache_track(self, track: Dict):
        """Silently download audio in background when liked or added to playlist."""
        vid_id = track.get("id")
        if not vid_id or is_track_cached(vid_id):
            return
        success = await download_track_audio(track)
        if success:
            self._update_row_cache_states(vid_id)

    @work(exclusive=True, group="batch_download", thread=False)
    async def _download_tracks_batch(self, tracks: List[Dict], container_name: str):
        """Batch sequential background download with live notification and indicator update."""
        to_download = [t for t in tracks if t.get("id") and not is_track_cached(t.get("id"))]
        total = len(to_download)
        if total == 0:
            self.notify(f"[{container_name.upper()}] Semua lagu sudah ter-download offline!", timeout=3.0)
            return

        self.notify(f"[{container_name.upper()}] Memulai download {total} lagu di background...", timeout=3.0)
        done = 0
        for track in to_download:
            vid_id = track.get("id")
            ok = await download_track_audio(track)
            if ok:
                done += 1
                self._update_row_cache_states(vid_id)
        self.notify(f"[{container_name.upper()}] Selesai! {done}/{total} lagu tersimpan di cache offline.", timeout=4.0)
