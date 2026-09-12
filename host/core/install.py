from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# Resolved from this module rather than from cli.py: cli.py is the frozen
# entry script, whose __file__ points at the bundle root instead of at
# host/, so an entry-script lookup misses the bundled template.
VERIFY_TEMPLATE = (Path(__file__).resolve().parent.parent
                    / "provision" / "nginx-hello")


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
    run: Callable[[], str | None]
    # Run on every invocation, never recorded as done. Two kinds of step need
    # this: the ones that prove or report the outcome, and the ones whose
    # product lives in the VM -- which can be destroyed without setup ever
    # hearing about it, leaving the state file claiming a distro that is gone.
    always_run: bool = False
    # Plain-language next move for the user when this step fails.
    action: str = ""


# Shown when RunOnce relaunches setup at logon: a window that opens by itself
# after a restart has to say why it is there.
RESUME_NOTICE = "Continuing setup after the restart — you don't need to do anything."


class RebootRequired(Exception):
    """The machine must restart before the remaining steps can run."""


class InstallError(RuntimeError):
    def __init__(self, step: str, message: str, action: str = ""):
        super().__init__(f"{step}: {message}")
        self.step = step
        self.message = message
        self.action = action


def run_install(steps: list[Step], state: InstallState,
                report: Callable[[Progress], None]) -> None:
    done = state.completed()
    for step in steps:
        if step.name in done and not step.always_run:
            report(Progress(step.name, "skipped"))
            continue
        report(Progress(step.name, "running"))
        try:
            message = step.run()
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
            raise InstallError(step.name, str(e), step.action) from e
        # An always-run step is never persisted: recording it would claim a
        # proof that is only valid for the run that produced it.
        if not step.always_run:
            state.mark(step.name)
        report(Progress(step.name, "done", message or ""))


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


class AgentTooOld(RuntimeError):
    """The VM runs an older agent than this host was built against."""


class AgentNotAccepted(RuntimeError):
    """The agent is serving, but refuses every authenticated call and a
    re-provision did not change that."""


# The agent answers one of these when it has no usable token of its own, or
# when the one this host is holding is not the one it started with. Neither
# clears with time: the token is read once, at container startup.
_TOKEN_CODES = frozenset({"agent_unconfigured", "unauthorized"})


def _version_tuple(version: str) -> tuple[int, ...] | None:
    """The leading dotted integers, or None for anything that cannot be
    ordered -- a locally built image tagged `dev`, a git sha."""
    parts = []
    for chunk in version.strip().split("."):
        digits = re.match(r"\d+", chunk)
        if digits is None:
            break
        parts.append(int(digits.group()))
    return tuple(parts) or None


# `docker compose up -d` returns before the new agent container is serving, so
# the first version read after an update legitimately answers "connection
# refused".
AGENT_RESTART_TIMEOUT = 30.0


def _is_current(found: str, want: tuple[int, ...] | None) -> bool:
    """A newer agent is deliberately not an error: routes are added rather
    than removed, so an agent ahead of the host still answers everything it
    asks for, and refusing one would break a host downgrade or a pre-release
    image for no gain. A version that cannot be ordered is not an error either
    -- refusing to set up over a string we cannot read is worse than
    continuing."""
    have = _version_tuple(found)
    return want is None or have is None or have >= want


def _version_once_serving(client, sleep, timeout: float) -> str:
    from host.client import AgentUnavailableError
    deadline = time.monotonic() + timeout
    while True:
        try:
            return client.version()
        except AgentUnavailableError:
            if time.monotonic() >= deadline:
                raise
        sleep(1.0)


