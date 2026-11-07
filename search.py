"""
YouTube search module using yt-dlp
"""

import asyncio
import json
import os
import shutil


def format_duration(seconds) -> str:
    if not seconds:
        return "--:--"
    try:
        sec = int(seconds)
        m, s = divmod(sec, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"
    except (ValueError, TypeError):
        return "--:--"


def find_yt_dlp() -> str:
    # Check user local bin first, then system PATH
    user_bin = os.path.expanduser("~/.local/bin/yt-dlp")
    if os.path.isfile(user_bin) and os.access(user_bin, os.X_OK):
        return user_bin
    system_bin = shutil.which("yt-dlp")
    if system_bin:
        return system_bin
    return "yt-dlp"


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
