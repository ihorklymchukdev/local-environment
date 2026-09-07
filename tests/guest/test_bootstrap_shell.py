import shutil
import subprocess
from pathlib import Path

BOOTSTRAP = Path("omelet/guest/bootstrap.sh")


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
        (Path("omelet/templates/nginx-hello/docker-compose.yml")).read_text())
    for name, svc in compose["services"].items():
        assert not svc.get("ports"), f"{name} publishes a host port"


def test_bootstrap_pins_a_traefik_that_docker_still_talks_to():
    # Traefik <= 3.5 asks the daemon for Docker API 1.24. docker-ce 29 raised
    # MinAPIVersion to 1.40 and rejects it, so the docker provider loads no
    # containers at all and every request answers 404 — with the routing layer
    # looking healthy. 3.6 is the first release that negotiates.
    import re
    match = re.search(r"traefik:v(\d+)\.(\d+)", BOOTSTRAP.read_text())
    assert match, "bootstrap.sh must pin an explicit traefik version"
    assert (int(match[1]), int(match[2])) >= (3, 6), \
        f"traefik:v{match[1]}.{match[2]} requests Docker API 1.24, which docker-ce 29 refuses"
