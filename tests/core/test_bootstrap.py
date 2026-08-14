from runtime.core.bootstrap import bootstrap, read_marker
from runtime.core.provider import Completed
from runtime.core import constants


class FakeProvider:
    def __init__(self, marker_value=""):
        self.execs = []
        self._marker = marker_value

    def exec(self, argv, *, root=False):
        self.execs.append((argv, root))
        joined = " ".join(argv)
        if "cat" in argv and constants.BOOTSTRAP_MARKER in joined:
            return Completed(0 if self._marker else 1, self._marker, "")
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