def agent_version_step(provider, *, client=None, expected: str | None = None,
                       repair=None, reconnect=None, sleep=time.sleep):
    """Bring the VM's agent up to the version this host expects, or say why not.

    `repair` re-provisions the guest stack (`compose pull && up -d`) and is
    tried once: without it the only exit from an older agent is destroying the
    VM, which discards every project in it.

    `reconnect` is the same idea for an agent that is serving but refuses every
    authenticated call. It re-provisions *and* recreates the agent container --
    the token is read once at startup, so re-provisioning alone leaves the
    running container refusing exactly the same calls -- then returns a client
    holding the token the VM has now. Returning None keeps the current client.
    """
    from host.client import AgentClient, AgentError
    from host.core import constants

    expected = expected or constants.EXPECTED_AGENT_VERSION
    client = client or AgentClient.for_provider(provider)
    want = _version_tuple(expected)
    reconnected = False
    try:
        found = client.version()
    except AgentError as e:
        if e.code not in _TOKEN_CODES or reconnect is None:
            raise
        client = reconnect() or client
        try:
            found = _version_once_serving(client, sleep, AGENT_RESTART_TIMEOUT)
        except AgentError as again:
            if again.code not in _TOKEN_CODES:
                raise
            raise AgentNotAccepted(
                "The Omelet service inside the virtual machine did not accept "
                "this computer, and setting the virtual machine up again did "
                f"not change that.\n{again.message}") from again
        reconnected = True
    if _is_current(found, want):
        if reconnected:
            return ("The Omelet service in the virtual machine was not "
                    "accepting this computer, and has been reconnected.")
        return None
    # Not after a reconnect: that already re-provisioned the guest stack, and
    # repeating it is minutes of pulling that cannot change the answer.
    if repair is not None and not reconnected:
        repair()
        found = _version_once_serving(client, sleep, AGENT_RESTART_TIMEOUT)
        if _is_current(found, want):
            return ("The Omelet service in the virtual machine was out of "
                    f"date and has been updated to {found}.")
    raise AgentTooOld(
        f"The virtual machine is running an older version of the Omelet "
        f"service ({found}) than this app expects ({expected}).")


class VerificationFailed(RuntimeError):
    """The smoke-test project did not serve a successful response."""


def _default_http_get(url: str) -> int:
    from urllib.request import urlopen
    with urlopen(url, timeout=30) as response:
        return response.status


# Traefik publishes a router a beat after the container starts, so the first
# request after `compose up` answers 404 on a stack that is perfectly healthy.
READY_TIMEOUT = 30.0


def _await_http_ok(url: str, http_get, timeout: float, sleep) -> None:
    deadline = time.monotonic() + timeout
    while True:
        error = None
        code = None
        try:
            code = http_get(url)
        except Exception as e:
            error = e
        if code == 200:
            return
        if time.monotonic() >= deadline:
            # First line for the user, second for whoever they send it to.
            if error is not None:
                raise VerificationFailed(
                    f"The test project did not answer at {url}.\n"
                    f"{type(error).__name__}: {error}") from error
            raise VerificationFailed(
                f"The test project answered with an error at {url}.\n"
                f"The address returned HTTP {code} instead of 200.")
        sleep(0.5)


def verify_step(provider, template_dir: Path, domain: str, *, client=None,
                http_get=_default_http_get, ready_timeout: float = READY_TIMEOUT,
                sleep=time.sleep) -> None:
    """Run the bundled template through the agent and require HTTP 200.

    The gate is the response the user's browser would get, not the job's own
    verdict: a container can run happily while its URL answers a proxy error.
    """
    from host.client import AgentClient, JobFailedError
    from host.core.constants import VERIFY_PROJECT_ID

    client = client or AgentClient.for_provider(provider)
    try:
        client.ensure_project(VERIFY_PROJECT_ID, domain=domain)
        client.upload_directory(VERIFY_PROJECT_ID, template_dir)
        try:
            result = client.wait_for_job(
                client.project_up(VERIFY_PROJECT_ID)).get("result") or {}
        except JobFailedError as e:
            status = e.result.get("status", "failed")
            raise VerificationFailed(
                "The test project's containers did not stay running.\n"
                f"status: {status}" + (f"\n{e}" if str(e) else "")) from e
        problem = result.get("problem")
        if problem:
            # The containers started, but the agent already probed the URL
            # through Traefik and knows why it will not answer. Waiting out
            # the readiness window to report "did not respond" would replace
            # that explanation with a symptom.
            raise VerificationFailed(problem["message"])
        urls = result.get("urls") or []
        if not urls:
            raise VerificationFailed(
                "the smoke-test project exposed no HTTP address")
        _await_http_ok(urls[0], http_get, ready_timeout, sleep)
    finally:
        _teardown(client)


def _teardown(client) -> None:
    """Remove the smoke-test project, containers and state row alike, so a
    failed verify leaves nothing running and `omelet status` stays clean."""
    import sys

    from host.core.constants import VERIFY_PROJECT_ID
    # Read before the call: inside the `except` below, the exception being
    # handled is this one, not the one that is propagating.
    already_failing = sys.exc_info()[0] is not None
    try:
        client.delete_project(VERIFY_PROJECT_ID)
    except Exception as e:
        # Swallowed only while a failure is already on its way out -- masking
        # the reason verification failed is worse than a leaked container. On
        # the success path the leak is the only thing left to report.
        if not already_failing:
            raise VerificationFailed(
                "The test project worked, but it could not be removed from "
                "the virtual machine afterwards. Its containers may still be "
                f"running.\n{e}") from e


