from pathlib import Path
from runtime.providers.wsl2 import Wsl2Provider


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


def make(runner):
    return Wsl2Provider(
        distro="runtime-vm",
        install_dir=Path("/tmp/inst"),
        rootfs=Path("/tmp/ubuntu.tar.gz"),
        wsl="wsl.exe",
        runner=runner,
    )


def test_exec_builds_passthrough_argv_and_decodes_utf8():
    r = FakeRunner(stdout=b"Linux 6.6\n")
    result = make(r).exec(["uname", "-sr"])
    assert r.calls[-1] == ["wsl.exe", "-d", "runtime-vm", "--", "uname", "-sr"]
    assert result.stdout == "Linux 6.6"
    assert result.ok is True


def test_exec_root_inserts_user_root():
    r = FakeRunner()
    make(r).exec(["id", "-un"], root=True)
    assert r.calls[-1] == ["wsl.exe", "-d", "runtime-vm", "-u", "root", "--", "id", "-un"]


def test_exists_true_when_distro_in_list():
    listing = "runtime-vm\r\nUbuntu\r\n".encode("utf-16-le")
    r = FakeRunner(stdout=listing)
    assert make(r).exists() is True
    assert r.calls[-1] == ["wsl.exe", "-l", "-q"]


def test_exists_false_when_absent():
    r = FakeRunner(stdout="Ubuntu\r\n".encode("utf-16-le"))
    assert make(r).exists() is False


def test_create_imports_then_enables_systemd_then_terminates():
    r = FakeRunner()
    make(r).create()
    argvs = r.calls
    assert argvs[0][:2] == ["wsl.exe", "--import"]
    assert argvs[0][2] == "runtime-vm"
    assert "/tmp/inst" in argvs[0][3]
    assert "/tmp/ubuntu.tar.gz" in argvs[0][4]
    assert argvs[0][-2:] == ["--version", "2"]
    # systemd fixup runs as root, writes wsl.conf
    assert any("-u" in a and "root" in a and "wsl.conf" in " ".join(a) for a in argvs)
    # ends by terminating so systemd takes effect
    assert argvs[-1] == ["wsl.exe", "--terminate", "runtime-vm"]


def test_stop_terminates_and_destroy_unregisters():
    r = FakeRunner()
    p = make(r)
    p.stop()
    assert r.calls[-1] == ["wsl.exe", "--terminate", "runtime-vm"]
    p.destroy()
    assert r.calls[-1] == ["wsl.exe", "--unregister", "runtime-vm"]
