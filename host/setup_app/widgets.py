from __future__ import annotations

# Everything the two screens draw. Canvas-based rather than ttk, because the
# step list needs states ttk has no widget for and the window is the whole
# product on macOS -- it is the only thing a user sees before their first
# project runs.

import tkinter as tk

from . import theme

# The five statuses run_install reports, plus the one a row starts in.
GLYPHS = {"pending": "", "running": "", "done": "✓", "skipped": "✓",
          "failed": "✗", "reboot": "!"}


def format_elapsed(seconds: float) -> str:
    """Whole seconds, and nothing at all below one.

    A list of rows each claiming "0s" says less than a list of rows saying
    nothing, and the fast steps here really are instant.
    """
    whole = int(seconds)
    if whole < 1:
        return ""
    if whole < 60:
        return f"{whole}s"
    return f"{whole // 60}m {whole % 60:02d}s"


def _mapped_width(canvas: tk.Canvas, fallback: int = 520) -> int:
    """The canvas's width once Tk has actually mapped it.

    Tk reports 1, not 0, for a widget that hasn't been mapped yet -- so
    `winfo_width() or 520` lets a width of 1 straight through, and a row drawn
    at width 1 puts every right-aligned item at a negative x. Self-correcting
    on the next <Configure>, but only after one frame drawn off-canvas.
    """
    width = canvas.winfo_width()
    return width if width > 1 else fallback


