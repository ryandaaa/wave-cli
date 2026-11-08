#!/usr/bin/env python3
"""
Wave-CLI Entrypoint
Spotify-Style Terminal Music Player for Linux
"""

import sys
import os
import argparse

# Ensure current project directory is in python sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tui import WaveApp
from search import ensure_yt_dlp

__version__ = "0.2.0"


def get_mpv_install_hint() -> str:
    """Return distro-specific install command for mpv."""
    if sys.platform == "darwin":
        return "brew install mpv"
    if sys.platform == "win32":
        return "winget install mpv.net  # atau: choco install mpv"

    # Linux distro detection
    os_release = "/etc/os-release"
    if os.path.isfile(os_release):
        try:
            with open(os_release, "r", encoding="utf-8") as f:
                content = f.read().lower()
            if any(d in content for d in ("ubuntu", "debian", "mint", "pop")):
                return "sudo apt update && sudo apt install -y mpv"
            if any(d in content for d in ("arch", "manjaro", "endeavouros")):
                return "sudo pacman -S mpv"
            if any(d in content for d in ("fedora", "rhel", "centos")):
                return "sudo dnf install -y mpv"
            if "opensuse" in content or "suse" in content:
                return "sudo zypper install -y mpv"
            if "void" in content:
                return "sudo xbps-install -S mpv"
            if "alpine" in content:
                return "sudo apk add mpv"
        except Exception:
            pass
    return "sudo apt install mpv  # atau gunakan package manager distro Anda"


def check_dependencies() -> bool:
    """Check required mpv dependency."""
    import shutil
    if not shutil.which("mpv"):
        hint = get_mpv_install_hint()
        print("=" * 62)
        print("[WAVE-CLI ERROR] Dependensi 'mpv' tidak ditemukan di sistem!")
        print("=" * 62)
        print("wave-cli membutuhkan 'mpv' sebagai audio engine untuk memutar musik.")
        print("\nSilakan pasang mpv dengan perintah berikut:\n")
        print(f"    {hint}\n")
        print("Setelah mpv terpasang, jalankan kembali perintah 'wave'.")
        print("=" * 62)
        return False
    return True


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="wave",
        description="Spotify-Style Zero-Flicker Terminal Music Player for Linux"
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"wave-cli v{__version__}"
    )
    parser.add_argument(
        "query",
        nargs="?",
        default="",
        help="Optional search query or playlist URL"
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    if not check_dependencies():
        sys.exit(1)

    # Ensure yt-dlp binary is available
    ensure_yt_dlp()

    app = WaveApp(initial_query=args.query)
    try:
        app.run()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        try:
            app.player.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
