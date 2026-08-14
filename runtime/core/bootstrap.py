from __future__ import annotations

import base64
from pathlib import Path

from . import constants

_GUEST_DIR = "/opt/runtime/bin"
_GUEST_SCRIPT = f"{_GUEST_DIR}/bootstrap.sh"
_GUEST_TRAEFIK = f"{_GUEST_DIR}/traefik.yml"
_ASSETS = Path(__file__).resolve().parent.parent / "guest"


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
    encoded = base64.b64encode(local.read_bytes()).decode("ascii")
    provider.exec(
        ["bash", "-lc", f"mkdir -p {_GUEST_DIR} && "
                        f"echo {encoded} | base64 -d > {remote}"],
        root=True,
    )


def bootstrap(provider, *, force: bool = False) -> None:
    if not force and read_marker(provider) == constants.BOOTSTRAP_VERSION:
        return
    _push_file(provider, _ASSETS / "bootstrap.sh", _GUEST_SCRIPT)
    _push_file(provider, _ASSETS / "traefik.yml", _GUEST_TRAEFIK)
    provider.exec(["bash", _GUEST_SCRIPT, str(constants.BOOTSTRAP_VERSION)], root=True)
