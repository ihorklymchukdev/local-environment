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


def test_there_is_a_glyph_for_every_status_run_install_can_report():
    from host.core.install import Progress
    # The five statuses run_install emits, and the sixth the UI starts rows in.
    for status in ("pending", "running", "done", "skipped", "failed", "reboot"):
        assert status in widgets.GLYPHS
    assert Progress("x", "running").status in widgets.GLYPHS
