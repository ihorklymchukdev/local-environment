from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


class InstallState:
    """Which steps have finished, so a resume or re-run skips them."""

    def __init__(self, path):
        self._path = Path(path)

    def completed(self) -> set[str]:
        try:
            data = json.loads(self._path.read_text())
        except (OSError, json.JSONDecodeError):
            return set()
        steps = data.get("completed", [])
        return set(steps) if isinstance(steps, list) else set()

    def mark(self, step: str) -> None:
        done = self.completed()
        done.add(step)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps({"completed": sorted(done)}))

    def clear(self) -> None:
        self._path.unlink(missing_ok=True)


@dataclass(frozen=True)
class Progress:
    step: str
    status: str          # running | done | skipped | failed | reboot
    message: str = ""


@dataclass(frozen=True)
class Step:
    name: str
    run: Callable[[], None]


class RebootRequired(Exception):
    """The machine must restart before the remaining steps can run."""


class InstallError(RuntimeError):
    def __init__(self, step: str, message: str):
        super().__init__(f"{step}: {message}")
        self.step = step
        self.message = message


def run_install(steps: list[Step], state: InstallState,
                report: Callable[[Progress], None]) -> None:
    done = state.completed()
    for step in steps:
        if step.name in done:
            report(Progress(step.name, "skipped"))
            continue
        report(Progress(step.name, "running"))
        try:
            step.run()
        except RebootRequired:
            # The reboot itself satisfies the gate; resuming must step past it.
            state.mark(step.name)
            report(Progress(step.name, "reboot"))
            raise
        except Exception as e:
            report(Progress(step.name, "failed", str(e)))
            raise InstallError(step.name, str(e)) from e
        state.mark(step.name)
        report(Progress(step.name, "done"))
