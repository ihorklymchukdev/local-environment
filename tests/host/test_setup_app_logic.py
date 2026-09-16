"""The parts of the window that are not the window.

No test opens a Tk root: everything worth asserting here is a pure function,
which is the reason the theme and the widgets are separate modules at all.
"""
import pytest

from host.setup_app import theme, widgets


def test_a_light_background_selects_the_light_palette():
    # winfo_rgb returns 16-bit channels: 65535 is full white.
    assert theme.palette_for((65535, 65535, 65535)) is theme.LIGHT
    assert theme.palette_for((60000, 60000, 60000)) is theme.LIGHT


def test_a_dark_background_selects_the_dark_palette():
    assert theme.palette_for((0, 0, 0)) is theme.DARK
    assert theme.palette_for((7710, 7710, 7967)) is theme.DARK


def test_luminance_weights_green_most():
    # Not an average: a mid green reads brighter to the eye than a mid blue,
    # and picking the palette by a flat mean gets dark mode wrong on macOS.
    green = theme.luminance((0, 40000, 0))
    blue = theme.luminance((0, 0, 40000))
    assert green > blue


def test_every_palette_defines_every_colour():
    for palette in (theme.LIGHT, theme.DARK):
        for name, value in vars(palette).items():
            assert isinstance(value, str) and value.startswith("#"), name
            assert len(value) == 7, f"{name}={value}"


@pytest.mark.parametrize("seconds,text", [
    (0, ""), (0.4, ""), (1, "1s"), (9.6, "9s"), (59, "59s"),
    (60, "1m 00s"), (145, "2m 25s"), (3600, "60m 00s"),
])
def test_elapsed_time_is_only_shown_once_there_is_some(seconds, text):
    # A step that took 400ms showing "0s" is noise on every row of the list.
    assert widgets.format_elapsed(seconds) == text


@pytest.mark.parametrize("base_size,delta,expected", [
    (13, 7, 20),      # ordinary positive base: title grows as intended
    (13, -1, 12),     # ordinary positive base: small shrinks as intended
    (-12, 7, -19),    # negative (pixel) base: title must still grow *larger*
    (-12, -1, -11),   # negative (pixel) base: small must still shrink
    (0, -1, 1),       # a delta that would cross zero floors at magnitude 1
    (3, -5, 1),       # same floor, from a positive base
])
def test_derived_size_moves_in_the_intended_direction_regardless_of_sign(
        base_size, delta, expected):
    # tkinter uses negative sizes for pixels (a known Windows pattern); naive
    # `base_size + delta` inverts every derived size when base_size < 0, so
    # "title" (delta +7) would come out smaller than body instead of larger.
    assert theme.derived_size(base_size, delta) == expected


def test_there_is_a_glyph_for_every_status_run_install_can_report():
    from host.core.install import Progress
    # The five statuses run_install emits, and the sixth the UI starts rows in.
    for status in ("pending", "running", "done", "skipped", "failed", "reboot"):
        assert status in widgets.GLYPHS
    assert Progress("x", "running").status in widgets.GLYPHS


from host.core.install import Progress, Step
from host.setup_app import wizard


def test_a_step_label_prefers_the_providers_own_words():
    # "Installing Lima 2.2.0" is Lima's sentence; the installer has no business
    # keeping a second copy of it in a dict keyed by step name.
    step = Step("install_runtime", lambda emit: None, label="Installing Lima 2.2.0")
    assert wizard.step_label(step) == "Installing Lima 2.2.0"


def test_a_step_without_a_label_falls_back_to_the_installers_wording():
    # "Preparing", not "Creating": the same step now starts an existing but
    # stopped VM as well as creating an absent one (host/core/install.py's
    # _ensure_vm_running), and the wizard's wording must not claim only one.
    assert wizard.step_label(Step("create_vm", lambda: None)) == \
        "Preparing the virtual machine"


def test_an_unknown_step_shows_its_own_name_rather_than_nothing():
    assert wizard.step_label(Step("something_new", lambda: None)) == "something_new"


