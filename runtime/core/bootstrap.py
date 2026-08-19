from __future__ import annotations

import base64
from pathlib import Path

from . import constants

_GUEST_DIR = "/opt/runtime/bin"
_GUEST_SCRIPT = f"{_GUEST_DIR}/bootstrap.sh"
_GUEST_TRAEFIK = f"{_GUEST_DIR}/traefik.yml"
_ASSETS = Path(__file__).resolve().parent.parent / "guest"


class BootstrapError(RuntimeError):
    """A command run inside the guest failed; carries the guest's own output."""


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
         ["bash", "-lc", f"mkdir -p {_GUEST_DIR} && "
                         f"echo {encoded} | base64 -d > {remote}"],
         step=f"copying {local.name} to the VM")


def bootstrap(provider, *, force: bool = False) -> None:
    if not force and read_marker(provider) == constants.BOOTSTRAP_VERSION:
        return
    _push_file(provider, _ASSETS / "bootstrap.sh", _GUEST_SCRIPT)
    _push_file(provider, _ASSETS / "traefik.yml", _GUEST_TRAEFIK)
    _run(provider, ["bash", _GUEST_SCRIPT, str(constants.BOOTSTRAP_VERSION)],
         step="guest bootstrap (Docker + Traefik install)")
    # The script writes the marker last, so a missing one means it exited
    # early without a non-zero status we could see.
    if read_marker(provider) != constants.BOOTSTRAP_VERSION:
        raise BootstrapError(
            "guest bootstrap reported success but left no version marker at "
            f"{constants.BOOTSTRAP_MARKER}")
