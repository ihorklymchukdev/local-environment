from __future__ import annotations

# The screen that runs the install. One row per step, a real progress bar, and
# the log behind a disclosure -- a first-time user watching this should see a
# short list of plain sentences, not a terminal.

import queue
import threading
import time
import tkinter as tk
from dataclasses import dataclass, field

from host.core import constants
from host.core.install import (
    RESUME_NOTICE, DeadEnd, InstallError, Progress, RebootRequired, Step, run_install,
)
from host.core.status import Readiness

from . import status as status_screen
from . import theme, widgets

# Steps the installer names itself. install_runtime is absent on purpose: its
# text comes from provider.runtime().label, because the version in it is
# Lima's fact, not the installer's -- a second copy here would go stale the
# first time the pinned version changes.
LABELS = {
    "preflight": "Checking this computer",
    "remediate": "Turning on Windows features",
    "reboot_gate": "Restart needed",
    "fetch_image": "Downloading Linux image",
    # Covers both: an absent VM is created, an existing-but-stopped one is
    # started (see host/core/install.py's _ensure_vm_running).
    "create_vm": "Preparing the virtual machine",
    "bootstrap": "Installing Omelet",
    "connect": "Connecting to the Omelet service",
    "verify": "Testing the setup",
    "finish": "Finishing up",
}


def step_label(step: Step) -> str:
    return step.label or LABELS.get(step.name, step.name)


def split_finish_message(progress: Progress) -> tuple[Progress, str | None]:
    """Pull the outcome-panel words off the finish step's `done` event.

    That event's message is the whole point of the run and belongs on the
    next screen, not scrolled into a log nobody opened -- but the row it
    names still has to turn done like every other row, or the spinner glyph
    `_list.tick()` was animating freezes there forever once the pump sees the
    sentinel and stops calling tick(). Stripping the message and handing the
    now-plain event back lets the caller run it through the same terminal-
    event handling as everything else. Every other event, including finish's
    own `running` event and every other step's `done` message (`connect_step`
    has one on its repair path), passes through untouched -- those messages
    still belong in the log.
    """
    if progress.step == "finish" and progress.status == "done":
        return Progress(progress.step, progress.status), progress.message
    return progress, None


@dataclass(frozen=True)
class Outcome:
    code: int
    message: str = ""
    log: tuple[str, ...] = field(default_factory=tuple)