def test_the_label_table_has_no_entry_for_a_step_the_provider_names():
    # install_runtime's text comes from provider.runtime().label. A second copy
    # here would go stale the first time the pinned Lima version changes.
    assert "install_runtime" not in wizard.LABELS


def test_the_windows_only_steps_are_still_named_for_windows():
    assert wizard.LABELS["remediate"] == "Turning on Windows features"


def test_the_finish_steps_done_message_moves_to_the_outcome_panel():
    # run_install's real finish/done event carries the words for the last
    # screen. Left in place, they'd double as a log line nobody asked to see,
    # and the row itself would never learn its message-less counterpart --
    # the actual bug this test guards was the row being skipped entirely.
    event, message = wizard.split_finish_message(
        Progress("finish", "done", "Setup finished successfully."))
    assert event == Progress("finish", "done")
    assert message == "Setup finished successfully."


def test_the_finish_steps_running_event_is_untouched():
    event, message = wizard.split_finish_message(Progress("finish", "running"))
    assert event == Progress("finish", "running")
    assert message is None


def test_an_ordinary_steps_message_still_belongs_in_the_log():
    # connect_step returns a sentence on its repair path; that must keep
    # reaching the log, not get swept into the outcome panel.
    progress = Progress("connect", "done", "reconnected")
    event, message = wizard.split_finish_message(progress)
    assert event == progress
    assert message is None


from host.core.provider import Access, AccessField
from host.core.status import Readiness
from host.setup_app import status

READY = Readiness(vm_exists=True, vm_reachable=True, engine_version="0.1.0", agent_api=1)
ACCESS = Access(headline="Connect a coding agent", summary="…",
                command="ssh -F /Users/you/.lima/omelet-vm/ssh.config lima-omelet-vm",
                fields=(AccessField("Host", "127.0.0.1"),
                        AccessField("Port", "39022")))


def test_a_ready_machine_says_so_in_two_lines():
    headline, detail = status.summarize(READY)
    assert headline == "Ready"
    assert "0.1.0" in detail


def test_a_machine_with_no_vm_says_what_is_missing_not_what_failed():
    headline, detail = status.summarize(Readiness())
    assert headline == "Not set up yet"
    assert "Set up" in detail or "set up" in detail


def test_a_stopped_vm_is_distinguished_from_a_missing_one():
    headline, _ = status.summarize(Readiness(vm_exists=True))
    assert headline != "Not set up yet"
    assert "not running" in headline.lower() or "stopped" in headline.lower()


def test_an_incompatible_agent_is_named_as_a_version_problem():
    from host.core import constants
    bad = Readiness(vm_exists=True, vm_reachable=True, engine_version="9.9.9",
                    agent_api=max(constants.SUPPORTED_API) + 1)
    headline, detail = status.summarize(bad)
    assert "version" in (headline + detail).lower()


@pytest.mark.parametrize("readiness", [
    Readiness(problem="disk full"),
    Readiness(vm_exists=True, problem="ssh connection refused"),
    Readiness(vm_exists=True, vm_reachable=True,
              problem="permission denied reading engine.version"),
    Readiness(vm_exists=True, vm_reachable=True, engine_version="0.1.0",
              problem="connection refused"),
], ids=["missing-vm", "unreachable-vm", "no-engine-version", "agent-not-answering"])
def test_a_set_problem_survives_into_the_detail_on_every_non_ready_branch(readiness):
    # Each non-ready branch has its own "append problem if set" line. A real
    # error thrown while probing (host/core/status.py's probe() sets `problem`
    # on any exception, at every stage) must never be silently swallowed into
    # a generic "run setup again" -- that already happened once, in the
    # `not engine_version` branch, which dropped it while its three siblings
    # kept it.
    _, detail = status.summarize(readiness)
    assert readiness.problem in detail


def test_diagnostics_carry_everything_someone_would_ask_for():
    text = status.diagnostics_text(READY, ACCESS, version="0.1.0",
                                   log=("bootstrap: done",))
    for expected in ("0.1.0", "vm_exists", "engine_version", "agent_api",
                     "bootstrap: done"):
        assert expected in text


