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


# --- finding limactl when there is no shell PATH ---
#
# The setup window is an app, and an app launched from Finder is started by
# LaunchServices with PATH=/usr/bin:/bin:/usr/sbin:/sbin. Homebrew is on
# neither prefix, so `shutil.which` alone reported Lima missing on a machine
# where `brew install lima` had just succeeded.


def test_limactl_is_found_on_the_path_when_there_is_one():
    from host.providers.lima import find_limactl
    assert find_limactl(which=lambda name: "/somewhere/bin/limactl") \
        == "/somewhere/bin/limactl"


def test_limactl_is_found_in_the_homebrew_prefix_without_a_path(tmp_path):
    from host.providers.lima import find_limactl

    brew = tmp_path / "homebrew" / "bin"
    brew.mkdir(parents=True)
    binary = brew / "limactl"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)

    assert find_limactl(which=lambda name: None, prefixes=(str(brew),)) == str(binary)


def test_a_missing_limactl_comes_back_as_the_bare_name(tmp_path):
    # Not None: is_supported() is the one place that reports Lima missing, and
    # it reports it by failing to resolve this value.
    from host.providers.lima import find_limactl
    assert find_limactl(which=lambda name: None, prefixes=(str(tmp_path),)) == "limactl"


def test_an_explicit_path_is_never_second_guessed():
    from host.providers.lima import find_limactl
    assert find_limactl("/opt/omelet/limactl", which=lambda name: "/usr/bin/limactl") \
        == "/opt/omelet/limactl"


def test_a_resolved_path_still_satisfies_the_installed_check(tmp_path):
    # is_supported() runs shutil.which over whatever it was handed, and which()
    # accepts an absolute path by checking that file directly -- so resolving
    # the binary must not turn the check into a permanent failure.
    binary = tmp_path / "limactl"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)

    provider = LimaProvider(limactl=str(binary), runner=FakeRunner())
    assert provider.is_supported().ok
