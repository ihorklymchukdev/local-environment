from __future__ import annotations

import base64
import io
import tarfile
from pathlib import Path

from . import constants

# Absolute path: Docker Desktop's WSL integration puts its own docker CLI on
# PATH, and a bare `docker` would send this VM's projects to Desktop's engine.
DOCKER = "/usr/bin/docker"
from .project import Project, classify, overlay_yaml


def _guest_dir(project_id: str) -> str:
    return f"{constants.GUEST_PROJECTS}/{project_id}"


def _compose_argv(project_id: str) -> list[str]:
    d = _guest_dir(project_id)
    return [DOCKER, "compose",
            "-f", f"{d}/docker-compose.yml",
            "-f", f"{d}/.runtime/overlay.yml",
            "up", "-d"]


def push_project(provider, project_id: str, local_dir) -> None:
    """Tar the local project and unpack it inside the guest (never on host)."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for item in Path(local_dir).iterdir():
            tar.add(item, arcname=item.name)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    d = _guest_dir(project_id)
    provider.exec(["bash", "-lc",
                   f"mkdir -p {d} && echo {encoded} | base64 -d | "
                   f"tar -xzf - -C {d}"], root=True)


def _write_overlay(provider, project: Project, domain: str) -> None:
    d = _guest_dir(project.id)
    text = overlay_yaml(project, domain)
    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
    provider.exec(["bash", "-lc",
                   f"mkdir -p {d}/.runtime && echo {encoded} | base64 -d "
                   f"> {d}/.runtime/overlay.yml"], root=True)


def _urls(project: Project, domain: str) -> list[str]:
    from .overlay import host_for
    return [f"http://{host_for(project.id, w, domain)}:{constants.EDGE_PORT}"
            for w in project.webs]


def compose_up(provider, project: Project, local_dir, domain: str):
    _write_overlay(provider, project, domain)
    up = provider.exec(_compose_argv(project.id), root=True)
    ps = provider.exec([DOCKER, "compose", "-f",
                        f"{_guest_dir(project.id)}/docker-compose.yml",
                        "ps", "--format", "json"], root=True)
    status = classify(up, ps.stdout)
    return status, _urls(project, domain)


def compose_down(provider, project_id: str):
    d = _guest_dir(project_id)
    return provider.exec([DOCKER, "compose", "-f", f"{d}/docker-compose.yml",
                          "-f", f"{d}/.runtime/overlay.yml", "down"], root=True)


def project_logs(provider, project_id: str, service: str | None = None) -> str:
    d = _guest_dir(project_id)
    argv = [DOCKER, "compose", "-f", f"{d}/docker-compose.yml", "logs", "--no-color"]
    if service:
        argv.append(service)
    return provider.exec(argv, root=True).stdout
