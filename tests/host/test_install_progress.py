"""A download step must be able to say how far along it is.

fetch() has taken an on_progress callback since it was written and nothing
ever passed one, so the installer's only long step reported nothing at all.
"""
from host.core.install import InstallState, Progress, Step, run_install


def _events(steps, tmp_path):
    seen = []
    run_install(steps, InstallState(tmp_path / "state.json"), seen.append)
    return seen


def test_a_progress_step_is_handed_an_emitter(tmp_path):
    def run(emit):
        emit(50, 200)
        emit(200, 200)

    seen = _events([Step("fetch_image", run, progress=True)], tmp_path)
    fractions = [e.fraction for e in seen if e.fraction is not None]
    assert fractions == [0.25, 1.0]
    assert all(e.step == "fetch_image" and e.status == "running"
               for e in seen if e.fraction is not None)


def test_a_plain_step_is_still_called_with_no_arguments(tmp_path):
    # Every existing step takes no arguments, and every test that builds a toy
    # step does too. Adding progress must not change that contract.
    seen = _events([Step("finish", lambda: "done")], tmp_path)
    assert [(e.step, e.status) for e in seen] == [("finish", "running"), ("finish", "done")]


def test_a_zero_length_download_reports_no_fraction(tmp_path):
    # Content-Length can be absent, and 0/0 must not raise inside the installer.
    seen = _events([Step("fetch_image", lambda emit: emit(0, 0), progress=True)], tmp_path)
    assert [e for e in seen if e.fraction is not None] == []


def test_progress_defaults_to_no_fraction():
    assert Progress("verify", "running").fraction is None