def test_diagnostics_never_open_a_file_and_carry_only_paths_not_contents(monkeypatch):
    # Paths are fine; secrets are not. This text is written to be pasted into
    # a bug report by someone who will not read it first. "PRIVATE KEY" not in
    # text only proves this one path's contents don't happen to leak today;
    # monkeypatching open() to explode proves the stronger property -- that
    # diagnostics_text is a pure pass-through of the strings it was already
    # handed and could never read a path off disk even if that path existed.
    def _no_reads(*args, **kwargs):
        raise AssertionError("diagnostics_text must never open a file")
    monkeypatch.setattr("builtins.open", _no_reads)

    access = Access(headline="x", summary="y", command="ssh …",
                    fields=(AccessField("Identity file", "/Users/you/.lima/_config/user"),))
    text = status.diagnostics_text(READY, access, version="0.1.0")
    assert "/Users/you/.lima/_config/user" in text
    assert "PRIVATE KEY" not in text


def test_diagnostics_work_before_anything_is_provisioned():
    # The button exists on a machine where the probe found nothing, and that is
    # exactly the machine whose user needs to send us something.
    text = status.diagnostics_text(Readiness(problem="limactl is not installed"),
                                   None, version="0.1.0")
    assert "limactl is not installed" in text


from host.setup_app import app as setup_app


def test_the_finish_sentence_is_folded_into_the_log_for_diagnostics():
    # wizard.split_finish_message strips the finish step's `done` message out
    # of the wizard's own log box so the row it names can still turn done --
    # which means nothing else appends it anywhere unless this does. Without
    # it, Copy diagnostics on the status screen that follows a successful run
    # would carry every log line except the one sentence the run was for.
    log = setup_app._log_with_notice(("bootstrap: done",),
                                     "Ready. Try: omelet up <folder>")
    assert log == ("bootstrap: done", "Ready. Try: omelet up <folder>")


def test_an_empty_finish_message_leaves_the_log_untouched():
    # A cancelled run's Outcome carries no message; appending an empty string
    # would put a blank line in the diagnostics for no reason.
    assert setup_app._log_with_notice(("a", "b"), "") == ("a", "b")


def test_diagnostics_carry_the_finish_sentence_once_it_is_in_the_log():
    text = status.diagnostics_text(
        READY, ACCESS, version="0.1.0",
        log=setup_app._log_with_notice((), "Ready. Try: omelet up <folder>"))
    assert "Ready. Try: omelet up <folder>" in text


def test_the_access_panel_is_not_gated_on_readiness_being_ready():
    # The Lima fallback (_PORT_UNCONFIRMED, _fallback_note's "run setup, then
    # open this window again") exists precisely for states `ready` excludes --
    # a VM that exists but whose engine never finished installing, or one that
    # has never booted at all. Gating the panel on `readiness.ready` made all
    # of that text, and every field in it, unreachable from this screen.
    assert status.show_access_panel(ACCESS) is True
    assert status.show_access_panel(None) is False


class _StatefulRun:
    """The one fact `_should_auto_start` reads off InstallState: whether
    anything has ever completed. A real `InstallState` over a tmp_path file
    would work identically; this avoids a filesystem fixture for a one-line
    check."""

    def __init__(self, completed):
        self._completed = completed

    def completed(self):
        return self._completed


def test_a_truly_fresh_machine_auto_starts_the_wizard():
    assert setup_app._should_auto_start(Readiness(), _StatefulRun(set())) is True


def test_a_machine_that_failed_a_previous_attempt_does_not_auto_start_again():
    # The create_vm relaunch trap: a VM that keeps failing to create never
    # makes `vm_exists` true, so gating on that fact alone sent every relaunch
    # straight back into another doomed wizard run, with no way to ever reach
    # the status screen or its Copy diagnostics button.
    assert setup_app._should_auto_start(
        Readiness(), _StatefulRun({"preflight"})) is False


def test_an_existing_vm_never_auto_starts_the_wizard():
    assert setup_app._should_auto_start(
        Readiness(vm_exists=True), _StatefulRun(set())) is False
