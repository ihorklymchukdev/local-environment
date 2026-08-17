from __future__ import annotations

import json
from pathlib import Path


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
