"""get.sh's choice of which engine to install, and that it actually runs when
fetched the ways it is fetched. The download and apt steps need a network and
are covered by the live-VM acceptance run."""
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GET = ROOT / "engine" / "get.sh"
REPO = "https://example.invalid/omelet"


def _bin(tmp_path: Path, **scripts: str) -> dict:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in scripts.items():
        path = bin_dir / name
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)
    return {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}


def _git_listing(tmp_path: Path, tags, code: int = 0) -> str:
    listing = tmp_path / "tags.txt"
    listing.write_text("".join(f"{'0' * 40}\trefs/tags/{t}\n" for t in tags))
    return f"cat '{listing}'\nexit {code}\n"


def _resolve(tmp_path, *, tags=(), git_code=0, installed="", **env):
    marker = tmp_path / "engine.version"
    if installed:
        marker.write_text(installed + "\n")
    environ = _bin(tmp_path, git=_git_listing(tmp_path, tags, git_code))
    for name in ("OMELET_ENGINE_REF", "OMELET_ENGINE_REPAIR"):
        environ.pop(name, None)
    environ.update(env)
    return subprocess.run(
        ["bash", "-c", f'source "{GET}" && resolve_ref "{REPO}" "{marker}"'],
        env=environ, capture_output=True, text=True)


def test_get_sh_is_valid_bash():
    result = subprocess.run(["bash", "-n", str(GET)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_the_highest_engine_tag_wins_by_version_not_by_text(tmp_path):
    result = _resolve(tmp_path, tags=["engine-v0.9.0", "engine-v0.10.0", "engine-v0.2.1"])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "engine-v0.10.0"


def test_an_explicit_ref_wins_over_every_tag(tmp_path):
    result = _resolve(tmp_path, tags=["engine-v0.3.0"], OMELET_ENGINE_REF="feature/x")
    assert result.stdout.strip() == "feature/x"


def test_a_repair_keeps_the_installed_ref_instead_of_upgrading(tmp_path):
    result = _resolve(tmp_path, tags=["engine-v0.3.0"], installed="engine-v0.2.0",
                      OMELET_ENGINE_REPAIR="1")
    assert result.stdout.strip() == "engine-v0.2.0"


def test_a_repair_with_nothing_installed_installs_the_latest(tmp_path):
    result = _resolve(tmp_path, tags=["engine-v0.3.0"], OMELET_ENGINE_REPAIR="1")
    assert result.stdout.strip() == "engine-v0.3.0"


def test_a_repository_without_engine_tags_is_a_plain_failure(tmp_path):
    result = _resolve(tmp_path, tags=[])
    assert result.returncode != 0
    assert "no engine-v" in result.stderr


def test_an_unreachable_repository_is_a_plain_failure(tmp_path):
    result = _resolve(tmp_path, tags=[], git_code=128)
    assert result.returncode != 0
    assert "could not reach" in result.stderr


@pytest.mark.parametrize("how", ["bash -c", "stdin"])
def test_fetching_the_script_runs_the_install_not_just_its_functions(tmp_path, how):
    # The host runs it with `bash -c "$script"`, a cloud VM with `curl | bash`;
    # a sourcing guard that misfires there would define functions and exit 0.
    environ = _bin(tmp_path, dpkg="exit 0\n", curl="exit 22\n",
                   git=_git_listing(tmp_path, ["engine-v0.1.0"]))
    for name in ("OMELET_ENGINE_REF", "OMELET_ENGINE_REPAIR"):
        environ.pop(name, None)
    script = GET.read_text()
    if how == "bash -c":
        result = subprocess.run(["bash", "-c", script], env=environ,
                                capture_output=True, text=True)
    else:
        result = subprocess.run(["bash"], input=script, env=environ,
                                capture_output=True, text=True)
    assert result.returncode != 0
    assert "could not download Omelet engine engine-v0.1.0" in result.stderr
