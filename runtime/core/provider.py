from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


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


@dataclass(frozen=True)
class Diagnosis:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def blocking(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.ok]


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
