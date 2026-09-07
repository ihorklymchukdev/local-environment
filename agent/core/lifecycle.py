from __future__ import annotations

import base64

from . import constants

# Absolute path: Docker Desktop's WSL integration puts its own docker CLI on
# PATH, and a bare `docker` would send this VM's projects to Desktop's engine.
DOCKER = "/usr/bin/docker"
from .project import Project, FAILED_TO_START, STARTED_OK, classify, overlay_yaml


def _guest_dir(project_id: str) -> str:
    return f"{constants.GUEST_PROJECTS}/{project_id}"


def _compose_argv(project_id: str) -> list[str]:
    d = _guest_dir(project_id)
    return [DOCKER, "compose",
            "-f", f"{d}/docker-compose.yml",
            "-f", f"{d}/.omelet/overlay.yml",
            "up", "-d"]


def _write_overlay(provider, project: Project, domain: str):
    d = _guest_dir(project.id)
    text = overlay_yaml(project, domain)
    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
    return provider.exec(["bash", "-lc",
                          f"mkdir -p {d}/.omelet && echo {encoded} | base64 -d "
                          f"> {d}/.omelet/overlay.yml"], root=True)


def _urls(project: Project, domain: str) -> list[str]:
    from .overlay import host_for
    return [f"http://{host_for(project.id, w, domain)}:{constants.EDGE_PORT}"
            for w in project.webs]


def compose_up(provider, project: Project, local_dir, domain: str):
    """Returns (status, urls, detail). `detail` carries the guest's own output
    when the stack did not start, so callers never have to report a bare status
    code that no one can act on."""
    written = _write_overlay(provider, project, domain)
    if not written.ok:
        # exec() never raises. Starting the stack anyway would produce a project
        # with no Traefik labels: no route, and no error naming the cause.
        return (FAILED_TO_START, _urls(project, domain),
                (written.stderr or written.stdout).strip()
                or "could not write the Traefik overlay inside the VM")
    up = provider.exec(_compose_argv(project.id), root=True)
    ps = provider.exec([DOCKER, "compose", "-f",
                        f"{_guest_dir(project.id)}/docker-compose.yml",
                        "ps", "--format", "json"], root=True)
    status = classify(up, ps.stdout)
    detail = "" if status == STARTED_OK else (up.stderr or up.stdout or ps.stderr).strip()
    return status, _urls(project, domain), detail


def compose_down(provider, project_id: str):
    d = _guest_dir(project_id)
    return provider.exec([DOCKER, "compose", "-f", f"{d}/docker-compose.yml",
                          "-f", f"{d}/.omelet/overlay.yml", "down"], root=True)


def container_id(provider, project_id: str, service: str) -> str:
    """Empty string when compose cannot resolve one — the project was never
    started, or the container is already gone. Callers hedge, they don't raise."""
    result = provider.exec([DOCKER, "compose", "-f",
                            f"{_guest_dir(project_id)}/docker-compose.yml",
                            "ps", "-q", service], root=True)
    lines = result.stdout.split() if result.ok else []
    return lines[0] if lines else ""


def logs_argv(project_id: str, service: str | None = None, *,
              follow: bool = False) -> list[str]:
    d = _guest_dir(project_id)
    argv = [DOCKER, "compose", "-f", f"{d}/docker-compose.yml", "logs", "--no-color"]
    if follow:
        argv.append("--follow")
    if service:
        argv.append(service)
    return argv


def project_logs(provider, project_id: str, service: str | None = None):
    """Returns the `Completed`, not its stdout: compose exits non-zero when the
    project was never created or the daemon is down, and dropping that turned a
    real failure into an empty log listing."""
    return provider.exec(logs_argv(project_id, service), root=True)
