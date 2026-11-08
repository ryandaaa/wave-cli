"""
Wave-CLI Offline Audio Cache Manager
Handles background downloading and local playback resolution using yt-dlp & Opus.
Standard storage: ~/.cache/wave-cli/audio/<video_id>.opus
"""

import asyncio
import os
import shutil
from typing import Dict, Optional, Set

try:
    from wave.youtube.binary import find_yt_dlp
except ImportError:
    from search import find_yt_dlp

CACHE_DIR = os.path.expanduser("~/.cache/wave-cli/audio")
_active_downloads: Set[str] = set()


def get_cache_dir() -> str:
    """Return the absolute path to the audio cache directory, creating it if needed."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    return CACHE_DIR


def get_cached_audio_path(video_id: str) -> Optional[str]:
    """Return absolute path to cached audio file if it exists and is valid (>50KB)."""
    if not video_id:
        return None
    file_path = os.path.join(CACHE_DIR, f"{video_id}.opus")
    if os.path.isfile(file_path):
        try:
            if os.path.getsize(file_path) > 50_000:
                return file_path
        except OSError:
            pass
    return None


def is_track_cached(video_id: str) -> bool:
    """Check if track audio is cached locally."""
    return get_cached_audio_path(video_id) is not None


def is_downloading(video_id: str) -> bool:
    """Check if track audio is currently being downloaded."""
    return video_id in _active_downloads


async def download_track_audio(track: Dict) -> bool:
    """
    Download a track's audio in background using yt-dlp to Opus.
    Non-blocking, idempotent, thread/coroutine-safe.
    """
    video_id = track.get("id")
    if not video_id:
        return False

    if is_track_cached(video_id):
        return True

    if video_id in _active_downloads:
        return False

    _active_downloads.add(video_id)
    cache_dir = get_cache_dir()
    output_template = os.path.join(cache_dir, f"{video_id}.%(ext)s")

    yt_dlp_path = find_yt_dlp()
    url = track.get("url") or f"https://www.youtube.com/watch?v={video_id}"

    cmd = [
        yt_dlp_path,
        "-f", "ba/b",
        "-x",
        "--audio-format", "opus",
        "--audio-quality", "0",
        "--no-warnings",
        "--socket-timeout", "15",
        "-o", output_template,
        url
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await proc.communicate()
        return is_track_cached(video_id)
    except Exception:
        return False
    finally:
        _active_downloads.discard(video_id)


def get_cache_size_bytes() -> int:
    """Get total size of audio cache in bytes."""
    total = 0
    if os.path.isdir(CACHE_DIR):
        for entry in os.scandir(CACHE_DIR):
            if entry.is_file():
                try:
                    total += entry.stat().st_size
                except OSError:
                    pass
    return total


def get_cache_size_str() -> str:
    """Return formatted human-readable cache size."""
    bytes_size = get_cache_size_bytes()
    mb = bytes_size / (1024 * 1024)
    if mb > 1024:
        return f"{mb / 1024:.2f} GB"
    return f"{mb:.1f} MB"


def clear_audio_cache() -> int:
    """Delete all cached audio files. Returns number of files removed."""
    count = 0
    if os.path.isdir(CACHE_DIR):
        for entry in os.scandir(CACHE_DIR):
            if entry.is_file():
                try:
                    os.unlink(entry.path)
                    count += 1
                except OSError:
                    pass
    return count
