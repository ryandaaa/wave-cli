"""
Root transparency patches for Textual Blank renderer and Style backgrounds.
Intercepts Blank and Style so transparent containers and text
never emit black ANSI background codes (#000000).
"""

from rich.style import Style as RichStyle
from textual import style
from textual.color import Color
from textual.renderables import blank

# ---------------- ROOT TRANSPARENCY PATCH ----------------
# 1. Intercept Textual's Blank renderer so transparent containers never emit black (#000000)
_orig_blank_init = blank.Blank.__init__


def _patched_blank_init(self, color="transparent"):
    if isinstance(color, str):
        c = Color.parse(color)
    elif isinstance(color, Color):
        c = color
    else:
        c = Color(0, 0, 0, a=0)

    if c.a == 0 or getattr(c, "is_transparent", False):
        self._rich_style = RichStyle()  # Pure transparent! No background ANSI code!
    else:
        _orig_blank_init(self, color)


# 2. Intercept Style.__init__ so any transparent background (alpha=0) becomes None
# This prevents Textual from converting transparent Color(0,0,0,0) into Rich '#000000' on labels & text!
_orig_style_init = style.Style.__init__


def _patched_style_init(self, *args, **kwargs):
    args = list(args)
    if args:
        bg = args[0]
        if bg is not None and getattr(bg, "a", 1.0) == 0:
            args[0] = None
    elif "background" in kwargs:
        bg = kwargs["background"]
        if bg is not None and getattr(bg, "a", 1.0) == 0:
            kwargs["background"] = None
    _orig_style_init(self, *args, **kwargs)


_patches_applied = False


def apply_textual_patches() -> None:
    """Apply root transparency patches to Textual Blank and Style."""
    global _patches_applied
    if _patches_applied:
        return
    blank.Blank.__init__ = _patched_blank_init
    style.Style.__init__ = _patched_style_init
    _patches_applied = True


# Apply patches immediately on import to preserve 100% identical behavior
apply_textual_patches()

__all__ = [
    "_orig_blank_init",
    "_patched_blank_init",
    "_orig_style_init",
    "_patched_style_init",
    "apply_textual_patches",
]
