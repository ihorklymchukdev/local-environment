import pytest

from host.core.install import (
    DeadEnd, InstallError, InstallState, Progress, RebootRequired, Step,
    preflight_step, reboot_gate_step, remediate_step, run_install,
)
from host.core.provider import CheckResult, Diagnosis


def _recorder():
    events = []
    return events, events.append


def test_state_round_trips_through_a_new_object(tmp_path):
    path = tmp_path / "install-state.json"
    InstallState(path).mark("preflight")
    assert InstallState(path).completed() == {"preflight"}


def test_state_starts_empty_when_the_file_is_absent(tmp_path):
    assert InstallState(tmp_path / "nope.json").completed() == set()


def test_state_survives_a_corrupt_file(tmp_path):
    # A half-written file after a power loss must not brick setup forever.
    path = tmp_path / "install-state.json"
    path.write_text("{not json")
    assert InstallState(path).completed() == set()


def test_clear_forgets_everything(tmp_path):
    path = tmp_path / "install-state.json"
    state = InstallState(path)
    state.mark("preflight")
    state.clear()
    assert InstallState(path).completed() == set()


def test_steps_run_in_order_and_are_all_marked(tmp_path):
    ran = []
    steps = [Step(n, (lambda n=n: ran.append(n))) for n in ("a", "b", "c")]
    state = InstallState(tmp_path / "s.json")
    events, report = _recorder()
    run_install(steps, state, report)
    assert ran == ["a", "b", "c"]
    assert state.completed() == {"a", "b", "c"}
    assert [(e.step, e.status) for e in events if e.status == "done"] == \
        [("a", "done"), ("b", "done"), ("c", "done")]


def test_completed_steps_are_skipped_not_rerun(tmp_path):
    ran = []
    state = InstallState(tmp_path / "s.json")
    state.mark("a")
    steps = [Step(n, (lambda n=n: ran.append(n))) for n in ("a", "b")]
    events, report = _recorder()
    run_install(steps, state, report)
    assert ran == ["b"], "an already-completed step must not run again"
    assert Progress("a", "skipped") in events


def test_a_failing_step_stops_the_run_and_is_not_marked(tmp_path):
    ran = []

    def boom():
        raise RuntimeError("apt exploded")

    steps = [Step("a", lambda: ran.append("a")),
             Step("b", boom),
             Step("c", lambda: ran.append("c"))]
    state = InstallState(tmp_path / "s.json")
    events, report = _recorder()
    with pytest.raises(InstallError) as excinfo:
        run_install(steps, state, report)
    assert excinfo.value.step == "b"
    assert "apt exploded" in str(excinfo.value)
    assert ran == ["a"], "steps after a failure must not run"
    assert state.completed() == {"a"}, "a failed step must stay un-marked so a re-run retries it"


def test_reboot_marks_the_step_so_resume_moves_past_it(tmp_path):
    steps = [Step("gate", lambda: (_ for _ in ()).throw(RebootRequired())),
             Step("after", lambda: None)]
    state = InstallState(tmp_path / "s.json")
    events, report = _recorder()
    with pytest.raises(RebootRequired):
        run_install(steps, state, report)
    assert state.completed() == {"gate"}, \
        "the gate is satisfied by the reboot itself; resume must not re-trigger it"
    assert any(e.status == "reboot" for e in events)


class FakeHost:
    def __init__(self, diagnosis, reboot=False):
        self._diagnosis = diagnosis
        self._reboot = reboot
        self.applied = []

    def preflight(self):
        return self._diagnosis

    def apply_remedy(self, remedy):
        self.applied.append(remedy)

    def reboot_required(self):
        return self._reboot


def test_preflight_raises_dead_end_with_the_users_instructions():
    host = FakeHost(Diagnosis([
        CheckResult("virtualization enabled", False,
                    fix="Restart into BIOS and enable Intel VT-x or AMD-V"),
    ]))
    with pytest.raises(DeadEnd, match="VT-x"):
        preflight_step(host)


def test_preflight_passes_when_only_fixable_checks_fail():
    host = FakeHost(Diagnosis([
        CheckResult("wsl features", False, fix="we enable it", remedy="enable_wsl_features"),
    ]))
    preflight_step(host)      # must not raise — step 2 handles this


def test_remediate_applies_only_fixable_remedies():
    host = FakeHost(Diagnosis([
        CheckResult("fine", True),
        CheckResult("wsl features", False, fix="x", remedy="enable_wsl_features"),
        CheckResult("wsl outdated", False, fix="y", remedy="update_wsl"),
    ]))
    remediate_step(host)
    assert host.applied == ["enable_wsl_features", "update_wsl"]


def test_remediate_does_nothing_when_everything_passes():
    host = FakeHost(Diagnosis([CheckResult("fine", True)]))
    remediate_step(host)
    assert host.applied == []


def test_reboot_gate_raises_only_when_the_provider_says_so():
    reboot_gate_step(FakeHost(Diagnosis([]), reboot=False))    # no raise
    with pytest.raises(RebootRequired):
        reboot_gate_step(FakeHost(Diagnosis([]), reboot=True))
