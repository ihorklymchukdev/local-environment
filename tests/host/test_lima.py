from pathlib import Path
from host.providers.lima import LimaProvider


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
    return LimaProvider(name="omelet-vm", config=Path("/tmp/omelet.yaml"),
                        limactl="limactl", runner=runner)


def test_exec_uses_limactl_shell():
    r = FakeRunner(stdout=b"ok\n")
    make(r).exec(["uname", "-sr"])
    assert r.calls[-1] == ["limactl", "shell", "omelet-vm", "uname", "-sr"]


def test_exec_root_uses_sudo():
    r = FakeRunner()
    make(r).exec(["id", "-un"], root=True)
    assert r.calls[-1] == ["limactl", "shell", "omelet-vm", "sudo", "id", "-un"]


def test_create_calls_start_with_config():
    r = FakeRunner()
    make(r).create()
    assert r.calls[-1] == ["limactl", "start", "--name=omelet-vm",
                           "--tty=false", "/tmp/omelet.yaml"]


def test_a_failed_vm_command_raises_instead_of_reporting_success():
    # `_cmd()` returns a Completed and never raises, so an unchecked result is
    # a silent success -- `omelet vm start` printing "VM started." for a VM
    # limactl refused to boot. The WSL2 provider learned this the hard way.
    import pytest

    with pytest.raises(RuntimeError, match="could not be started"):
        make(FakeRunner(returncode=1)).start()
    with pytest.raises(RuntimeError, match="could not be created"):
        make(FakeRunner(returncode=1)).create()


def test_stop_and_destroy():
    r = FakeRunner()
    p = make(r)
    p.stop()
    assert r.calls[-1] == ["limactl", "stop", "omelet-vm"]
    p.destroy()
    assert r.calls[-1] == ["limactl", "delete", "omelet-vm"]


def test_the_lima_config_forwards_exactly_the_ports_the_host_dials():
    # The literals in omelet.yaml are the only thing making the guest sockets
    # reachable from the host. Both are declared equal on the two sides on
    # purpose; a distinct-port forward is made at runtime over ssh instead and
    # never belongs in this file. Held against the constants, not against
    # another copy of the literals.
    import re
    from pathlib import Path

    from host.core import constants

    config = (Path(__file__).resolve().parents[2] / "host" / "providers"
              / "omelet.yaml").read_text()
    pairs = {(int(g), int(h)) for g, h in re.findall(
        r"guestPort:\s*(\d+)\s*\n\s*hostPort:\s*(\d+)", config)}
    assert pairs == {(constants.EDGE_PORT, constants.EDGE_PORT),
                     (constants.AGENT_PORT, constants.AGENT_PORT)}
