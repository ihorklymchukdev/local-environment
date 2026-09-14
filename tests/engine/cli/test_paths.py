import os
import stat

import pytest

from tests.engine.cli.loader import load

cli = load()


@pytest.fixture
def root(tmp_path):
    projects = tmp_path / "opt" / "projects"
    projects.mkdir(parents=True)
    return projects


def test_a_folder_and_its_subfolders_belong_to_the_project(root):
    (root / "blog" / "src" / "pages").mkdir(parents=True)
    expected = (root / "blog").resolve()
    assert cli.project_of(root / "blog", root) == expected
    assert cli.project_of(root / "blog" / "src" / "pages", root) == expected


def test_the_home_symlink_reaches_the_same_project(root, tmp_path):
    (root / "blog").mkdir()
    link = tmp_path / "home" / "projects"
    link.parent.mkdir()
    link.symlink_to(root)
    assert cli.project_of(link / "blog", root) == (root / "blog").resolve()


def test_the_projects_root_itself_and_folders_outside_it_are_no_project(root, tmp_path):
    (tmp_path / "elsewhere").mkdir()
    assert cli.project_of(root, root) is None
    assert cli.project_of(tmp_path / "elsewhere", root) is None


def test_a_folder_whose_name_is_not_an_id_must_be_renamed_first(root):
    folder = root / "My Blog"
    folder.mkdir()
    with pytest.raises(cli.OmeletError, match="'my-blog'"):
        cli.require_id(folder)


def test_a_folder_name_with_nothing_usable_is_refused(root):
    folder = root / "???"
    folder.mkdir()
    with pytest.raises(cli.OmeletError, match="cannot be a project name"):
        cli.require_id(folder)


def test_the_agent_can_write_its_overlay_after_a_root_session_made_the_files(root):
    project = root / "blog"
    omelet_dir = project / ".omelet"
    omelet_dir.mkdir(parents=True)
    omelet_dir.chmod(0o755)
    overlay = omelet_dir / "overlay.yml"
    overlay.write_text("old")
    overlay.chmod(0o644)
    source = project / "app.py"
    source.write_text("")
    source.chmod(0o644)

    cli.prepare_overlay_dir(project, os.getgid())

    assert stat.S_IMODE(omelet_dir.stat().st_mode) == 0o2775
    assert stat.S_IMODE(overlay.stat().st_mode) == 0o664
    assert stat.S_IMODE(source.stat().st_mode) == 0o644


def test_a_missing_omelet_folder_is_created_writable(root):
    project = root / "blog"
    project.mkdir()
    cli.prepare_overlay_dir(project, os.getgid())
    assert stat.S_IMODE((project / ".omelet").stat().st_mode) == 0o2775


def test_a_symlinked_omelet_dir_is_refused(root, tmp_path):
    project = root / "blog"
    project.mkdir(parents=True)
    target = tmp_path / "elsewhere"
    target.mkdir()
    target.chmod(0o700)
    (project / ".omelet").symlink_to(target)

    with pytest.raises(cli.OmeletError, match="symbolic link"):
        cli.prepare_overlay_dir(project, os.getgid())

    assert stat.S_IMODE(target.stat().st_mode) == 0o700


def test_a_symlinked_overlay_file_is_refused(root, tmp_path):
    project = root / "blog"
    omelet_dir = project / ".omelet"
    omelet_dir.mkdir(parents=True)
    omelet_dir.chmod(0o755)
    target = tmp_path / "secret.yml"
    target.write_text("secret")
    target.chmod(0o600)
    (omelet_dir / "overlay.yml").symlink_to(target)

    with pytest.raises(cli.OmeletError, match="symbolic link"):
        cli.prepare_overlay_dir(project, os.getgid())

    assert stat.S_IMODE(target.stat().st_mode) == 0o600
