"""Why a started project still does not answer.

`classify()` only asks whether the containers stayed up. An app that listens on
127.0.0.1 inside its own container passes that check and is then unreachable
from anywhere else, so the URL answers a proxy error with nothing naming the
cause. This module is the only place in the system that can see both sides.
"""
from __future__ import annotations

import ipaddress
import time
from dataclasses import dataclass

from . import constants
from .detect import WebSpec
from .lifecycle import DOCKER, container_id
from .overlay import host_for
from .project import Project

# Traefik publishes a router a beat after the container starts, so the first
# requests answer 404 on a stack that is perfectly healthy. Same window the
# host's own post-install check waits.
READY_TIMEOUT = 30.0
POLL_INTERVAL = 0.5

BOUND_TO_LOOPBACK = "bound_to_loopback"
SERVICE_UNREACHABLE = "service_unreachable"

_BAD_GATEWAY = 502
# 404 is a router that does not exist yet, 502 a container Traefik cannot dial.
# Both are ordinary a second after `up`; every other status is an answer.
_RETRYABLE = {404, _BAD_GATEWAY}
_LISTEN = "0A"


@dataclass(frozen=True)
class Diagnosis:
    code: str
    message: str

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True)
class Listener:
    address: ipaddress.IPv4Address | ipaddress.IPv6Address
    port: int

    @property
    def is_loopback(self) -> bool:
        mapped = getattr(self.address, "ipv4_mapped", None)
        return (mapped or self.address).is_loopback


def default_probe(url: str, host: str) -> int:
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen

    try:
        with urlopen(Request(url, headers={"Host": host}), timeout=10) as response:
            return response.status
    except HTTPError as e:
        # Traefik's own 404 or 502 is the answer this probe came for, not an
        # error; urllib just happens to raise it.
        return e.code


def _settle(url: str, host: str, *, http_probe, timeout: float, sleep, clock):
    """Polls until something conclusive comes back or the window closes.
    Returns the last status seen, or None if nothing ever answered."""
    deadline = clock() + timeout
    while True:
        try:
            status = http_probe(url, host)
        except Exception:
            # Nothing answered at all: Traefik itself may still be starting.
            status = None
        if status is not None and status not in _RETRYABLE:
            return status
        if clock() >= deadline:
            return status
        sleep(POLL_INTERVAL)


def _decode_address(field: str):
    """`0100007F:0050` -> (127.0.0.1, 80). /proc/net/tcp prints each 32-bit
    word in host byte order, so every word has to be reversed."""
    hex_address, _, hex_port = field.partition(":")
    try:
        raw = bytes.fromhex(hex_address)
        port = int(hex_port, 16)
    except ValueError:
        return None
    if len(raw) not in (4, 16):
        return None
    packed = b"".join(raw[i:i + 4][::-1] for i in range(0, len(raw), 4))
    return ipaddress.ip_address(packed), port


def parse_listeners(proc_net: str) -> list[Listener]:
    listeners = []
    for line in proc_net.splitlines():
        fields = line.split()
        # The header line's `st` column reads "st", so it drops out here too.
        if len(fields) < 4 or fields[3] != _LISTEN:
            continue
        decoded = _decode_address(fields[1])
        if decoded is not None:
            listeners.append(Listener(*decoded))
    return listeners


def _listeners(runner, project_id: str, service: str) -> list[Listener] | None:
    """None means the check itself could not run — a slim image with no `cat`,
    or a container that is already gone. Callers must hedge, never claim."""
    cid = container_id(runner, project_id, service)
    if not cid:
        return None
    # /proc/net/tcp, not `ss`: a slim image has neither ss nor netstat, but
    # procfs is always mounted.
    result = runner.exec([DOCKER, "exec", cid, "cat",
                          "/proc/net/tcp", "/proc/net/tcp6"], root=True)
    if not result.ok and not result.stdout.strip():
        return None
    return parse_listeners(result.stdout)


def _loopback_message(web: WebSpec) -> str:
    return (f"The '{web.service}' service is listening on 127.0.0.1 inside its "
            f"container, so nothing outside that container can reach it. "
            f"Change it to listen on 0.0.0.0 (all addresses) on port "
            f"{web.port}, then start the project again.")


def _unreachable_message(web: WebSpec) -> str:
    return (f"Nothing answered on port {web.port} of the '{web.service}' "
            f"service, so the address returns a proxy error. The usual cause "
            f"is a service listening on 127.0.0.1 instead of 0.0.0.0 inside "
            f"its container; `omelet logs` shows what it printed.")


def _explain(runner, project_id: str, web: WebSpec) -> Diagnosis:
    listeners = _listeners(runner, project_id, web.service)
    if listeners is None:
        return Diagnosis(SERVICE_UNREACHABLE, _unreachable_message(web))
    on_port = [listener for listener in listeners if listener.port == web.port]
    # Only when the routed port itself is loopback-only: a container that also
    # listens on 0.0.0.0 somewhere is failing for some other reason.
    if on_port and all(listener.is_loopback for listener in on_port):
        return Diagnosis(BOUND_TO_LOOPBACK, _loopback_message(web))
    return Diagnosis(SERVICE_UNREACHABLE, _unreachable_message(web))


def diagnose(runner, project: Project, domain: str, *,
             edge_port: int = constants.EDGE_PORT,
             traefik_host: str = "traefik",
             http_probe=default_probe,
             timeout: float = READY_TIMEOUT,
             sleep=time.sleep, clock=time.monotonic) -> Diagnosis | None:
    """None when the project answers, or when nothing was proven. Never raises:
    a crashed diagnosis would turn a working `up` into a failed request."""
    if not project.webs:
        return None
    web = project.webs[0]
    # By container name with an explicit Host header: the public hostname
    # resolves to 127.0.0.1, which inside the agent container is the agent.
    status = _settle(f"http://{traefik_host}:{edge_port}/",
                     host_for(project.id, web, domain),
                     http_probe=http_probe, timeout=timeout,
                     sleep=sleep, clock=clock)
    if status != _BAD_GATEWAY:
        return None
    return _explain(runner, project.id, web)
