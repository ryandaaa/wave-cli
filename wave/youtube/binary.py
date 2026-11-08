"""
yt-dlp binary detection and auto-provisioning.
"""

import os
import shutil
import sys


def find_yt_dlp() -> str:
    # 1. Check user local bin first, then system PATH
    user_bin = os.path.expanduser("~/.local/bin/yt-dlp")
    if os.path.isfile(user_bin) and os.access(user_bin, os.X_OK):
        return user_bin
    system_bin = shutil.which("yt-dlp")
    if system_bin:
        return system_bin
    data_bin = os.path.expanduser("~/.local/share/wave-cli/bin/yt-dlp")
    if os.path.isfile(data_bin) and os.access(data_bin, os.X_OK):
        return data_bin
    return "yt-dlp"


def ensure_yt_dlp() -> str:
    """Ensure yt-dlp is available, auto-download official standalone binary if missing."""
    found = find_yt_dlp()
    if found != "yt-dlp" or shutil.which("yt-dlp"):
        return found

    target_dir = os.path.expanduser("~/.local/bin")
    os.makedirs(target_dir, exist_ok=True)
    exe_name = "yt-dlp.exe" if sys.platform == "win32" else "yt-dlp"
    target_path = os.path.join(target_dir, exe_name)
    url = f"https://github.com/yt-dlp/yt-dlp/releases/latest/download/{exe_name}"

    try:
        import urllib.request
        urllib.request.urlretrieve(url, target_path)
        if sys.platform != "win32":
            os.chmod(target_path, 0o755)
        return target_path
    except Exception:
        return "yt-dlp"
