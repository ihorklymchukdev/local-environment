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
    assert wizard.step_label(Step("create_vm", lambda: None)) == \
        "Creating the virtual machine"


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
