from __future__ import annotations

import base64

# Absolute path: Docker Desktop's WSL integration puts its own docker CLI on
# PATH, and a bare `docker` would send this VM's projects to Desktop's engine.
DOCKER = "/usr/bin/docker"

from .constants import COMPOSE_FILE
from .project import Project, FAILED_TO_START, STARTED_OK, classify, overlay_yaml

# Every path here comes from the caller's project directory, never from
# constants: the agent writes uploads to `config.projects_root`, and a second
# source of truth would upload into one directory and run compose against
# another, silently. The directory is valid on both sides because /opt/omelet
# is bind-mounted into the agent at the identical path.


def _compose_argv(directory) -> list[str]:
    return [DOCKER, "compose",
            "-f", f"{directory}/{COMPOSE_FILE}",
            "-f", f"{directory}/.omelet/overlay.yml",
            "up", "-d"]


def _write_overlay(provider, project: Project, directory, domain: str):
    text = overlay_yaml(project, domain)
    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
    return provider.exec(["bash", "-lc",
                          f"mkdir -p {directory}/.omelet && echo {encoded} | "
                          f"base64 -d > {directory}/.omelet/overlay.yml"],
                         root=True)


def compose_up(provider, project: Project, directory, domain: str):
    """Returns (status, detail). `detail` carries the guest's own output when
    the stack did not start, so callers never have to report a bare status code
    that no one can act on. URLs are the API layer's job -- it is the only place
    that holds the configured edge port."""
    written = _write_overlay(provider, project, directory, domain)
    if not written.ok:
        # exec() never raises. Starting the stack anyway would produce a project
        # with no Traefik labels: no route, and no error naming the cause.
        return (FAILED_TO_START,
                (written.stderr or written.stdout).strip()
                or "could not write the Traefik overlay inside the VM")
    up = provider.exec(_compose_argv(directory), root=True)
    ps = provider.exec([DOCKER, "compose", "-f",
                        f"{directory}/{COMPOSE_FILE}",
                        "ps", "--format", "json"], root=True)
    status = classify(up, ps.stdout)
    detail = "" if status == STARTED_OK else (up.stderr or up.stdout or ps.stderr).strip()
    return status, detail


def compose_down(provider, directory):
    return provider.exec([DOCKER, "compose", "-f", f"{directory}/{COMPOSE_FILE}",
                          "-f", f"{directory}/.omelet/overlay.yml", "down"],
                         root=True)


def container_id(provider, directory, service: str) -> str:
    """Empty string when compose cannot resolve one — the project was never
    started, or the container is already gone. Callers hedge, they don't raise."""
    result = provider.exec([DOCKER, "compose", "-f",
                            f"{directory}/{COMPOSE_FILE}",
                            "ps", "-q", service], root=True)
    lines = result.stdout.split() if result.ok else []
    return lines[0] if lines else ""


def logs_argv(directory, service: str | None = None, *,
              follow: bool = False) -> list[str]:
    argv = [DOCKER, "compose", "-f", f"{directory}/{COMPOSE_FILE}",
            "logs", "--no-color"]
    if follow:
        argv.append("--follow")
    if service:
        argv.append(service)
    return argv


def project_logs(provider, directory, service: str | None = None):
    """Returns the `Completed`, not its stdout: compose exits non-zero when the
    project was never created or the daemon is down, and dropping that turned a
    real failure into an empty log listing."""
    return provider.exec(logs_argv(directory, service), root=True)
