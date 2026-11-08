"""
Wave string and visual formatting utilities.
"""


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


def make_progress_bar(percent: float, width: int = 32) -> str:
    """Generate fluid ASCII progress bar without emojis."""
    percent = max(0.0, min(100.0, percent))
    filled = int((percent / 100.0) * width)
    if filled >= width:
        bar = "=" * width
    elif filled > 0:
        bar = "=" * (filled - 1) + ">" + "-" * (width - filled)
    else:
        bar = "-" * width
    return f"[{bar}]"


def make_vol_bar(vol: float, width: int = 10) -> str:
    """Generate ASCII volume bar."""
    vol = max(0.0, min(100.0, vol))
    filled = int((vol / 100.0) * width)
    return "[" + "|" * filled + "." * (width - filled) + f"] {int(vol)}%"
