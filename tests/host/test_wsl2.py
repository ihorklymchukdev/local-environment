from pathlib import Path
from host.providers.wsl2 import Wsl2Provider


class FakeRunner:
    """Records argv, returns a scripted (returncode, stdout, stderr)."""
    def __init__(self, stdout=b"", stderr=b"", returncode=0):
        self.calls = []
        self._out, self._err, self._rc = stdout, stderr, returncode

    def __call__(self, argv):
        self.calls.append(argv)
        class R:
            returncode = self._rc
            stdout = self._out
            stderr = self._err
        return R()


def make(runner, install_dir=Path("/tmp/inst"), rootfs=Path("/tmp/ubuntu.tar.gz")):
    return Wsl2Provider(
        distro="omelet-vm",
        install_dir=install_dir,
        rootfs=rootfs,
        wsl="wsl.exe",
        runner=runner,
    )


def test_exec_builds_passthrough_argv_and_decodes_utf8():
    r = FakeRunner(stdout=b"Linux 6.6\n")
    result = make(r).exec(["uname", "-sr"])
    assert r.calls[-1] == ["wsl.exe", "-d", "omelet-vm", "--", "uname", "-sr"]
    assert result.stdout == "Linux 6.6"
    assert result.ok is True


def test_exec_root_inserts_user_root():
    r = FakeRunner()
    make(r).exec(["id", "-un"], root=True)
    assert r.calls[-1] == ["wsl.exe", "-d", "omelet-vm", "-u", "root", "--", "id", "-un"]


def test_exists_true_when_distro_in_list():
    listing = "omelet-vm\r\nUbuntu\r\n".encode("utf-16-le")
    r = FakeRunner(stdout=listing)
    assert make(r).exists() is True
    assert r.calls[-1] == ["wsl.exe", "-l", "-q"]


def test_exists_false_when_absent():
    r = FakeRunner(stdout="Ubuntu\r\n".encode("utf-16-le"))
    assert make(r).exists() is False


def test_create_imports_then_enables_systemd_then_terminates(tmp_path):
    rootfs = tmp_path / "ubuntu.tar.gz"
    rootfs.write_bytes(b"")
    install = tmp_path / "inst"
    r = FakeRunner()
    make(r, install_dir=install, rootfs=rootfs).create()
    argvs = r.calls
    assert argvs[0][:2] == ["wsl.exe", "--import"]
    assert argvs[0][2] == "omelet-vm"
    assert str(install) in argvs[0][3]
    assert str(rootfs) in argvs[0][4]
    assert argvs[0][-2:] == ["--version", "2"]
    # systemd fixup runs as root, writes wsl.conf
    assert any("-u" in a and "root" in a and "wsl.conf" in " ".join(a) for a in argvs)
    # ends by terminating so systemd takes effect
    assert argvs[-1] == ["wsl.exe", "--terminate", "omelet-vm"]


def test_create_rejects_a_rootfs_path_that_does_not_exist():
    r = FakeRunner()
    try:
        make(r, rootfs=Path("/tmp/definitely-not-here.wsl")).create()
        assert False, "expected FileNotFoundError"
    except FileNotFoundError as e:
        assert "definitely-not-here" in str(e)
    assert r.calls == [], "must not shell out to wsl.exe with a bad rootfs"


def test_create_raises_when_import_fails(tmp_path):
    rootfs = tmp_path / "ubuntu.tar.gz"
    rootfs.write_bytes(b"")
    r = FakeRunner(stderr="Invalid distro name".encode("utf-16-le"), returncode=1)
    try:
        make(r, install_dir=tmp_path / "inst", rootfs=rootfs).create()
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "Invalid distro name" in str(e)


def test_stop_terminates_and_destroy_unregisters():
    r = FakeRunner()
    p = make(r)
    p.stop()
    assert r.calls[-1] == ["wsl.exe", "--terminate", "omelet-vm"]
    p.destroy()
    assert r.calls[-1] == ["wsl.exe", "--unregister", "omelet-vm"]


class ScriptedRunner(FakeRunner):
    """Fails only the calls whose argv contains `fail_on`; everything else
    succeeds. Enough to fail one step of a multi-command operation."""

    def __init__(self, fail_on, stderr=b"", **kwargs):
        super().__init__(**kwargs)
        self._fail_on = fail_on
        self._fail_err = stderr

    def __call__(self, argv):
        self.calls.append(argv)
        failed = self._fail_on in " ".join(argv)
        err, out = self._fail_err, self._out

        class R:
            returncode = 1 if failed else 0
            stdout = b"" if failed else out
            stderr = err if failed else b""
        return R()


def _raises(call, needle):
    try:
        call()
    except RuntimeError as e:
        assert needle in str(e), str(e)
        return str(e)
    raise AssertionError(f"expected a RuntimeError mentioning {needle!r}")


def test_create_stops_when_the_systemd_write_fails(tmp_path):
    # Unchecked, systemd stays off and the only symptom is bootstrap dying
    # minutes later at `systemctl enable --now docker`.
    rootfs = tmp_path / "ubuntu.tar.gz"
    rootfs.write_bytes(b"")
    r = ScriptedRunner("wsl.conf", stderr=b"bash: /etc/wsl.conf: Read-only file system")
    provider = make(r, install_dir=tmp_path / "inst", rootfs=rootfs)

    message = _raises(provider.create, "systemd")
    assert "Read-only file system" in message, "the guest's own words must survive"
    assert not any("--terminate" in " ".join(a) for a in r.calls), \
        "a broken VM must not be reported as created"


def test_start_reports_a_distro_that_does_not_exist(tmp_path):
    r = ScriptedRunner("true", stderr="There is no distribution with the "
                                      "supplied name.".encode("utf-16-le"))
    _raises(make(r).start, "could not be started")


def test_stop_and_destroy_report_failures_instead_of_claiming_success():
    stop = ScriptedRunner("--terminate",
                          stderr="no distribution".encode("utf-16-le"))
    _raises(make(stop).stop, "could not be stopped")

    destroy = ScriptedRunner("--unregister",
                             stderr="no distribution".encode("utf-16-le"))
    _raises(make(destroy).destroy, "could not be removed")
