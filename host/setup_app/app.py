from __future__ import annotations

# The router. Two screens live behind it: the status screen a user lands on,
# and the wizard that runs the install.
#
# It opens on status even when nothing is provisioned -- and starts the wizard
# itself in that case, so a first-time user still double-clicks once. On a
# machine that is already set up, the status screen is where the SSH details
# are, and nothing re-runs a multi-minute install just to show them.

import queue
import threading
import tkinter as tk

from host.core.status import Readiness, probe

from . import status as status_screen
from . import theme, widgets, wizard


def _log_with_notice(log: tuple[str, ...], message: str) -> tuple[str, ...]:
    """The finish step's closing sentence never reaches the wizard's own log
    box (`wizard.split_finish_message` strips it before `_append` so the row
    it names can still turn done) -- so unless it lands here too, Copy
    diagnostics on the status screen that follows would carry everything the
    run logged except the one sentence the run was for."""
    return (*log, message) if message else log


def run_window(provider, steps_factory, state, *, resumed: bool = False) -> int:
    root = tk.Tk()
    root.title("Omelet Setup")
    root.geometry("620x620")
    root.minsize(560, 560)

    palette = theme.palette_for_root(root)
    fonts = theme.load_fonts(root)
    root.configure(bg=palette.bg)

    app_state = {"code": 0, "screen": None, "log": ()}

    def close() -> None:
        screen = app_state["screen"]
        if isinstance(screen, wizard.WizardScreen):
            outcome = screen.cancelled()
            app_state["code"] = outcome.code
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)

    def show(frame) -> None:
        previous = app_state["screen"]
        if previous is not None:
            previous.destroy()
        app_state["screen"] = frame
        frame.pack(fill="both", expand=True)

    def show_status(readiness: Readiness, notice: str = "") -> None:
        from host.core import constants
        try:
            access = provider.access()
        except Exception:
            # A provider that cannot describe how to get in is not a reason to
            # show nothing; the rest of the screen still answers "am I set up".
            access = None
        show(status_screen.StatusScreen(
            root, palette, fonts, readiness, access,
            on_setup=start_wizard, on_close=close,
            version=constants.APP_VERSION, log=app_state["log"], notice=notice))

    def start_wizard(*, first: bool = False) -> None:
        # A fresh list every time: the steps close over provider state
        # (`provider.rootfs` is assigned while the list is built), so a
        # re-run against a list built for an earlier run would run the
        # second install against the first one's bindings.
        #
        # `resumed` only ever describes the run this window opened for -- a
        # user who presses "Re-run setup" afterwards asked for this run
        # themselves, and must not see "you don't need to do anything" about
        # a restart that happened, if at all, several runs ago. Only the one
        # call made before anything else runs may claim it.
        screen = wizard.WizardScreen(root, palette, fonts, steps_factory(),
                                     state, on_finished=wizard_finished,
                                     resumed=first and resumed)
        show(screen)
        screen.start()

    def wizard_finished(outcome: wizard.Outcome) -> None:
        app_state["code"] = outcome.code
        app_state["log"] = _log_with_notice(outcome.log, outcome.message)
        if outcome.code == 0:
            # Straight to the screen that says how to get in: the install's
            # closing sentence is the beginning of the next thing the user
            # does, so it has to survive onto the screen that follows -- not
            # just into the log, which nobody opens by default.
            begin_probe(then=lambda readiness: show_status(
                readiness, notice=outcome.message))

    # --- the probe, off the main thread so the window draws immediately ---

    results: queue.Queue = queue.Queue()

    def begin_probe(*, then, auto_setup: bool = False) -> None:
        show(_Spinner(root, palette, fonts))
        threading.Thread(target=lambda: results.put(probe(provider)),
                         daemon=True).start()

        def wait() -> None:
            try:
                readiness = results.get_nowait()
            except queue.Empty:
                return root.after(100, wait)
            if auto_setup and not readiness.vm_exists:
                return start_wizard()
            then(readiness)

        root.after(100, wait)

    if resumed:
        # A window that opened by itself after a restart has one job.
        start_wizard(first=True)
    else:
        begin_probe(then=show_status, auto_setup=True)

    root.mainloop()
    return app_state["code"]


class _Spinner(tk.Frame):
    """Shown for the second or two the probe takes. A window that draws nothing
    while a subprocess runs reads as a hang."""

    def __init__(self, parent, palette: theme.Palette, fonts):
        super().__init__(parent, bg=palette.bg)
        widgets.Header(self, palette, fonts, "Omelet", "Checking this computer…").pack(fill="x")
        self._list = widgets.StepList(self, palette, fonts, [("probe", "Looking for the virtual machine")])
        self._list.set_state("probe", "running")
        self._list.pack(fill="x", padx=theme.PAD, pady=theme.PAD)
        self._after_id: str | None = None
        self._tick()

    def _tick(self) -> None:
        self._list.tick()
        self._after_id = self.after(80, self._tick)

    def destroy(self) -> None:
        # `show()` destroys every screen it replaces, but Misc.destroy only
        # deletes the Tcl command backing this widget -- it does not cancel a
        # pending `after()`, so the next tick fires against a command that no
        # longer exists and Tk logs a background error ("invalid command
        # name"). This also explains why the `winfo_exists()` guard that used
        # to open `_tick` could never fire: destroy() is the only path off
        # this screen, so by the time a stray tick could arrive, this
        # override has already cancelled it.
        if self._after_id is not None:
            self.after_cancel(self._after_id)
            self._after_id = None
        super().destroy()
