"""The pieces of the host/agent seam that exist purely for authentication.

The full HTTP client (on `urllib.request`, following
`host/core/install.py::_default_http_get`) is built on top of this
separately. This module is deliberately small: reading the shared token and
shaping the header it goes in, nothing that talks HTTP.
"""

from __future__ import annotations

from .core import constants
from .core.provider import VmProvider


class AgentUnavailableError(RuntimeError):
    """No token could be read from the VM -- unprovisioned, or bootstrap
    never finished. Raised before any HTTP call is attempted so the first
    symptom a user sees is not a bare 401."""


def read_token(provider: VmProvider) -> str:
    """Read `/opt/omelet/agent.token` fresh, once, via `provider.exec()`.

    Never cached to the host filesystem: a copy at rest is a second secret to
    protect and a second thing to go stale after a VM rebuild. One `wsl.exe`
    round trip per CLI invocation is an acceptable price.

    Phase 3 replaces this shared, VM-wide token with a service-issued device
    token; this function is the one place that changes.
    """
    result = provider.exec(["cat", constants.GUEST_TOKEN], root=True)
    token = result.stdout.strip() if result.ok else ""
    if not token:
        raise AgentUnavailableError(
            "the VM has no agent token -- it may not be provisioned yet; "
            "run setup and try again")
    return token


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
