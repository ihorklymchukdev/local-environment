import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "engine" / "lib" / "install-agents.sh"
SOURCE = ROOT / "engine"


def _install(home: Path, source: Path = SOURCE) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["bash", str(SCRIPT), str(source), str(home), f"{os.getuid()}:{os.getgid()}"],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result


def test_skills_are_left_to_npx(tmp_path):
    _install(tmp_path)
    assert not (tmp_path / ".claude" / "skills").exists()
    assert not (tmp_path / ".agents" / "skills").exists()


def test_the_codex_block_is_replaced_and_the_users_own_text_kept(tmp_path):
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    agents_md = home / ".codex" / "AGENTS.md"
    agents_md.write_text("# my notes\nkeep me")  # no trailing newline on purpose
    source = tmp_path / "src"
    shutil.copytree(SOURCE, source)

    _install(home, source)
    (source / "instructions" / "omelet.md").write_text("new instructions\n")
    _install(home, source)

    text = agents_md.read_text()
    assert text.startswith("# my notes\nkeep me\n")
    assert text.count("<!-- omelet:begin -->") == 1
    assert "new instructions" in text
    assert "You are working inside an Omelet VM" not in text


def test_the_projects_link_is_made_once_and_a_real_folder_is_left_alone(tmp_path):
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    _install(fresh)
    _install(fresh)
    assert os.readlink(fresh / "projects") == "/opt/omelet/projects"

    taken = tmp_path / "taken"
    (taken / "projects").mkdir(parents=True)
    result = _install(taken)
    assert (taken / "projects").is_dir() and not (taken / "projects").is_symlink()
    assert "left" in result.stdout


def test_a_projects_link_pointing_elsewhere_is_left_alone_and_reported(tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    (home / "projects").symlink_to(elsewhere)
    result = _install(home)
    assert os.readlink(home / "projects") == str(elsewhere)
    assert "left" in result.stdout