class WizardScreen(tk.Frame):
    def __init__(self, parent, palette: theme.Palette, fonts, steps, state,
                 on_finished, *, resumed: bool = False, on_close=None,
                 on_view_status=None):
        super().__init__(parent, bg=palette.bg)
        self._palette, self._fonts = palette, fonts
        self._steps, self._state = steps, state
        self._on_finished = on_finished
        # Both optional: a caller with nowhere to send "Close" or "View status"
        # (there is none today, but a test building this screen standalone
        # might have neither) gets a terminal panel with only Copy diagnostics
        # rather than a button wired to nothing.
        self._on_close = on_close
        self._on_view_status = on_view_status
        self._events: queue.Queue = queue.Queue()
        self._log: list[str] = []
        self._outcome = Outcome(0)
        self._finished = False
        self._started_at = {}
        self._done = 0
        # The bar's own fraction, tracked here rather than read back off the
        # widget: ProgressBar keeps no public accessor, and reaching into its
        # private `_value` was the exact review finding Task 6 fixed on Button.
        self._fraction = 0.0

        self._header = widgets.Header(
            self, palette, fonts, "Omelet",
            RESUME_NOTICE if resumed else "Setting up your local environment")
        self._header.pack(fill="x")

        body = tk.Frame(self, bg=palette.bg)
        body.pack(fill="both", expand=True, padx=theme.PAD, pady=theme.PAD)

        self._list = widgets.StepList(
            body, palette, fonts, [(s.name, step_label(s)) for s in steps])
        self._list.pack(fill="x")

        self._bar = widgets.ProgressBar(body, palette)
        self._bar.pack(fill="x", pady=(12, 4))

        self._detail = tk.Label(body, text="", bg=palette.bg, fg=palette.muted,
                                font=fonts["small"], anchor="w", justify="left",
                                wraplength=520)
        self._detail.pack(fill="x")

        self._disclosure = widgets.Button(body, palette, fonts, "Show details ▾",
                                          self._toggle_log, width=140)
        self._disclosure.pack(anchor="w", pady=(12, 0))
        self._log_box = tk.Text(body, height=9, wrap="word", relief="flat",
                                bg=palette.surface, fg=palette.text,
                                font=fonts["mono"], state="disabled",
                                highlightthickness=1,
                                highlightbackground=palette.border)

        self._buttons = tk.Frame(body, bg=palette.bg)
        self._buttons.pack(side="bottom", anchor="e", pady=(12, 0))

    # --- running ---

    def start(self) -> None:
        threading.Thread(target=self._worker, daemon=True).start()
        self.after(80, self._pump)

    def _worker(self) -> None:
        try:
            try:
                run_install(self._steps, self._state, self._events.put)
            except RebootRequired:
                self._outcome = Outcome(2, (
                    "Restart your computer.\n"
                    "Setup will continue on its own when you log back in."))
            except DeadEnd as e:
                self._outcome = Outcome(1, "This computer needs a change before "
                                           f"setup can continue:\n\n{e}")
            except InstallError as e:
                message = f"Setup failed during {step_label(self._step(e.step))}."
                if e.action:
                    message += f"\n\n{e.action}"
                self._outcome = Outcome(1, message)
            except Exception as e:                  # noqa: BLE001 - last resort
                self._outcome = Outcome(1, f"Unexpected error: {e}")
        finally:
            self._events.put(None)

    def _step(self, name: str) -> Step:
        for step in self._steps:
            if step.name == name:
                return step
        return Step(name, lambda: None)

    def _pump(self) -> None:
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            if event is None:
                return self._finish()
            self._render(event)
        self._list.tick()
        self.after(80, self._pump)

    def _set_fraction(self, value: float) -> None:
        self._fraction = value
        self._bar.set(value)

    def _render(self, event: Progress) -> None:
        event, finish_message = split_finish_message(event)
        if finish_message is not None:
            self._outcome = Outcome(0, finish_message, tuple(self._log))
        label = step_label(self._step(event.step))
        if event.fraction is not None:
            self._set_fraction((self._done + event.fraction) / len(self._steps))
            self._detail.configure(text=f"{label} — {int(event.fraction * 100)}%")
            return
        if event.status == "running":
            self._started_at[event.step] = time.monotonic()
            self._detail.configure(text=label)
        else:
            self._done += 1
            self._set_fraction(self._done / len(self._steps))
        elapsed = time.monotonic() - self._started_at.get(event.step, time.monotonic())
        self._list.set_state(event.step, event.status,
                             elapsed if event.status != "running" else 0.0)
        if event.message:
            self._append(f"{label}: {event.message}")

    def _append(self, text: str) -> None:
        self._log.append(text)
        self._log_box.configure(state="normal")
        self._log_box.insert("end", text + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _toggle_log(self) -> None:
        if self._log_box.winfo_ismapped():
            self._log_box.pack_forget()
            self._disclosure.set_text("Show details ▾")
        else:
            self._log_box.pack(fill="both", expand=True, pady=(8, 0))
            self._disclosure.set_text("Hide details ▴")

    def _finish(self) -> None:
        self._finished = True
        self._set_fraction(1.0 if self._outcome.code == 0 else self._fraction)
        self._header.say("Finished" if self._outcome.code == 0 else "Setup stopped")
        self._detail.configure(
            text=self._outcome.message,
            fg=self._palette.text if self._outcome.code == 0 else self._palette.error)
        if self._outcome.code != 0 and self._log and not self._log_box.winfo_ismapped():
            self._toggle_log()
        self._populate_terminal_buttons()
        self._on_finished(Outcome(self._outcome.code, self._outcome.message,
                                  tuple(self._log)))

    def _populate_terminal_buttons(self) -> None:
        """A terminal screen with no buttons is a dead end.

        The `run_window` this screen replaced had a working Close button here
        (docs/macos-install-test-matrix.md case 3), and install.py's
        `_ACTIONS` for `bootstrap`, `connect` and `verify` have told a failed
        user to press Copy diagnostics since the installer was written --
        against a button that has never existed anywhere in the app. A
        success outcome reaches this too (`_on_finished` immediately swaps
        this screen for the probe spinner on that path), but populating it
        unconditionally is what makes every other terminal outcome --
        failure, a dead end, a reboot -- come with real buttons instead of an
        outcome sentence and nothing else.
        """
        widgets.Button(self._buttons, self._palette, self._fonts,
                       "Copy diagnostics", self._copy_diagnostics,
                       width=160).pack(side="left", padx=(0, 8))
        if self._outcome.code != 0 and self._on_view_status is not None:
            # The only way out of a run that failed before a VM exists: a
            # relaunch used to force straight back into this same wizard
            # (`app.py`'s auto_setup gate saw no VM and started it again),
            # so Copy diagnostics was reachable from the failure screen
            # itself but the status screen -- and its own Set up button for
            # trying again -- never was.
            widgets.Button(self._buttons, self._palette, self._fonts,
                           "View status", self._on_view_status, primary=True,
                           width=150).pack(side="left", padx=(0, 8))
        if self._on_close is not None:
            widgets.Button(self._buttons, self._palette, self._fonts, "Close",
                           self._on_close, width=100).pack(side="left")

    def _copy_diagnostics(self) -> None:
        """Reuses status.diagnostics_text rather than a second formatter.

        There is no Readiness or Access here -- this screen runs before either
        is known, and a run that fails at `create_vm` never gets one at all --
        so it is handed the "nothing established" default and no access. The
        outcome message is folded in the same way `app._log_with_notice` folds
        it into the status screen's log: `_render` strips it out of `_log` so
        the finish row can still turn done, and it belongs in the text a user
        pastes into a bug report exactly as much as it belongs on screen.
        """
        log = (*self._log, self._outcome.message) if self._outcome.message \
            else tuple(self._log)
        self.clipboard_clear()
        self.clipboard_append(status_screen.diagnostics_text(
            Readiness(), None, version=constants.APP_VERSION, log=log))

    def cancelled(self) -> Outcome:
        """The window was closed mid-install. Report failure rather than
        defaulting to success -- nothing about a half-built VM is a success."""
        if self._finished:
            return self._outcome
        return Outcome(1, "Setup was cancelled before completing.", tuple(self._log))
