"""
YouTube playlist detection and extraction using yt-dlp.
"""

import asyncio
import json

from wave.util.format import format_duration
from wave.youtube.binary import find_yt_dlp


def is_playlist_url(query: str) -> bool:
    q = query.strip().lower()
    return ("list=" in q or "youtube.com/playlist" in q) and ("http://" in q or "https://" in q or "youtube.com" in q or "youtu.be" in q)


async def fetch_youtube_playlist(url: str, limit: int = 150) -> tuple:
    """
    Fetch tracks from a YouTube playlist URL.
    Returns (playlist_title: str, tracks: list[dict])
    """
    yt_dlp_path = find_yt_dlp()
    cmd = [
        yt_dlp_path,
        "--flat-playlist",
        "--dump-single-json",
        "--yes-playlist",
        "--playlist-end", str(limit),
        "--socket-timeout", "10",
        "--no-warnings",
        url.strip()
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0 or not stdout:
            return "YouTube Playlist", []

        data = json.loads(stdout.decode())
        pl_title = data.get("title") or "YouTube Playlist"
        entries = data.get("entries", [])
        results = []

        for entry in entries:
            if not entry:
                continue
            video_id = entry.get("id", "")
            title = entry.get("title", "Unknown Title")
            uploader = entry.get("uploader") or entry.get("channel") or "Unknown Artist"
            dur_sec = entry.get("duration") or 0
            dur_str = format_duration(dur_sec)
            video_url = f"https://www.youtube.com/watch?v={video_id}"

            results.append({
                "id": video_id,
                "title": title,
                "artist": uploader,
                "duration": dur_str,
                "duration_sec": int(dur_sec) if dur_sec else 0,
                "url": video_url
            })

        return pl_title, results
    except Exception:
        return "YouTube Playlist", []
