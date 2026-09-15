from __future__ import annotations

# The screen that runs the install. One row per step, a real progress bar, and
# the log behind a disclosure -- a first-time user watching this should see a
# short list of plain sentences, not a terminal.

import queue
import threading
import time
import tkinter as tk
from dataclasses import dataclass, field

from host.core.install import (
    RESUME_NOTICE, DeadEnd, InstallError, Progress, RebootRequired, Step, run_install,
)

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
    "create_vm": "Creating the virtual machine",
    "bootstrap": "Installing Omelet",
    "connect": "Connecting to the Omelet service",
    "verify": "Testing the setup",
    "finish": "Finishing up",
}


def step_label(step: Step) -> str:
    return step.label or LABELS.get(step.name, step.name)


@dataclass(frozen=True)
class Outcome:
    code: int
    message: str = ""
    log: tuple[str, ...] = field(default_factory=tuple)


class WizardScreen(tk.Frame):
    def __init__(self, parent, palette: theme.Palette, fonts, steps, state,
                 on_finished, *, resumed: bool = False):
        super().__init__(parent, bg=palette.bg)
        self._palette, self._fonts = palette, fonts
        self._steps, self._state = steps, state
        self._on_finished = on_finished
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
        # The finish step's product is words, and they belong on the next
        # screen rather than scrolled away in a log nobody opened.
        if event.step == "finish" and event.status == "done":
            self._outcome = Outcome(0, event.message, tuple(self._log))
            return
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
        self._on_finished(Outcome(self._outcome.code, self._outcome.message,
                                  tuple(self._log)))

    def cancelled(self) -> Outcome:
        """The window was closed mid-install. Report failure rather than
        defaulting to success -- nothing about a half-built VM is a success."""
        if self._finished:
            return self._outcome
        return Outcome(1, "Setup was cancelled before completing.", tuple(self._log))
