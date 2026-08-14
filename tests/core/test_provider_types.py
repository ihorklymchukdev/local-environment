from runtime.core.provider import Completed, CheckResult, Diagnosis


def test_completed_ok_reflects_returncode():
    assert Completed(0, "out", "").ok is True
    assert Completed(1, "", "err").ok is False


def test_diagnosis_ok_only_when_all_checks_pass():
    good = Diagnosis([CheckResult("a", True), CheckResult("b", True)])
    bad = Diagnosis([CheckResult("a", True), CheckResult("b", False, fix="do x")])
    assert good.ok is True
    assert bad.ok is False


def test_diagnosis_blocking_lists_only_failures():
    d = Diagnosis([CheckResult("a", True), CheckResult("b", False, fix="do x")])
    assert [c.label for c in d.blocking] == ["b"]
