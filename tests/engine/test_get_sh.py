"""get.sh's choice of which engine to install, and that it actually runs when
fetched the ways it is fetched. The download and apt steps need a network and
are covered by the live-VM acceptance run."""
import os
import subprocess
import tarfile
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


def test_a_pre_release_tag_never_outranks_a_plain_release(tmp_path):
    result = _resolve(tmp_path, tags=["engine-v1.0.0-rc1", "engine-v1.0.0", "engine-v0.9.0"])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "engine-v1.0.0"


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


def _archive_with_install_sh(tmp_path: Path, ref: str, body: str) -> Path:
    tar_path = tmp_path / "archive.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        data = body.encode()
        info = tarfile.TarInfo(name=f"local-environment-{ref}/engine/install.sh")
        info.size = len(data)
        tar.addfile(tarinfo=info, fileobj=__import__("io").BytesIO(data))
    return tar_path


@pytest.mark.parametrize("repair", [False, True])
def test_a_successful_install_exits_zero_and_hands_install_sh_the_ref(tmp_path, repair):
    # A regression test for a trap that referenced an out-of-scope local
    # variable: under set -u it turned every successful install into exit 1.
    root = tmp_path / "opt-omelet"
    root.mkdir()
    script = GET.read_text().replace("/opt/omelet", str(root))

    ref = "engine-v0.1.0"
    tar_path = _archive_with_install_sh(
        tmp_path, ref, '#!/usr/bin/env bash\necho "install.sh args: $*"\n')

    def make_curl(archive_path):
        # curl -fsSL <url> -o <dest>: $1=-fsSL $2=url $3=-o $4=dest
        return f"cp '{archive_path}' \"$4\"\n"

    environ = _bin(tmp_path, dpkg="exit 0\n", curl=make_curl(tar_path),
                   git=_git_listing(tmp_path, [ref]))
    for name in ("OMELET_ENGINE_REF", "OMELET_ENGINE_REPAIR"):
        environ.pop(name, None)
    expected_args = ref
    if repair:
        environ["OMELET_ENGINE_REPAIR"] = "1"
        (root / "engine.version").write_text(ref + "\n")
        expected_args += " --repair"

    result = subprocess.run(["bash", "-c", script], env=environ,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert f"install.sh args: {expected_args}" in result.stdout
    assert (root / "engine" / "install.sh").exists()


def test_an_archive_without_the_engine_is_a_plain_failure(tmp_path):
    # Archive with GitHub shape (top-level directory) but no engine/ inside.
    tar_path = tmp_path / "archive.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        info = tarfile.TarInfo(name="local-environment-engine-v0.1.0/host/readme.txt")
        info.size = 5
        tar.addfile(tarinfo=info, fileobj=__import__("io").BytesIO(b"hello"))

    def make_curl(archive_path):
        # curl -fsSL <url> -o <dest>: $1=-fsSL $2=url $3=-o $4=dest
        return f"cp '{archive_path}' \"$4\"\n"

    environ = _bin(tmp_path, dpkg="exit 0\n", curl=make_curl(tar_path),
                   git=_git_listing(tmp_path, ["engine-v0.1.0"]))
    for name in ("OMELET_ENGINE_REF", "OMELET_ENGINE_REPAIR"):
        environ.pop(name, None)

    script = GET.read_text()
    result = subprocess.run(["bash", "-c", script], env=environ,
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert "engine-v0.1.0" in result.stderr
    assert "no engine/" in result.stderr