def rounded(canvas: tk.Canvas, x1, y1, x2, y2, radius, **kwargs) -> int:
    """A rounded rectangle. Canvas has no such primitive, and a square-cornered
    card next to macOS's own chrome reads as a rendering failure."""
    points = [x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
              x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
              x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class Header(tk.Canvas):
    """The accent band across the top: the product's name, and one line saying
    what this window is doing."""

    HEIGHT = 84

    def __init__(self, parent, palette: theme.Palette, fonts, title: str, subtitle: str):
        super().__init__(parent, height=self.HEIGHT, highlightthickness=0,
                         bg=palette.accent)
        self._palette, self._fonts = palette, fonts
        self.create_text(theme.PAD, 26, text=title, anchor="w",
                         fill=palette.accent_text, font=fonts["title"])
        self._subtitle = self.create_text(
            theme.PAD, 58, text=subtitle, anchor="w",
            fill=palette.accent_text, font=fonts["small"])

    def say(self, subtitle: str) -> None:
        self.itemconfigure(self._subtitle, text=subtitle)


class StepList(tk.Canvas):
    """One row per install step: a glyph, a label, and how long it took.

    Redrawn whole on every change. The list is a dozen rows at most, and a
    partial redraw is how a step row ends up showing two states at once.
    """

    def __init__(self, parent, palette: theme.Palette, fonts, labels: list[tuple[str, str]]):
        super().__init__(parent, highlightthickness=0, bg=palette.bg,
                         height=theme.ROW_HEIGHT * len(labels) + 8)
        self._palette, self._fonts = palette, fonts
        self._labels = labels                       # [(step name, text)]
        self._state = {name: "pending" for name, _ in labels}
        self._elapsed = {name: 0.0 for name, _ in labels}
        self._spin = 0
        self.bind("<Configure>", lambda event: self.redraw())

    def set_state(self, name: str, state: str, elapsed: float = 0.0) -> None:
        if name in self._state:
            self._state[name] = state
            self._elapsed[name] = elapsed
            self.redraw()

    def tick(self) -> None:
        """Advance the running row's arc. Called on the window's timer."""
        self._spin = (self._spin + 30) % 360
        if "running" in self._state.values():
            self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        width = _mapped_width(self)
        for index, (name, text) in enumerate(self._labels):
            y = 12 + index * theme.ROW_HEIGHT
            state = self._state[name]
            self._glyph(theme.PAD + theme.GLYPH // 2, y + 8, state)
            colour = (self._palette.muted if state in ("pending", "skipped")
                      else self._palette.error if state == "failed"
                      else self._palette.text)
            self.create_text(theme.PAD + theme.GLYPH + 12, y + 8, text=text,
                             anchor="w", fill=colour, font=self._fonts["body"])
            elapsed = format_elapsed(self._elapsed[name])
            if elapsed:
                self.create_text(width - theme.PAD, y + 8, text=elapsed, anchor="e",
                                 fill=self._palette.muted, font=self._fonts["small"])

    def _glyph(self, cx: int, cy: int, state: str) -> None:
        radius = theme.GLYPH // 2
        box = (cx - radius, cy - radius, cx + radius, cy + radius)
        if state == "running":
            self.create_oval(*box, outline=self._palette.border, width=2)
            self.create_arc(*box, start=self._spin, extent=100, style="arc",
                            outline=self._palette.accent, width=2)
            return
        if state == "pending":
            self.create_oval(*box, outline=self._palette.border, width=2)
            return
        fill = {"done": self._palette.ok, "skipped": self._palette.muted,
                "failed": self._palette.error, "reboot": self._palette.accent}[state]
        self.create_oval(*box, fill=fill, outline=fill)
        self.create_text(cx, cy, text=GLYPHS[state], fill=self._palette.surface,
                         font=self._fonts["small"])


class ProgressBar(tk.Canvas):
    """Determinate, because every long step here can say how far along it is.

    The bar this replaces was indeterminate through a 391 MB download, which
    is the one moment a user most wants to know whether to wait."""

    HEIGHT = 6

    def __init__(self, parent, palette: theme.Palette):
        super().__init__(parent, height=self.HEIGHT, highlightthickness=0, bg=palette.bg)
        self._palette = palette
        self._value = 0.0
        self.bind("<Configure>", lambda event: self._draw())

    def set(self, value: float) -> None:
        self._value = max(0.0, min(1.0, value))
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        width = _mapped_width(self)
        self.create_rectangle(0, 0, width, self.HEIGHT,
                              fill=self._palette.border, outline="")
        if self._value > 0:
            self.create_rectangle(0, 0, width * self._value, self.HEIGHT,
                                  fill=self._palette.accent, outline="")


class Button(tk.Canvas):
    """A drawn button, in two weights. ttk's would not take the accent colour
    on macOS's aqua theme, which is the one place this app's look matters."""

    HEIGHT = 34

    def __init__(self, parent, palette: theme.Palette, fonts, text: str,
                 command, *, primary: bool = False, width: int = 150):
        super().__init__(parent, height=self.HEIGHT, width=width,
                         highlightthickness=0, bg=palette.bg)
        self._palette, self._fonts = palette, fonts
        self._text, self._command, self._primary = text, command, primary
        self._enabled = True
        self._draw(hover=False)
        self.bind("<Enter>", lambda e: self._enabled and self._draw(hover=True))
        self.bind("<Leave>", lambda e: self._enabled and self._draw(hover=False))
        self.bind("<Button-1>", lambda e: self._enabled and self._command())

    def enable(self, enabled: bool) -> None:
        self._enabled = enabled
        self._draw(hover=False)

    def set_text(self, text: str) -> None:
        """Change the label in place, e.g. Copy -> Copied.

        No-ops once the widget is gone: a caller may hold this Button past a
        deferred `after()` callback that fires after the window closed, and
        drawing on a destroyed canvas raises TclError rather than doing
        nothing the way a plain attribute set would.
        """
        if not self.winfo_exists():
            return
        self._text = text
        self._draw(hover=False)

    def _draw(self, *, hover: bool) -> None:
        self.delete("all")
        width = int(self["width"])
        if not self._enabled:
            fill, text_colour = self._palette.border, self._palette.muted
        elif self._primary:
            fill, text_colour = self._palette.accent, self._palette.accent_text
        else:
            fill, text_colour = self._palette.surface, self._palette.text
        rounded(self, 1, 1, width - 1, self.HEIGHT - 1, theme.RADIUS,
                fill=fill, outline=self._palette.border)
        if hover and self._enabled:
            rounded(self, 1, 1, width - 1, self.HEIGHT - 1, theme.RADIUS,
                    fill="", outline=self._palette.accent, width=2)
        self.create_text(width // 2, self.HEIGHT // 2, text=self._text,
                         fill=text_colour, font=self._fonts["body"])
        self.configure(cursor="hand2" if self._enabled else "")


class FieldRow(tk.Frame):
    """One label, one monospaced value, one Copy button.

    Read-only on purpose: the app never writes to the user's ~/.ssh/config.
    """

    def __init__(self, parent, palette: theme.Palette, fonts, label: str, value: str):
        super().__init__(parent, bg=palette.bg)
        self._value = value
        self._restore_id: str | None = None
        tk.Label(self, text=label, width=14, anchor="w", bg=palette.bg,
                 fg=palette.muted, font=fonts["small"]).pack(side="left")
        entry = tk.Entry(self, bg=palette.surface, fg=palette.text,
                         readonlybackground=palette.surface,
                         font=fonts["mono"], relief="flat",
                         highlightthickness=1, highlightbackground=palette.border)
        entry.insert(0, value)
        # Read-only rather than disabled: the text must stay selectable, so a
        # user can drag out one field without the Copy button at all.
        entry.configure(state="readonly")
        entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._copy = Button(self, palette, fonts, "Copy", self._on_copy, width=70)
        self._copy.pack(side="left")

    def _on_copy(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self._value)
        self._copy.set_text("Copied")
        self._restore_id = self.after(1200, self._restore)

    def _restore(self) -> None:
        if not self.winfo_exists():
            return
        self._copy.set_text("Copy")

    def destroy(self) -> None:
        # Same bug _Spinner.destroy was written to fix: Misc.destroy only
        # deletes the Tcl command behind this widget, it does not cancel a
        # pending after() -- so a row destroyed inside the 1.2s Copy/Copied
        # window (closing the status screen right after a click) fired
        # _restore against a command that no longer existed, and the
        # winfo_exists() guard in _restore could never run in time to stop it.
        if self._restore_id is not None:
            self.after_cancel(self._restore_id)
            self._restore_id = None
        super().destroy()
