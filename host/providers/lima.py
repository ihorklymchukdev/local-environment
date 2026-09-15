from __future__ import annotations

# UNVERIFIED: written for parity against the VmProvider contract; not run on
# macOS in this session. Command construction is unit-tested; live behavior
# (vz, rosetta, port forwarding) must be confirmed on an Apple Silicon host.

import os
import platform
import shutil
import subprocess
from pathlib import Path

from . import lima_install
from ..core.provider import Completed, Diagnosis, CheckResult, Runtime

LOOPBACK = "127.0.0.1"

# Homebrew installs limactl here and puts neither prefix on the PATH an app
# launched from Finder is given -- LaunchServices starts one with
# /usr/bin:/bin:/usr/sbin:/sbin, and a GUI process inherits no shell profile.
# `which limactl` answering yes in a terminal is therefore not the question the
# setup window is asking, which is how it came to tell a user who had just run
# `brew install lima` to install Lima.
BREW_PREFIXES = ("/opt/homebrew/bin", "/usr/local/bin")


def default_data_root() -> Path:
    """Everything the host keeps for itself on this platform: the VM directory,
    the download cache and the managed Lima. The single literal -- the provider
    factory's default_install_dir() is derived from it, so the two cannot
    disagree about where setup put limactl."""
    return Path.home() / ".local" / "share" / "omelet"


def find_limactl(name: str = "limactl", *, which=shutil.which,
                 prefixes=BREW_PREFIXES, managed: Path | None = None) -> str:
    """Absolute path to limactl, or `name` unchanged if it was not found.

    The managed copy wins whenever it exists: setup installs a pinned version,
    and every assumption LimaProvider makes about Lima's on-disk layout is an
    assumption about that version. A user's Homebrew Lima is never removed,
    never upgraded and never used once ours is there -- the fallback below
    exists for one case, a source checkout that has never run setup.
    """
    if os.sep in name:
        return name             # an explicit path: a test, or a bundled copy
    if managed is not None and os.access(managed, os.X_OK):
        return str(managed)
    found = which(name)
    if found:
        return found
    for prefix in prefixes:
        candidate = os.path.join(prefix, name)
        if os.access(candidate, os.X_OK):
            return candidate
    return name


def _default_runner(argv):
    return subprocess.run(argv, capture_output=True)


class LimaProvider:
    def __init__(self, name="omelet-vm", config: Path | None = None,
                 limactl="limactl", runner=_default_runner,
                 lima_home: Path | None = None, data_root: Path | None = None,
                 mac_ver=None):
        self.name = name
        self.config = Path(config) if config else None
        self.limactl = limactl
        self._run = runner
        self.lima_home = Path(lima_home) if lima_home else Path.home() / ".lima"
        self.data_root = Path(data_root) if data_root else default_data_root()
        # Injectable for the same reason Wsl2Provider's `facts` is: platform.mac_ver()
        # returns ('', ..., ...) on the Windows host this suite mostly runs on, so a
        # test exercising preflight()/is_supported() needs a real version to check
        # the >= 13 gate against.
        self._mac_ver = mac_ver or platform.mac_ver

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
        """What `omelet doctor` prints: the whole truth about this machine.

        Wider than preflight() on purpose, and the reverse of the WSL2
        provider, where preflight is the richer of the two. Setup installs Lima
        itself now, so preflight must not stop for it -- but a user running
        doctor still deserves to be told it is missing, and told that setup is
        what fixes it.
        """
        checks = list(self._os_checks())
        from shutil import which
        present = os.access(self.limactl, os.X_OK) or which(self.limactl) is not None
        checks.append(CheckResult(
            f"Lima {lima_install.LIMA_VERSION}", present,
            None if present else "run Omelet setup, which installs Lima for you"))
        return Diagnosis(checks)

    def _os_checks(self):
        release = self._mac_ver()[0]
        major = int(release.split(".")[0]) if release.split(".")[0].isdigit() else 0
        # vz, which omelet.yaml asks for, is macOS 13+. The .pkg refuses to
        # install below that; a source checkout has nothing stopping it.
        yield CheckResult(
            f"macOS 13 or newer (found {release or 'unknown'})", major >= 13,
            None if major >= 13 else
            "Omelet needs macOS 13 or newer; this Mac cannot run it")

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
        """What setup gates on before it installs anything. Only facts about
        this computer that no step can change."""
        return Diagnosis(list(self._os_checks()))

    def runtime(self) -> Runtime | None:
        return Runtime(f"Installing Lima {lima_install.LIMA_VERSION}",
                       lambda emit: lima_install.install(self.data_root,
                                                         on_progress=emit))

    def apply_remedy(self, remedy: str) -> None:
        raise ValueError(f"unknown remedy: {remedy}")

    def reboot_required(self) -> bool:
        return False   # no OS features to enable; Lima needs no restart

    # Nothing on macOS to turn on: the Virtualization framework is part of the
    # OS, so setup has no remediation step and no restart to gate on. Both
    # steps are dropped from the list rather than shown and skipped -- a Mac
    # user watching "Turning on Windows features" learns the wrong thing about
    # what this program is doing.
    remediable = False

    def register_resume(self, exe_path: str) -> None:
        """Nothing to resume: `reboot_required()` is always False here, so the
        gate never raises and setup never has to survive a restart."""

    def image(self):
        """No rootfs for the host to fetch.

        `images:` in omelet.yaml names the guest image and `limactl start`
        downloads and caches it, so the host has nothing to download and the
        install list drops its download step. None is the answer, not a URL
        nobody reads -- see `default_steps`.
        """
        return None

    @property
    def location(self) -> Path:
        """Where limactl keeps this VM. Not the host's install dir: Lima owns
        the disk image and its config, and `limactl delete` is what removes
        them."""
        return self.lima_home / self.name

    # Named for the user, in the finish message.
    terminal = "Terminal"
