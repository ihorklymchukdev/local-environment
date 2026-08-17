from __future__ import annotations

# UNVERIFIED: written for parity against the VmProvider contract; not run on
# macOS in this session. Command construction is unit-tested; live behavior
# (vz, rosetta, port forwarding) must be confirmed on an Apple Silicon host.

import subprocess
from pathlib import Path

from ..core.provider import Completed, Diagnosis, CheckResult


def _default_runner(argv):
    return subprocess.run(argv, capture_output=True)


class LimaProvider:
    def __init__(self, name="runtime-vm", config: Path | None = None,
                 limactl="limactl", runner=_default_runner):
        self.name = name
        self.config = Path(config) if config else None
        self.limactl = limactl
        self._run = runner

    def _cmd(self, args: list[str]) -> Completed:
        p = self._run([self.limactl, *args])
        return Completed(p.returncode,
                         p.stdout.decode("utf-8", "replace").strip("\n"),
                         (p.stderr or b"").decode("utf-8", "replace").strip("\n"))

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
        self._cmd(["start", f"--name={self.name}", "--tty=false", str(self.config)])

    def start(self) -> None:
        self._cmd(["start", self.name])

    def stop(self) -> None:
        self._cmd(["stop", self.name])

    def destroy(self) -> None:
        self._cmd(["delete", self.name])

    def exec(self, argv: list[str], *, root: bool = False) -> Completed:
        prefix = ["sudo", *argv] if root else list(argv)
        return self._cmd(["shell", self.name, *prefix])

    def forward(self, guest_port: int, host_port: int) -> None:
        # Declared in runtime.yaml portForwards; nothing to do at runtime for
        # the edge port. Dynamic forwards are a later milestone.
        if guest_port != host_port:
            raise NotImplementedError(
                "distinct-port forwarding on Lima is not part of the PoC slice")

    def preflight(self) -> Diagnosis:
        return self.is_supported()

    def apply_remedy(self, remedy: str) -> None:
        raise ValueError(f"unknown remedy: {remedy}")

    def reboot_required(self) -> bool:
        return False   # no OS features to enable; Lima needs no restart
