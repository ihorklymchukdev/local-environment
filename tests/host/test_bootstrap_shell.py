import shutil
import subprocess
from pathlib import Path

BOOTSTRAP = Path("host/provision/bootstrap.sh")


def test_bootstrap_is_valid_bash():
    # `bash -n` parses without executing; catches syntax errors.
    result = subprocess.run(["bash", "-n", str(BOOTSTRAP)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_bootstrap_pins_docker_official_repo_not_docker_io():
    text = BOOTSTRAP.read_text()
    assert "download.docker.com" in text
    assert "docker.io" not in text


def test_bootstrap_writes_version_marker():
    text = BOOTSTRAP.read_text()
    assert "/opt/omelet/.bootstrapped" in text


def test_bootstrap_guards_on_the_package_not_the_docker_binary():
    # Docker Desktop's WSL integration puts its own docker CLI on PATH. Guarding
    # on `command -v docker` skipped the install and then failed at
    # `systemctl enable` with "Unit file docker.service does not exist".
    code = [l for l in BOOTSTRAP.read_text().splitlines()
            if not l.lstrip().startswith("#")]
    assert any("dpkg -s docker-ce" in l for l in code)
    assert not any("command -v docker" in l for l in code)


def test_bootstrap_invokes_docker_by_absolute_path():
    # A bare `docker` would reach Docker Desktop's CLI when its WSL integration
    # is on, sending this VM's containers to Desktop's engine instead.
    import re
    for line in BOOTSTRAP.read_text().splitlines():
        stripped = line.strip()
        if re.match(r"^(\|\||&&)?\s*docker\s", stripped):
            raise AssertionError(f"bare docker invocation: {stripped}")


def test_smoke_test_template_publishes_no_host_port():
    # The template reaches the browser through Traefik on the edge network, so a
    # published port buys nothing and collides: the first real Windows run died
    # with "failed to bind host port 0.0.0.0:8080/tcp: address already in use".
    import yaml
    compose = yaml.safe_load(
        (Path("agent/templates/nginx-hello/docker-compose.yml")).read_text())
    for name, svc in compose["services"].items():
        assert not svc.get("ports"), f"{name} publishes a host port"


def _commands() -> list[str]:
    """Executable lines only -- a comment mentioning `docker run traefik` must
    not satisfy or trip the assertions below."""
    return [l.strip() for l in BOOTSTRAP.read_text().splitlines()
            if l.strip() and not l.lstrip().startswith("#")]


def _index_of(needle: str) -> int:
    for i, line in enumerate(_commands()):
        if needle in line:
            return i
    raise AssertionError(f"bootstrap.sh has no line containing {needle!r}")


def test_bootstrap_brings_the_stack_up_with_compose_not_an_inline_container():
    # Traefik and the agent are one compose stack now; an inline `docker run`
    # would start a Traefik outside it that compose can never upgrade or stop.
    commands = _commands()
    assert any("compose -f /opt/omelet/stack.yml" in l and " up -d" in l for l in commands)
    assert not any("docker run" in l for l in commands), "the inline traefik container is gone"
    assert not any("docker rm -f traefik" in l for l in commands)
    assert not any("traefik.yml" in l for l in commands)


def test_bootstrap_always_pulls_before_bringing_the_stack_up():
    # Always pulling is the delivery decision: it is how an agent update reaches
    # an already-bootstrapped VM. `up -d` alone would keep running a stale image.
    assert _index_of("compose -f /opt/omelet/stack.yml pull") < _index_of(" up -d")


def test_bootstrap_makes_opt_omelet_writable_before_the_agent_starts():
    # The agent runs as a non-root user whose only shared credential with the VM
    # is the docker group. Root-owned 0755 here means it cannot create
    # /opt/omelet/state.db, and `restart: always` then loops it forever.
    assert _index_of("chgrp") < _index_of(" up -d")
    assert any("docker" in l for l in _commands() if "chgrp" in l), \
        "the group the agent actually belongs to"
    assert any("g+s" in l for l in _commands()), \
        "setgid, or project directories the agent creates lose the group"


def test_bootstrap_writes_the_marker_last():
    # bootstrap.py treats a missing marker as failure, which only works while the
    # marker is the final step: written earlier, a failed pull looks bootstrapped.
    commands = _commands()
    marker = _index_of("> /opt/omelet/.bootstrapped")
    assert marker > _index_of(" up -d")
    assert marker >= len(commands) - 2, "nothing that can fail may run after the marker"
