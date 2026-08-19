import shutil
import subprocess
from pathlib import Path

BOOTSTRAP = Path("runtime/guest/bootstrap.sh")


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
    assert "/opt/runtime/.bootstrapped" in text


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
