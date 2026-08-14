from __future__ import annotations

import subprocess
from pathlib import Path

from ..core.provider import Completed, Diagnosis
from .wsl_encoding import decode_wsl
from .wsl_checks import diagnose_wsl2


def _default_runner(argv):
    return subprocess.run(argv, capture_output=True)


class Wsl2Provider:
    def __init__(self, distro="runtime-vm", install_dir: Path | None = None,
                 rootfs: Path | None = None, wsl="wsl.exe", runner=_default_runner):
        self.distro = distro
        self.install_dir = Path(install_dir) if install_dir else None
        self.rootfs = Path(rootfs) if rootfs else None
        self.wsl = wsl
        self._run = runner

    # --- wsl.exe's own output is UTF-16LE ---
    def _meta(self, args: list[str]) -> Completed:
        p = self._run([self.wsl, *args])
        return Completed(p.returncode, decode_wsl(p.stdout), decode_wsl(p.stderr))

    def is_supported(self) -> Diagnosis:
        return diagnose_wsl2(self._run, self.wsl)

    def exists(self) -> bool:
        out = self._meta(["-l", "-q"]).stdout
        return self.distro in [line.strip() for line in out.splitlines()]

    def create(self) -> None:
        if self.install_dir is None or self.rootfs is None:
            raise ValueError("install_dir and rootfs are required to create the VM")
        self.install_dir.mkdir(parents=True, exist_ok=True)
        self._meta(["--import", self.distro, str(self.install_dir),
                    str(self.rootfs), "--version", "2"])
        # systemd is off by default in WSL; docker.service needs it.
        self.exec(["bash", "-lc", "printf '[boot]\\nsystemd=true\\n' > /etc/wsl.conf"],
                  root=True)
        self.stop()  # --terminate so the wsl.conf change takes effect on next boot

    def start(self) -> None:
        # Running any command boots the distro.
        self.exec(["true"])

    def stop(self) -> None:
        self._meta(["--terminate", self.distro])

    def destroy(self) -> None:
        self._meta(["--unregister", self.distro])

    def exec(self, argv: list[str], *, root: bool = False) -> Completed:
        base = [self.wsl, "-d", self.distro]
        if root:
            base += ["-u", "root"]
        base += ["--", *argv]
        p = self._run(base)
        # command passthrough is UTF-8
        return Completed(p.returncode,
                         p.stdout.decode("utf-8", "replace").strip("\n"),
                         p.stderr.decode("utf-8", "replace").strip("\n"))

    def forward(self, guest_port: int, host_port: int) -> None:
        # WSL2 localhostForwarding surfaces guest 0.0.0.0:<port> on host
        # localhost:<same port>. The edge port is chosen equal on both sides,
        # so no action is required here. Distinct raw-TCP forwards
        # (guest_port != host_port) are added in a later milestone via netsh.
        if guest_port != host_port:
            raise NotImplementedError(
                "distinct-port forwarding on WSL2 is not part of the PoC slice")
