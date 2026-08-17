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
        except DeadEnd as e:
            report(Progress(step.name, "failed", str(e)))
            raise
        except Exception as e:
            report(Progress(step.name, "failed", str(e)))
            raise InstallError(step.name, str(e)) from e
        state.mark(step.name)
        report(Progress(step.name, "done"))


class DeadEnd(RuntimeError):
    """A blocking check no code can fix — the user must act."""


def preflight_step(provider) -> None:
    diagnosis = provider.preflight()
    dead = diagnosis.dead_ends
    if dead:
        raise DeadEnd("\n".join(
            f"{c.label}: {c.fix}" if c.fix else c.label for c in dead))


def remediate_step(provider) -> None:
    for check in provider.preflight().fixable:
        provider.apply_remedy(check.remedy)


def reboot_gate_step(provider) -> None:
    if provider.reboot_required():
        raise RebootRequired()


class VerificationFailed(RuntimeError):
    """The smoke-test project did not serve a successful response."""


def _default_http_get(url: str) -> int:
    from urllib.request import urlopen
    with urlopen(url, timeout=30) as response:
        return response.status


def verify_step(provider, template_dir, domain: str, *,
                http_get=_default_http_get) -> None:
    """Run the bundled template end to end and require HTTP 200."""
    import yaml

    from . import constants
    from .lifecycle import compose_down, compose_up, push_project
    from .project import STARTED_OK, load_project

    template_dir = Path(template_dir)
    compose = yaml.safe_load((template_dir / "docker-compose.yml").read_text()) or {}
    project = load_project(compose, None, template_dir.name)
    try:
        push_project(provider, project.id, template_dir)
        status, urls = compose_up(provider, project, template_dir, domain)
        if status != STARTED_OK:
            raise VerificationFailed(f"smoke-test project status: {status}")
        try:
            code = http_get(urls[0])
        except Exception as e:
            raise VerificationFailed(f"{urls[0]} did not respond: {e}") from e
        if code != 200:
            raise VerificationFailed(f"{urls[0]} returned HTTP {code}, expected 200")
    finally:
        compose_down(provider, project.id)


def default_steps(provider, *, cache_dir, template_dir, domain,
                  exe_path: str) -> list[Step]:
    from .download import fetch

    def fetch_image():
        image = provider.image()
        dest = Path(cache_dir) / image.url.rsplit("/", 1)[-1]
        provider.rootfs = fetch(image, dest)

    def gate():
        if provider.reboot_required():
            provider.register_resume(exe_path)
        reboot_gate_step(provider)

    return [
        Step("preflight", lambda: preflight_step(provider)),
        Step("remediate", lambda: remediate_step(provider)),
        Step("reboot_gate", gate),
        Step("fetch_image", fetch_image),
        Step("create_vm", lambda: None if provider.exists() else provider.create()),
        Step("bootstrap", lambda: _bootstrap(provider)),
        Step("verify", lambda: verify_step(provider, template_dir, domain)),
    ]


def _bootstrap(provider) -> None:
    from .bootstrap import bootstrap
    bootstrap(provider)