def finish_step(install_dir) -> str:
    """The only step whose product is words. Every run must reach it."""
    return (
        "Setup finished successfully.\n"
        f"The virtual machine and its files are in: {install_dir}\n\n"
        "To start a project, open PowerShell and run:\n\n"
        "    omelet up <folder>\n\n"
        "where <folder> is the folder that holds your docker-compose.yml.")


_ACTIONS = {
    "preflight": "This computer could not be checked. Restart it and run setup again.",
    "remediate": "Windows features could not be turned on. Run setup again and "
                 "choose Yes when Windows asks for permission.",
    "reboot_gate": "Restart the computer and run setup again.",
    "fetch_image": "The Linux image could not be downloaded — the internet "
                   "connection was unavailable. Run setup again and the download "
                   "continues from where it stopped.",
    "create_vm": "The virtual machine could not be created. Restart the computer, "
                 "make sure there is at least 10 GB free, and run setup again.",
    "bootstrap": "Docker could not be installed inside the virtual machine. The "
                 "detail above comes from inside the VM. Run setup again; if it "
                 "fails the same way twice, send us that text.",
    "agent": "The Omelet service inside the virtual machine could not be "
             "brought up to date, or would not accept this computer — the "
             "message above says which. Run setup again; if it fails the same "
             "way twice, use Copy diagnostics and send us the text.",
    "verify": "The test project did not answer. Run setup again; if it fails a "
              "second time, use Copy diagnostics and send us the text.",
}


def default_steps(provider, *, cache_dir, template_dir: Path, domain,
                  exe_path: str, install_dir) -> list[Step]:
    from .download import fetch

    image = provider.image()
    # Assigned here rather than inside fetch_image: that step is skipped on a
    # resume or a re-run, and create_vm needs the path in every process.
    rootfs = Path(cache_dir) / image.url.rsplit("/", 1)[-1]
    provider.rootfs = rootfs

    def fetch_image():
        fetch(image, rootfs)

    def gate():
        if provider.reboot_required():
            provider.register_resume(exe_path)
        reboot_gate_step(provider)

    def step(name: str, run, *, always_run: bool = False) -> Step:
        return Step(name, run, always_run=always_run, action=_ACTIONS.get(name, ""))

    return [
        step("preflight", lambda: preflight_step(provider)),
        step("remediate", lambda: remediate_step(provider)),
        step("reboot_gate", gate),
        # Only the three steps above may be remembered across runs: they are
        # facts about this computer. Everything below is a fact about the VM,
        # and each re-derives it cheaply -- fetch() returns on a matching
        # digest, create() on an existing distro, bootstrap() on a matching
        # guest marker -- so re-running them costs seconds and skipping them
        # costs a WSL_E_DISTRO_NOT_FOUND minutes later.
        step("fetch_image", fetch_image, always_run=True),
        step("create_vm", lambda: None if provider.exists() else provider.create(),
             always_run=True),
        step("bootstrap", lambda: _bootstrap(provider), always_run=True),
        # Before verify, not after: a host talking to an agent that predates
        # the routes it uses should say so in one sentence, not fail several
        # minutes into a compose run with a 404 on a route name.
        step("agent", lambda: agent_version_step(
            provider, repair=lambda: _bootstrap(provider, force=True),
            reconnect=lambda: _reconnect(provider)),
            always_run=True),
        step("verify", lambda: verify_step(provider, template_dir, domain),
             always_run=True),
        step("finish", lambda: finish_step(install_dir), always_run=True),
    ]


def _bootstrap(provider, *, force: bool = False) -> None:
    from .bootstrap import bootstrap
    bootstrap(provider, force=force)


def _reconnect(provider):
    """Re-provision the guest, recreate the agent container so it re-reads the
    token bootstrap.sh just repaired, and dial it with the token the VM holds
    now (the client caches the one it was built with)."""
    from host.client import AgentClient

    from .bootstrap import restart_agent
    _bootstrap(provider, force=True)
    restart_agent(provider)
    return AgentClient.for_provider(provider)
