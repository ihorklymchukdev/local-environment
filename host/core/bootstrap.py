from __future__ import annotations

import base64
import posixpath
from pathlib import Path

from host.core import constants

_GUEST_DIR = f"{constants.GUEST_ROOT}/bin"
_GUEST_SCRIPT = f"{_GUEST_DIR}/bootstrap.sh"
_GUEST_AGENTS = f"{constants.GUEST_ROOT}/agents"
_SKILL = "skills/omelet-setup/SKILL.md"
# Repo root from source, sys._MEIPASS from a frozen build -- both layouts put
# the bundled assets under the same host/ and agent/ prefixes.
_ROOT = Path(__file__).resolve().parent.parent.parent
# stack.yml lives here rather than beside the agent because the agent never
# reads it and its image never contains it: it is the manifest the host pushes
# so a VM with no agent yet can start one.
_ASSETS = _ROOT / "host" / "provision"


class BootstrapError(RuntimeError):
    """A command run inside the guest failed; carries the guest's own output."""


def guest_assets() -> tuple[tuple[Path, str], ...]:
    """Every file pushed into the VM, paired with the guest path it lands at.

    Read at call time so tests can repoint the source directories, and exposed
    so `cli.selfcheck` verifies exactly this list -- a push whose source file no
    longer exists otherwise only surfaces minutes into a real install.
    """
    return (
        (_ASSETS / "bootstrap.sh", _GUEST_SCRIPT),
        (_ASSETS / "stack.yml", constants.GUEST_STACK),
        (_ASSETS / "guest" / "omelet.py", f"{_GUEST_DIR}/omelet"),
        (_ASSETS / "install-agents.sh", f"{_GUEST_DIR}/install-agents.sh"),
        (_ASSETS / "agents" / "omelet.md", f"{_GUEST_AGENTS}/omelet.md"),
        (_ASSETS / "agents" / _SKILL, f"{_GUEST_AGENTS}/{_SKILL}"),
    )


def _run(provider, argv, *, step: str):
    result = provider.exec(argv, root=True)
    if not result.ok:
        detail = (result.stderr or result.stdout).strip()
        raise BootstrapError(
            f"{step} failed inside the VM (exit {result.returncode})"
            + (f":\n{detail}" if detail else "."))
    return result


def read_marker(provider) -> int | None:
    r = provider.exec(["cat", constants.BOOTSTRAP_MARKER])
    if not r.ok or not r.stdout.strip():
        return None
    try:
        return int(r.stdout.strip())
    except ValueError:
        return None


def _push_file(provider, local: Path, remote: str) -> None:
    # base64 avoids quoting/newline issues over `wsl -- bash -lc`.
    # CRLF is stripped here as well as in .gitattributes: the installer is
    # frozen on Windows, so a checkout with core.autocrlf bundles CRLF assets,
    # and bash reads `set -euo pipefail\r` as an invalid option.
    payload = local.read_bytes().replace(b"\r\n", b"\n")
    encoded = base64.b64encode(payload).decode("ascii")
    _run(provider,
         ["bash", "-lc", f"mkdir -p {posixpath.dirname(remote)} && "
                         f"echo {encoded} | base64 -d > {remote}"],
         step=f"copying {local.name} to the VM")


# Absolute path for the same reason bootstrap.sh uses one: Docker Desktop's
# WSL integration puts its own docker CLI on PATH.
_DOCKER = "/usr/bin/docker"


def restart_agent(provider) -> None:
    """Recreate the agent container so it re-reads /opt/omelet/agent.token.

    The agent reads the token once, at startup, and `compose up -d` leaves an
    unchanged service running -- so re-provisioning alone cannot fix an agent
    that came up without a readable token and refuses every call since.
    """
    _run(provider, ["bash", "-lc",
                    f"{_DOCKER} compose -f {constants.GUEST_STACK} "
                    "up -d --force-recreate agent"],
         step="restarting the Omelet service in the VM")


def bootstrap(provider, *, force: bool = False) -> None:
    if not force and read_marker(provider) == constants.BOOTSTRAP_VERSION:
        return
    for local, remote in guest_assets():
        _push_file(provider, local, remote)
    _run(provider, ["bash", _GUEST_SCRIPT, str(constants.BOOTSTRAP_VERSION)],
         step="guest bootstrap (Docker + agent stack)")
    # The script writes the marker last, so a missing one means it exited
    # early without a non-zero status we could see.
    if read_marker(provider) != constants.BOOTSTRAP_VERSION:
        raise BootstrapError(
            "guest bootstrap reported success but left no version marker at "
            f"{constants.BOOTSTRAP_MARKER}")
