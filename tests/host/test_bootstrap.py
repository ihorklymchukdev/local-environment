import pytest

from host.core.bootstrap import bootstrap, read_marker, BootstrapError
from host.core.provider import Completed
from host.core import constants


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


def test_every_asset_the_bootstrap_pushes_exists_on_disk():
    # The push list is read at run time, not import time, so a file deleted from
    # the repo surfaces as FileNotFoundError minutes into a user's install --
    # which is precisely how a stale traefik.yml push shipped once.
    from host.core.bootstrap import guest_assets
    for local, _remote in guest_assets():
        assert local.is_file(), f"bootstrap pushes a file that does not exist: {local}"


def test_bootstrap_pushes_the_stack_file_the_guest_script_brings_up():
    # bootstrap.sh runs `docker compose -f /opt/omelet/stack.yml up -d` and
    # aborts if the file is absent, so the two paths have to agree.
    p = FakeProvider(marker_value="")
    bootstrap(p)
    pushes = [" ".join(a) for a, _ in p.execs if "base64 -d" in " ".join(a)]
    assert any(w.rstrip().endswith(constants.GUEST_STACK) for w in pushes), \
        f"nothing was pushed to {constants.GUEST_STACK}"
    assert "services:" in _pushed_payload(p, constants.GUEST_STACK).decode()


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


# The upload writes *to* /opt/omelet/bin/bootstrap.sh, so only the `bash <path>`
# form (no -lc) identifies the script actually running.
SCRIPT_RUN = "bash /opt/omelet/bin/bootstrap.sh"


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


def _pushed_payload(provider, filename):
    """Decode what _push_file actually sent to the guest for `filename`."""
    import base64 as _b64
    for argv, _root in provider.execs:
        joined = " ".join(argv)
        if "base64 -d" in joined and joined.rstrip().endswith(filename):
            blob = joined.split("echo ", 1)[1].split(" |", 1)[0]
            return _b64.b64decode(blob)
    raise AssertionError(f"no push recorded for {filename}")


def test_push_file_strips_crlf_so_bash_can_read_the_script(tmp_path, monkeypatch):
    # A Windows checkout (core.autocrlf) turns bootstrap.sh into CRLF. Bash then
    # reads line 2 as `set -euo pipefail\r` and aborts with "invalid option
    # name" -- which is exactly how the first real Windows build failed.
    import host.core.bootstrap as bs

    crlf_assets = tmp_path / "guest"
    crlf_assets.mkdir()
    (crlf_assets / "bootstrap.sh").write_bytes(b"#!/usr/bin/env bash\r\nset -euo pipefail\r\n")
    (crlf_assets / "stack.yml").write_bytes(b"services:\r\n  agent:\r\n")
    monkeypatch.setattr(bs, "_ASSETS", crlf_assets)
    monkeypatch.setattr(bs, "_DEPLOY", crlf_assets)

    p = FakeProvider(marker_value="")
    bootstrap(p)

    script = _pushed_payload(p, "/opt/omelet/bin/bootstrap.sh")
    assert b"\r" not in script, "CRLF reached the Linux guest"
    assert script.splitlines()[1] == b"set -euo pipefail"
    assert b"\r" not in _pushed_payload(p, constants.GUEST_STACK)
