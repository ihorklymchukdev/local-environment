#!/usr/bin/env python3
"""`omelet` inside the VM: turns a folder in ~/projects into a routed project.

Pushed into the guest by the host and installed as /usr/local/bin/omelet, then
run by whichever coding agent the user works in. Stdlib only: it can import
neither host/ nor agent/, so the names it shares with them are declared again
here and held equal by tests/test_constants_agree.py.
"""
from __future__ import annotations

import argparse
import grp
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, TextIO

AGENT_PORT = 39099
GUEST_ROOT = "/opt/omelet"
GUEST_PROJECTS = f"{GUEST_ROOT}/projects"
GUEST_TOKEN = f"{GUEST_ROOT}/agent.token"
COMPOSE_FILE = "docker-compose.yml"
# The agent container's only credential shared with this VM.
DOCKER_GROUP = "docker"


class OmeletError(Exception):
    """One plain sentence for the user; `main` prints it and exits 1."""


def project_id_for(name: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", name.strip().lower()).strip("-")


def project_of(directory: Path, root: Path) -> Path | None:
    """The project folder holding `directory`, or None outside `root`.

    Resolved first, so ~/projects/x (a symlink) and /opt/omelet/projects/x are
    one folder; a subfolder counts, so `omelet up` from src/ runs the project.
    """
    root = root.resolve()
    path = directory.resolve()
    for candidate in (path, *path.parents):
        if candidate.parent == root:
            return candidate
    return None


def require_id(folder: Path) -> str:
    project_id = project_id_for(folder.name)
    if not project_id:
        raise OmeletError(
            f"The folder name '{folder.name}' cannot be a project name. "
            "Rename it using letters, digits and dashes.")
    if project_id != folder.name:
        # The agent derives the folder from the slugged id, so any other name
        # would register a different, empty folder.
        raise OmeletError(
            f"Rename the folder '{folder.name}' to '{project_id}' first, "
            "then run the command again.")
    return project_id


def docker_gid() -> int:
    try:
        return grp.getgrnam(DOCKER_GROUP).gr_gid
    except KeyError:
        raise OmeletError(
            "This VM has no docker group, so Omelet is not set up here. "
            "Run `omelet setup` on your computer.") from None


def prepare_overlay_dir(project: Path, gid: int) -> None:
    """Let the agent write .omelet/overlay.yml, the one file it writes here.

    It runs as a non-root member of the docker group, while a coding agent
    working as root leaves directories 755 and files 644.
    """
    omelet_dir = project / ".omelet"
    overlay = omelet_dir / "overlay.yml"
    try:
        omelet_dir.mkdir(exist_ok=True)
        os.chown(omelet_dir, -1, gid)
        os.chmod(omelet_dir, 0o2775)
        if overlay.exists():
            os.chown(overlay, -1, gid)
            os.chmod(overlay, 0o664)
    except PermissionError as e:
        raise OmeletError(
            f"Omelet could not make {omelet_dir} writable for itself "
            f"({e.strerror}). Run the command as the folder's owner.") from None
