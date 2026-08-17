import pytest

from runtime.core.bootstrap import bootstrap, read_marker, BootstrapError
from runtime.core.provider import Completed
from runtime.core import constants


class FakeProvider:
    """Guest stand-in: a successful bootstrap.sh run writes the marker, as the
    real script does on its last line."""

    def __init__(self, marker_value="", fail_on=None, stderr="", writes_marker=True):
        self.execs = []
        self._marker = marker_value
        self._fail_on = fail_on
        self._stderr = stderr
        self._writes_marker = writes_marker

    def exec(self, argv, *, root=False):
        self.execs.append((argv, root))
        joined = " ".join(argv)
        if "cat" in argv and constants.BOOTSTRAP_MARKER in joined:
            return Completed(0 if self._marker else 1, self._marker, "")
        if self._fail_on and self._fail_on in joined:
            return Completed(1, "", self._stderr)
        if "bootstrap.sh" in joined and self._writes_marker:
            self._marker = str(constants.BOOTSTRAP_VERSION)
        return Completed(0, "", "")


def test_read_marker_returns_int_when_present():
    assert read_marker(FakeProvider(marker_value="1")) == 1


def test_read_marker_none_when_absent():
    assert read_marker(FakeProvider(marker_value="")) is None


def test_bootstrap_skips_when_marker_current():
    p = FakeProvider(marker_value=str(constants.BOOTSTRAP_VERSION))
    bootstrap(p)
    # only the marker read happened; the script was never run as root
    assert all("bootstrap.sh" not in " ".join(a) for a, _ in p.execs)


def test_bootstrap_runs_script_as_root_when_absent():
    p = FakeProvider(marker_value="")
    bootstrap(p)
    ran = [a for a, root in p.execs if root and "bootstrap.sh" in " ".join(a)]
    assert ran, "expected bootstrap.sh to run as root"


def test_bootstrap_runs_when_force_true():
    p = FakeProvider(marker_value=str(constants.BOOTSTRAP_VERSION))
    bootstrap(p, force=True)
    ran = [a for a, root in p.execs if root and "bootstrap.sh" in " ".join(a)]
    assert ran, "expected bootstrap.sh to run as root when force=True"


# The upload writes *to* /opt/runtime/bin/bootstrap.sh, so only the `bash <path>`
# form (no -lc) identifies the script actually running.
SCRIPT_RUN = "bash /opt/runtime/bin/bootstrap.sh"


def test_bootstrap_raises_with_guest_stderr_when_script_fails():
    p = FakeProvider(fail_on=SCRIPT_RUN,
                     stderr="E: Unable to locate package docker-ce")
    with pytest.raises(BootstrapError) as excinfo:
        bootstrap(p)
    assert "docker-ce" in str(excinfo.value)


def test_bootstrap_raises_when_push_fails_and_skips_the_script():
    p = FakeProvider(fail_on="base64 -d")
    with pytest.raises(BootstrapError):
        bootstrap(p)
    assert all(not " ".join(a).startswith(SCRIPT_RUN) for a, _ in p.execs), \
        "the script must not run when its own upload failed"


def test_bootstrap_raises_when_script_exits_zero_without_writing_marker():
    p = FakeProvider(writes_marker=False)
    with pytest.raises(BootstrapError, match="marker"):
        bootstrap(p)
