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
