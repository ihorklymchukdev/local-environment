from __future__ import annotations

# Colours, fonts and metrics for both screens.
#
# Nothing here asks which operating system it is on, and it must not start:
# light and dark are chosen from the ttk theme's own background, which the OS
# has already set correctly. That keeps dark mode working on both platforms and
# keeps tests/test_no_platform_leak.py passing.

from dataclasses import dataclass
from tkinter import font as tkfont


@dataclass(frozen=True)
class Palette:
    bg: str
    surface: str
    text: str
    muted: str
    accent: str
    accent_text: str
    ok: str
    error: str
    border: str


LIGHT = Palette(bg="#f6f6f7", surface="#ffffff", text="#16161a",
                muted="#6b6b76", accent="#c2571a", accent_text="#ffffff",
                ok="#2e7d4f", error="#b3261e", border="#dcdce1")

DARK = Palette(bg="#1c1c1f", surface="#26262b", text="#f2f2f4",
               muted="#a0a0ab", accent="#e2802f", accent_text="#1c1c1f",
               ok="#5cc98a", error="#ff8a80", border="#3a3a41")


def luminance(rgb16: tuple[int, int, int]) -> float:
    """Perceived brightness, 0.0-1.0, from tkinter's 16-bit channels.

    Weighted, not averaged: a flat mean calls macOS's graphite window chrome
    light and hands a light palette to a dark window.
    """
    red, green, blue = (channel / 65535 for channel in rgb16)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def palette_for(rgb16: tuple[int, int, int]) -> Palette:
    return DARK if luminance(rgb16) < 0.5 else LIGHT


def palette_for_root(root) -> Palette:
    """The palette matching the window the OS just gave us."""
    from tkinter import ttk
    background = ttk.Style(root).lookup("TFrame", "background") or "#ffffff"
    try:
        return palette_for(root.winfo_rgb(background))
    except Exception:
        return LIGHT


def load_fonts(root) -> dict[str, tkfont.Font]:
    """The system UI font at five sizes.

    Copies of the named fonts tkinter resolves per platform, never a family
    name of our own: every label in this app used to ask for "Segoe UI", which
    does not exist on macOS, so the whole window fell back to a default the
    layout was not measured against.
    """
    base = tkfont.nametofont("TkDefaultFont")
    size = base.cget("size") or 13
    def derived(delta: int, weight: str = "normal") -> tkfont.Font:
        made = base.copy()
        made.configure(size=size + delta, weight=weight)
        return made
    mono = tkfont.nametofont("TkFixedFont").copy()
    mono.configure(size=size - 1)
    return {"title": derived(7, "bold"), "heading": derived(2, "bold"),
            "body": derived(0), "small": derived(-1), "mono": mono}


PAD = 20            # window margin
ROW_HEIGHT = 30     # one step row
GLYPH = 22          # the circle at the left of a step row
RADIUS = 8          # card and button corner radius
