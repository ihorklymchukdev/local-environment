"""Is this machine set up? Asked cheaply, and answered without raising.

The setup window calls `probe()` before it draws its first screen, to decide
whether to open on a status screen or run install. `host.client` is imported
lazily inside `probe()`, matching `host/core/install.py`: importing it at
module level would drag the HTTP client into every import of this module.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import constants


@dataclass(frozen=True)
class Readiness:
    """What the window knows before it draws anything.

    Every field is a fact it managed to establish; `problem` holds the first
    one it could not, in the words whoever refused gave. Nothing here raises --
    a probe that threw would leave the window with nothing to show at all.
    """
    vm_exists: bool = False
    vm_reachable: bool = False
    engine_version: str | None = None
    agent_api: int | None = None
    problem: str = ""

    @property
    def ready(self) -> bool:
        return (self.vm_exists and self.vm_reachable
                and bool(self.engine_version)
                and self.agent_api in constants.SUPPORTED_API)


def _default_client_factory(provider):
    from host.client import AgentClient
    return AgentClient.for_provider(provider)


def probe(provider, *, client_factory=None) -> Readiness:
    """Ask the three questions that decide which screen opens.

    `vm_reachable` is `exec(["true"]).ok` rather than a new provider member for
    "is it running": reaching the guest is the fact that matters, both
    platforms answer it identically, and the Protocol already offers `exec`.

    Wrapped in one broad `except`: a provider that throws (a missing
    `limactl`, say) must come back as a fact in `problem`, not as a crash in
    the caller that hasn't drawn anything yet.
    """
    client_factory = client_factory or _default_client_factory
    try:
        if not provider.exists():
            return Readiness()
        if not provider.exec(["true"]).ok:
            return Readiness(vm_exists=True)
        marker = provider.exec(["cat", constants.ENGINE_MARKER])
        engine = marker.stdout.strip() if marker.ok else ""
        if not engine:
            return Readiness(vm_exists=True, vm_reachable=True)
        try:
            api = client_factory(provider).health().get("api", 1)
        except Exception as e:
            return Readiness(vm_exists=True, vm_reachable=True,
                              engine_version=engine, problem=f"{e}")
        return Readiness(vm_exists=True, vm_reachable=True,
                          engine_version=engine, agent_api=api)
    except Exception as e:
        return Readiness(problem=f"{e}")
