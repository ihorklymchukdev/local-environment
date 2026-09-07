from omelet.core.diagnose import render_diagnosis
from omelet.core.provider import Diagnosis, CheckResult


def test_render_marks_pass_and_fail_with_fix():
    text = render_diagnosis(Diagnosis([
        CheckResult("wsl --version available", True),
        CheckResult("virtualization enabled", False, fix="enable VT-x in BIOS"),
    ]))
    assert "wsl --version available" in text
    assert "enable VT-x in BIOS" in text
    # a failed check is visually distinct from a passed one
    pass_line = [l for l in text.splitlines() if "available" in l][0]
    fail_line = [l for l in text.splitlines() if "virtualization" in l][0]
    assert pass_line[:1] != fail_line[:1]
