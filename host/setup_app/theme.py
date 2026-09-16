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


# accent/accent_text must clear WCAG AA (4.5:1) for normal text: the original
# "#c2571a" measured 4.49:1 against white, just under. "#b85319" is the same
# orange darkened enough to clear 4.5:1 (~4.9:1 measured) without reading as a
# different colour.
LIGHT = Palette(bg="#f6f6f7", surface="#ffffff", text="#16161a",
                muted="#6b6b76", accent="#b85319", accent_text="#ffffff",
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
    try:
        # Both the lookup and the RGB conversion can raise on an unusual ttk
        # theme; either failure should fall back to LIGHT, not surface as a
        # crash the no-Tk-root test policy can never exercise directly.
        background = ttk.Style(root).lookup("TFrame", "background") or "#ffffff"
        return palette_for(root.winfo_rgb(background))
    except Exception:
        return LIGHT


def derived_size(base_size: int, delta: int) -> int:
    """Move a tkinter font size by `delta`, independent of tkinter's own sign
    convention: a negative size means pixels, not points, which is a known
    pattern on Windows. Naive `base_size + delta` inverts every derived size
    when `base_size` is negative -- "title" (delta +7) comes out smaller than
    body instead of larger, and "small" (delta -1) comes out larger. Working
    in magnitude and restoring the sign keeps the delta's direction correct
    either way; flooring the magnitude at 1 stops a delta bigger than the
    base from flipping the sign it's supposed to preserve.
    """
    sign = -1 if base_size < 0 else 1
    magnitude = max(abs(base_size) + delta, 1)
    return sign * magnitude


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
        made.configure(size=derived_size(size, delta), weight=weight)
        return made
    mono = tkfont.nametofont("TkFixedFont").copy()
    mono.configure(size=derived_size(size, -1))
    return {"title": derived(7, "bold"), "heading": derived(2, "bold"),
            "body": derived(0), "small": derived(-1), "mono": mono}


PAD = 20            # window margin
ROW_HEIGHT = 30     # one step row
GLYPH = 22          # the circle at the left of a step row
RADIUS = 8          # card and button corner radius
