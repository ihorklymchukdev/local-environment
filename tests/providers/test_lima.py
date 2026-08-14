from pathlib import Path
from runtime.providers.lima import LimaProvider


class FakeRunner:
    def __init__(self, stdout=b"", returncode=0):
        self.calls = []
        self._out, self._rc = stdout, returncode

    def __call__(self, argv):
        self.calls.append(argv)
        class R:
            returncode = self._rc
            stdout = self._out
            stderr = b""
        return R()


def make(runner):
    return LimaProvider(name="runtime-vm", config=Path("/tmp/runtime.yaml"),
                        limactl="limactl", runner=runner)


def test_exec_uses_limactl_shell():
    r = FakeRunner(stdout=b"ok\n")
    make(r).exec(["uname", "-sr"])
    assert r.calls[-1] == ["limactl", "shell", "runtime-vm", "uname", "-sr"]


def test_exec_root_uses_sudo():
    r = FakeRunner()
    make(r).exec(["id", "-un"], root=True)
    assert r.calls[-1] == ["limactl", "shell", "runtime-vm", "sudo", "id", "-un"]


def test_create_calls_start_with_config():
    r = FakeRunner()
    make(r).create()
    assert r.calls[-1] == ["limactl", "start", "--name=runtime-vm",
                           "--tty=false", "/tmp/runtime.yaml"]


def test_stop_and_destroy():
    r = FakeRunner()
    p = make(r)
    p.stop()
    assert r.calls[-1] == ["limactl", "stop", "runtime-vm"]
    p.destroy()
    assert r.calls[-1] == ["limactl", "delete", "runtime-vm"]
