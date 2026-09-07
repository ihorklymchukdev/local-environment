from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Matches the bare distribution name off the front of a PEP 508 requirement
# string, e.g. "uvicorn[standard]>=0.30" -> "uvicorn".
_NAME_RE = re.compile(r"[A-Za-z0-9_.-]+")


def _dependency_names() -> set[str]:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    deps = data["project"]["dependencies"]
    names = set()
    for dep in deps:
        match = _NAME_RE.match(dep)
        assert match, f"could not parse dependency name from {dep!r}"
        names.add(match.group(0).lower())
    return names


def test_host_dependencies_exclude_web_framework():
    # The host ships as a PyInstaller-frozen binary; every declared dependency
    # lands in it. fastapi/uvicorn belong to the agent's Docker image only.
    names = _dependency_names()
    assert "fastapi" not in names
    assert "uvicorn" not in names
