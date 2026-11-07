#!/usr/bin/env python3
"""
Wave-CLI Entrypoint
Spotify-Style Terminal Music Player for Linux
"""

import sys
import os

# Ensure current project directory is in python sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tui import WaveApp


def main():
    app = WaveApp()
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
