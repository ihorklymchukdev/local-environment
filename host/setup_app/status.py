from __future__ import annotations

# The screen the app opens on. It answers two questions -- is this machine set
# up, and how does my coding agent get inside the VM -- and it renders an
# Access value without knowing what SSH is.

import tkinter as tk

from host.core import constants
from host.core.provider import Access
from host.core.status import Readiness

from . import theme, widgets


def summarize(readiness: Readiness) -> tuple[str, str]:
    """A headline and one line under it. Never a status code, never a
    traceback: this is the first thing a user reads."""
    if readiness.ready:
        return ("Ready",
                f"Omelet {readiness.engine_version} is running in the virtual machine.")
    if not readiness.vm_exists:
        return ("Not set up yet",
                "Set up Omelet to create the virtual machine and install it."
                + (f"\n{readiness.problem}" if readiness.problem else ""))
    if not readiness.vm_reachable:
        return ("The virtual machine is not running",
                "Run setup again to start it."
                + (f"\n{readiness.problem}" if readiness.problem else ""))
    if not readiness.engine_version:
        return ("Omelet is not installed in the virtual machine",
                "The virtual machine is there, but nothing is installed inside "
                "it yet. Run setup again."
                + (f"\n{readiness.problem}" if readiness.problem else ""))
    if readiness.agent_api not in constants.SUPPORTED_API:
        if readiness.agent_api is None:
            return ("The Omelet service is not answering",
                    "The virtual machine is running, but the service inside it "
                    "did not respond. Run setup again."
                    + (f"\n{readiness.problem}" if readiness.problem else ""))
        return ("Versions do not match",
                "This app and the Omelet service inside the virtual machine are "
                f"versions that cannot work together (service API "
                f"{readiness.agent_api}, this app speaks "
                f"{', '.join(str(n) for n in sorted(constants.SUPPORTED_API))}).")
    return ("Not ready", readiness.problem or "Run setup again.")


def diagnostics_text(readiness: Readiness, access: Access | None, *,
                     version: str, log: tuple[str, ...] = ()) -> str:
    """The text behind Copy diagnostics.

    install.py's failure messages have told users to press this button since
    the installer was written, and no such button existed. It carries facts and
    paths -- never a token, and never the contents of a key file.
    """
    lines = [f"omelet {version}", ""]
    for name in ("vm_exists", "vm_reachable", "engine_version", "agent_api", "problem"):
        lines.append(f"{name}: {getattr(readiness, name)!r}")
    if access is not None:
        lines += ["", f"command: {access.command}"]
        lines += [f"{field.label}: {field.value}" for field in access.fields]
        if access.note:
            lines.append(f"note: {access.note}")
    if log:
        lines += ["", "--- setup log ---", *log]
    return "\n".join(lines) + "\n"


def show_access_panel(access: Access | None) -> bool:
    """Whether the access panel belongs on screen at all.

    Not gated on `readiness.ready`: the Lima fallback in `LimaProvider.access`
    exists precisely so this screen shows something true even before the
    first boot (`lima._PORT_UNCONFIRMED`) or when the VM exists but the engine
    never finished installing -- both states `ready` excludes by definition,
    which used to make that fallback text, and the note steering a user to
    "run setup, then open this window again", unreachable from here. A user
    whose VM exists but whose engine install failed was left with no route in
    at all, not even the `ssh`/`wsl` command that would let them look.
    """
    return access is not None


class StatusScreen(tk.Frame):
    def __init__(self, parent, palette: theme.Palette, fonts,
                 readiness: Readiness, access: Access | None, *,
                 on_setup, on_close, version: str, log: tuple[str, ...] = (),
                 notice: str = ""):
        super().__init__(parent, bg=palette.bg)
        self._palette, self._fonts = palette, fonts
        self._readiness, self._access = readiness, access
        self._version, self._log = version, log

        headline, detail = summarize(readiness)
        widgets.Header(self, palette, fonts, "Omelet", headline).pack(fill="x")

        body = tk.Frame(self, bg=palette.bg)
        body.pack(fill="both", expand=True, padx=theme.PAD, pady=theme.PAD)

        tk.Label(body, text=detail, bg=palette.bg, fg=palette.text,
                 font=fonts["body"], anchor="w", justify="left",
                 wraplength=520).pack(fill="x")

        if notice:
            # The wizard's own closing sentence -- e.g. where the VM lives and
            # what to type next. It is what just happened, not an error, so it
            # reads as body text and sits above the access panel where a user
            # landing here straight off a successful install can't miss it.
            tk.Label(body, text=notice, bg=palette.bg, fg=palette.text,
                     font=fonts["body"], anchor="w", justify="left",
                     wraplength=520).pack(fill="x", pady=(10, 0))

        if show_access_panel(access):
            self._access_panel(body, access)

        buttons = tk.Frame(body, bg=palette.bg)
        buttons.pack(side="bottom", anchor="e", pady=(16, 0))
        widgets.Button(buttons, palette, fonts, "Copy diagnostics",
                       self._copy_diagnostics, width=160).pack(side="left", padx=(0, 8))
        widgets.Button(buttons, palette, fonts,
                       "Re-run setup" if readiness.ready else "Set up Omelet",
                       on_setup, primary=True, width=150).pack(side="left", padx=(0, 8))
        widgets.Button(buttons, palette, fonts, "Close", on_close,
                       width=100).pack(side="left")

    def _access_panel(self, parent, access: Access) -> None:
        panel = tk.Frame(parent, bg=self._palette.bg)
        panel.pack(fill="x", pady=(18, 0))
        tk.Label(panel, text=access.headline, bg=self._palette.bg,
                 fg=self._palette.text, font=self._fonts["heading"],
                 anchor="w").pack(fill="x")
        tk.Label(panel, text=access.summary, bg=self._palette.bg,
                 fg=self._palette.muted, font=self._fonts["small"], anchor="w",
                 justify="left", wraplength=520).pack(fill="x", pady=(2, 10))
        widgets.FieldRow(panel, self._palette, self._fonts,
                         "Command", access.command).pack(fill="x", pady=2)
        for field in access.fields:
            widgets.FieldRow(panel, self._palette, self._fonts,
                             field.label, field.value).pack(fill="x", pady=2)
        if access.note:
            tk.Label(panel, text=access.note, bg=self._palette.bg,
                     fg=self._palette.muted, font=self._fonts["small"],
                     anchor="w", justify="left", wraplength=520).pack(
                         fill="x", pady=(8, 0))

    def _copy_diagnostics(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(diagnostics_text(self._readiness, self._access,
                                               version=self._version, log=self._log))
