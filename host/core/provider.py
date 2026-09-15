from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol, runtime_checkable


@dataclass(frozen=True)
class Completed:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass(frozen=True)
class CheckResult:
    label: str
    ok: bool
    fix: str | None = None
    remedy: str | None = None


@dataclass(frozen=True)
class Diagnosis:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def blocking(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.ok]

    @property
    def dead_ends(self) -> list[CheckResult]:
        return [c for c in self.blocking if c.remedy is None]

    @property
    def fixable(self) -> list[CheckResult]:
        return [c for c in self.blocking if c.remedy is not None]


@dataclass(frozen=True)
class Runtime:
    """A program the VM platform needs that setup installs for the user.

    `None` from `provider.runtime()` means the platform ships it -- wsl.exe is
    part of Windows. A value means one step, named by `label`, calling `run`
    with the installer's fraction emitter.
    """
    label: str
    run: Callable[[Callable[[int, int], None] | None], None]


@runtime_checkable
class VmProvider(Protocol):
    def is_supported(self) -> Diagnosis: ...
    def exists(self) -> bool: ...
    def create(self) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def destroy(self) -> None: ...
    def exec(self, argv: list[str], *, root: bool = False) -> Completed: ...
    def forward(self, guest_port: int, host_port: int) -> None: ...
    def preflight(self) -> Diagnosis: ...
    def apply_remedy(self, remedy: str) -> None: ...
    def reboot_required(self) -> bool: ...
