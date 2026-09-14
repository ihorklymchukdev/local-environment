from __future__ import annotations

import base64
import os
import re

from host.core import constants


class BootstrapError(RuntimeError):
    """A command run inside the guest failed; carries the guest's own output."""


# Downloaded in full before it runs: `curl | bash` executes whatever arrived
# before a dropped connection. python3 covers a rootfs that ships without curl.
_STUB = """set -euo pipefail
if command -v curl >/dev/null 2>&1; then
  script="$(curl -fsSL "$1")" || { echo "could not download the Omelet installer from $1" >&2; exit 1; }
else
  script="$(python3 -c 'import sys, urllib.request; sys.stdout.write(urllib.request.urlopen(sys.argv[1], timeout=60).read().decode())' "$1")" \\
    || { echo "could not download the Omelet installer from $1" >&2; exit 1; }
fi
bash -c "$script"
"""
_STUB_PATH = "/tmp/omelet-bootstrap.sh"

# The command reaches the guest as one `bash -lc` argument through wsl.exe or
# ssh, where a space or quote would be parsed again.
_SHELL_SAFE = re.compile(r"[A-Za-z0-9._:/@+=-]+")


def _shell_safe(value: str, name: str) -> str:
    if not _SHELL_SAFE.fullmatch(value):
        raise BootstrapError(
            f"{name} contains characters the VM command line cannot carry: {value!r}")
    return value


def _run(provider, argv, *, step: str):
    result = provider.exec(argv, root=True)
    if not result.ok:
        detail = (result.stderr or result.stdout).strip()
        raise BootstrapError(
            f"{step} failed inside the VM (exit {result.returncode})"
            + (f":\n{detail}" if detail else "."))
    return result


def _installed(provider) -> bool:
    return provider.exec(["test", "-s", constants.ENGINE_MARKER], root=True).ok


def bootstrap(provider, *, source: str | None = None, repair: bool = False) -> None:
    """Install the engine in the VM unless it is already there.

    `repair` reinstalls regardless and tells the installer to keep the ref it
    has and recreate the agent container.
    """
    if not repair and _installed(provider):
        return
    url = _shell_safe(
        source or os.environ.get("OMELET_ENGINE_URL") or constants.ENGINE_URL,
        "OMELET_ENGINE_URL")
    assignments = []
    ref = os.environ.get("OMELET_ENGINE_REF")
    if ref:
        assignments.append(f"OMELET_ENGINE_REF={_shell_safe(ref, 'OMELET_ENGINE_REF')}")
    if repair:
        assignments.append("OMELET_ENGINE_REPAIR=1")
    encoded = base64.b64encode(_STUB.encode()).decode("ascii")
    command = " ".join([*assignments, "bash", _STUB_PATH, url])
    _run(provider,
         ["bash", "-lc", f"echo {encoded} | base64 -d > {_STUB_PATH} && {command}"],
         step="installing Omelet inside the VM")
    # The installer writes the marker last, so its absence means it stopped
    # early without a non-zero status reaching us.
    if not _installed(provider):
        raise BootstrapError(
            "the Omelet installer reported success but left no "
            f"{constants.ENGINE_MARKER}")
