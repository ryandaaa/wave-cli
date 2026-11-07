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

__version__ = "0.2.0"


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
