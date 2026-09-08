from __future__ import annotations

# UNVERIFIED: written for parity against the VmProvider contract; not run on
# macOS in this session. Command construction is unit-tested; live behavior
# (vz, rosetta, port forwarding) must be confirmed on an Apple Silicon host.

import subprocess
from pathlib import Path

from ..core.provider import Completed, Diagnosis, CheckResult

LOOPBACK = "127.0.0.1"


def _default_runner(argv):
    return subprocess.run(argv, capture_output=True)


class LimaProvider:
    def __init__(self, name="omelet-vm", config: Path | None = None,
                 limactl="limactl", runner=_default_runner,
                 lima_home: Path | None = None):
        self.name = name
        self.config = Path(config) if config else None
        self.limactl = limactl
        self._run = runner
        self.lima_home = Path(lima_home) if lima_home else Path.home() / ".lima"

    def _spawn(self, argv: list[str]) -> Completed:
        p = self._run(argv)
        return Completed(p.returncode,
                         (p.stdout or b"").decode("utf-8", "replace").strip("\n"),
                         (p.stderr or b"").decode("utf-8", "replace").strip("\n"))

    def _cmd(self, args: list[str]) -> Completed:
        return self._spawn([self.limactl, *args])

    @staticmethod
    def _require(result: Completed, what: str) -> Completed:
        """Same contract as the WSL2 provider's: `_cmd()` returns a `Completed`
        and never raises, so a dropped result reports success for a VM that was
        never created. A caller must not be able to tell which platform it is
        on, and that includes how loudly a failure arrives."""
        if result.ok:
            return result
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"{what} (exit {result.returncode})"
                           + (f": {detail}" if detail else "."))

    def is_supported(self) -> Diagnosis:
        from shutil import which
        present = which(self.limactl) is not None
        return Diagnosis([CheckResult(
            "limactl installed", present,
            None if present else "install Lima (brew install lima) or bundle limactl")])

    def exists(self) -> bool:
        out = self._cmd(["list", "--quiet"]).stdout
        return self.name in [line.strip() for line in out.splitlines()]

    def create(self) -> None:
        if self.config is None:
            raise ValueError("config path is required to create the VM")
        self._require(
            self._cmd(["start", f"--name={self.name}", "--tty=false", str(self.config)]),
            f"the virtual machine '{self.name}' could not be created")

    def start(self) -> None:
        self._require(self._cmd(["start", self.name]),
                      f"the virtual machine '{self.name}' could not be started")

    def stop(self) -> None:
        self._require(self._cmd(["stop", self.name]),
                      f"the virtual machine '{self.name}' could not be stopped")

    def destroy(self) -> None:
        self._require(self._cmd(["delete", self.name]),
                      f"the virtual machine '{self.name}' could not be removed")

    def exec(self, argv: list[str], *, root: bool = False) -> Completed:
        prefix = ["sudo", *argv] if root else list(argv)
        return self._cmd(["shell", self.name, *prefix])

    # --- port forwarding ---
    #
    # Lima keeps an ssh control master for every running VM, and writes the
    # config that reaches it next to the VM's own state. `ssh -O forward` asks
    # that existing connection for one more tunnel, so there is no daemon to
    # supervise and nothing to clean up if the host process goes away. No
    # elevation: these are host ports the user already owns.

    def _ssh_config(self) -> Path:
        return self.lima_home / self.name / "ssh.config"

    def _control(self, verb: str, guest_port: int, host_port: int) -> Completed:
        return self._spawn(["ssh", "-F", str(self._ssh_config()),
                            "-O", verb, "-L", f"{host_port}:{LOOPBACK}:{guest_port}",
                            f"lima-{self.name}"])

    def forward(self, guest_port: int, host_port: int) -> None:
        if guest_port == host_port:
            # Declared in omelet.yaml's portForwards and set up when the VM
            # starts; asking for it again would only fail as a duplicate.
            return
        # `-O forward` fails on a tunnel that already exists, and says so only
        # in prose, so cancelling first makes the pair idempotent by
        # construction rather than by matching an error string.
        self._control("cancel", guest_port, host_port)
        self._require(
            self._control("forward", guest_port, host_port),
            f"port {host_port} could not be forwarded to {guest_port} in the VM")

    def unforward(self, guest_port: int, host_port: int) -> None:
        if guest_port == host_port:
            return
        # Not checked: ssh exits non-zero for a tunnel that is not there, and
        # releasing a forward nobody added is the expected case on cleanup.
        self._control("cancel", guest_port, host_port)

    def forwards(self) -> list[tuple[int, int]]:
        """Always empty, and that is the answer rather than a gap.

        The tunnels live in the control master, which dies with the VM, so a
        restart cannot leak one and there is nothing to release. The WSL2 twin
        has to enumerate because netsh stores its table in the registry.
        """
        return []

    def preflight(self) -> Diagnosis:
        return self.is_supported()

    def apply_remedy(self, remedy: str) -> None:
        raise ValueError(f"unknown remedy: {remedy}")

    def reboot_required(self) -> bool:
        return False   # no OS features to enable; Lima needs no restart
