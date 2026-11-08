"""
YouTube search module using yt-dlp.
"""

import asyncio
import json

from wave.util.format import format_duration
from wave.youtube.binary import find_yt_dlp


async def search_youtube(query: str, limit: int = 15) -> list:
    """
    Search YouTube via yt-dlp --flat-playlist.
    Returns list of dicts: id, title, artist, duration, duration_sec, url
    """
    if not query.strip():
        return []

    yt_dlp_path = find_yt_dlp()
    cmd = [
        yt_dlp_path,
        "--flat-playlist",
        "--dump-single-json",
        "--default-search", f"ytsearch{limit}",
        "--socket-timeout", "10",
        "--no-warnings",
        query.strip()
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()

        if proc.returncode != 0 or not stdout:
            return []

        data = json.loads(stdout.decode())
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
            url = f"https://www.youtube.com/watch?v={video_id}"

            results.append({
                "id": video_id,
                "title": title,
                "artist": uploader,
                "duration": dur_str,
                "duration_sec": int(dur_sec) if dur_sec else 0,
                "url": url
            })

        return results
    except Exception as e:
        return []
