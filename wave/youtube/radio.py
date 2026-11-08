"""
YouTube radio recommendation mix fetching using yt-dlp.
"""

import asyncio
import json

from wave.util.format import format_duration
from wave.youtube.binary import find_yt_dlp
from wave.youtube.search import search_youtube


async def fetch_radio_mix(video_id: str, artist: str = "", title: str = "", limit: int = 15) -> list:
    """
    Fetch algorithmic radio recommendation tracks for a given track/video_id.
    Uses YouTube Radio Mix endpoint (list=RD<video_id>) with ytsearch fallback.
    """
    if not video_id:
        return []

    yt_dlp_path = find_yt_dlp()
    url = f"https://www.youtube.com/watch?v={video_id}&list=RD{video_id}"
    cmd = [
        yt_dlp_path,
        "--flat-playlist",
        "--dump-single-json",
        "--playlist-end", str(limit + 5),
        "--socket-timeout", "10",
        "--no-warnings",
        url
    ]

    results = []
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0 and stdout:
            data = json.loads(stdout.decode())
            entries = data.get("entries", [])
            for entry in entries:
                if not entry:
                    continue
                v_id = entry.get("id", "")
                if not v_id or v_id == video_id:
                    continue
                t_title = entry.get("title", "Unknown Title")
                uploader = entry.get("uploader") or entry.get("channel") or "Unknown Artist"
                dur_sec = entry.get("duration") or 0
                results.append({
                    "id": v_id,
                    "title": t_title,
                    "artist": uploader,
                    "duration": format_duration(dur_sec),
                    "duration_sec": int(dur_sec) if dur_sec else 0,
                    "url": f"https://www.youtube.com/watch?v={v_id}"
                })
    except Exception:
        pass

    # Fallback to search query if radio mix was empty
    if len(results) < 3 and (artist or title):
        query = f"{artist} {title}".strip() or artist or title
        fallback_results = await search_youtube(f"{query} mix", limit=limit)
        for r in fallback_results:
            if r.get("id") != video_id and not any(x["id"] == r["id"] for x in results):
                results.append(r)

    return results[:limit]
