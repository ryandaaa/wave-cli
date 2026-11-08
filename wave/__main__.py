"""
Wave-CLI package entrypoint.
Enables execution via `python -m wave`.
"""

import sys

try:
    from wave.cli import main
except ImportError:
    # Temporary fallback to root main.py before wave/cli.py is created in Step 8
    from main import main  # type: ignore[import-not-found]

if __name__ == "__main__":
    main()
