from runtime.core.install import InstallState


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
