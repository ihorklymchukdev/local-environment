import pytest

from runtime.core.install import (
    InstallError, InstallState, Progress, RebootRequired, Step, run_install,
)


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
