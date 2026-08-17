from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import ttk

from runtime.core.install import (
    DeadEnd, InstallError, Progress, RebootRequired, run_install,
)

_LABELS = {
    "preflight": "Checking this computer",
    "remediate": "Turning on Windows features",
    "reboot_gate": "Restart needed",
    "fetch_image": "Downloading Linux image",
    "create_vm": "Creating the virtual machine",
    "bootstrap": "Installing Docker",
    "verify": "Testing the setup",
}
_MARKS = {"running": "…", "done": "✓", "failed": "✗", "skipped": "✓", "reboot": "!"}


def run_window(steps, state) -> int:
    events: queue.Queue = queue.Queue()
    outcome = {"code": 0, "message": ""}
    finished = {"value": False}

    def worker():
        try:
            try:
                run_install(steps, state, events.put)
            except RebootRequired:
                outcome.update(code=2, message=(
                    "Restart your computer.\n"
                    "Setup will continue on its own when you log back in."))
            except DeadEnd as e:
                outcome.update(code=1, message=
                    f"This computer needs a change before setup can continue:\n\n{e}")
            except InstallError as e:
                outcome.update(code=1, message=f"Setup failed during {e.step}:\n\n{e.message}")
            except Exception as e:
                outcome.update(code=1, message=f"Unexpected error: {e}")
        finally:
            events.put(None)

    root = tk.Tk()
    root.title("Local Runtime Setup")
    root.geometry("560x420")

    def on_close():
        # User closed the window mid-install; report failure rather than default success.
        if not finished["value"]:
            outcome.update(code=1, message="Setup was cancelled before completing.")
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)

    rows: dict[str, tk.StringVar] = {}
    frame = ttk.Frame(root, padding=16)
    frame.pack(fill="both", expand=True)
    for step in steps:
        var = tk.StringVar(value=f"   {_LABELS.get(step.name, step.name)}")
        ttk.Label(frame, textvariable=var, font=("Segoe UI", 10)).pack(anchor="w", pady=2)
        rows[step.name] = var

    bar = ttk.Progressbar(frame, mode="indeterminate")
    bar.pack(fill="x", pady=12)
    bar.start(12)

    log = tk.Text(frame, height=8, wrap="word", state="disabled")
    log.pack(fill="both", expand=True)

    def append(text: str):
        log.configure(state="normal")
        log.insert("end", text + "\n")
        log.see("end")
        log.configure(state="disabled")

    def pump():
        while True:
            try:
                event = events.get_nowait()
            except queue.Empty:
                break
            if event is None:
                finished["value"] = True
                bar.stop()
                if outcome["message"]:
                    append("\n" + outcome["message"])
                ttk.Button(frame, text="Close", command=root.destroy).pack(pady=8)
                return
            _render(event, rows, append)
        root.after(100, pump)

    threading.Thread(target=worker, daemon=True).start()
    root.after(100, pump)
    root.mainloop()
    return outcome["code"]


def _render(event: Progress, rows, append) -> None:
    label = _LABELS.get(event.step, event.step)
    if event.step in rows:
        rows[event.step].set(f" {_MARKS.get(event.status, ' ')} {label}")
    if event.message:
        append(f"{label}: {event.message}")
