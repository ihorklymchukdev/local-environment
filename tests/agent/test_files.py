import io
import tarfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.api.app import create_app
from agent.core import files
from agent.core.config import AgentConfig


def _tar_bytes(*, add_default_file=True, entries=None) -> bytes:
    """Build a tar.gz in memory. `entries` is a list of (TarInfo, data|None)
    pairs for tests that need to hand-craft a malicious member; normal
    callers just get a plain `hello.txt`."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        if add_default_file:
            data = b"hello\n"
            info = tarfile.TarInfo("hello.txt")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        for info, data in entries or []:
            tar.addfile(info, io.BytesIO(data) if data is not None else None)
    return buf.getvalue()


def _entry(name, **kw):
    info = tarfile.TarInfo(name)
    for k, v in kw.items():
        setattr(info, k, v)
    return info


# ---------------------------------------------------------------------------
# Core-level: agent.core.files.extract_archive
# ---------------------------------------------------------------------------

def test_relative_traversal_entry_is_rejected(tmp_path):
    archive = tmp_path / "evil.tar.gz"
    archive.write_bytes(_tar_bytes(add_default_file=False, entries=[
        (_entry("../../etc/passwd", size=4), b"pwn\n"),
    ]))
    dest = tmp_path / "project"
    with pytest.raises(files.PathTraversalError):
        files.extract_archive(archive, dest)


def test_absolute_path_entry_is_rejected(tmp_path):
    archive = tmp_path / "evil.tar.gz"
    archive.write_bytes(_tar_bytes(add_default_file=False, entries=[
        (_entry("/etc/passwd", size=4), b"pwn\n"),
    ]))
    dest = tmp_path / "project"
    with pytest.raises(files.PathTraversalError):
        files.extract_archive(archive, dest)


def test_symlink_target_escaping_the_project_is_rejected(tmp_path):
    archive = tmp_path / "evil.tar.gz"
    link = _entry("escape", type=tarfile.SYMTYPE, linkname="../../etc/passwd")
    archive.write_bytes(_tar_bytes(add_default_file=False, entries=[(link, None)]))
    dest = tmp_path / "project"
    with pytest.raises(files.PathTraversalError):
        files.extract_archive(archive, dest)


def test_hardlink_target_escaping_the_project_is_rejected(tmp_path):
    archive = tmp_path / "evil.tar.gz"
    link = _entry("escape", type=tarfile.LNKTYPE, linkname="../../etc/passwd")
    archive.write_bytes(_tar_bytes(add_default_file=False, entries=[(link, None)]))
    dest = tmp_path / "project"
    with pytest.raises(files.PathTraversalError):
        files.extract_archive(archive, dest)


def test_a_body_that_is_not_gzip_is_a_bad_archive(tmp_path):
    archive = tmp_path / "not-a-tar.tar.gz"
    archive.write_bytes(b"this is plainly not a tarball")
    dest = tmp_path / "project"
    with pytest.raises(files.BadArchiveError):
        files.extract_archive(archive, dest)


def test_extraction_merges_and_leaves_untracked_files_alone(tmp_path):
    dest = tmp_path / "project"
    dest.mkdir()
    (dest / "data").mkdir()
    (dest / "data" / "postgres.db").write_text("irreplaceable")
    (dest / "docker-compose.yml").write_text("old")

    archive = tmp_path / "update.tar.gz"
    archive.write_bytes(_tar_bytes(add_default_file=False, entries=[
        (_entry("docker-compose.yml", size=3), b"new"),
    ]))
    files.extract_archive(archive, dest)

    assert (dest / "docker-compose.yml").read_text() == "new"
    assert (dest / "data" / "postgres.db").read_text() == "irreplaceable"


def test_resolve_within_rejects_absolute_and_traversal_paths(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    with pytest.raises(files.PathTraversalError):
        files.resolve_within(root, "/etc/passwd")
    with pytest.raises(files.PathTraversalError):
        files.resolve_within(root, "../../etc/passwd")


def test_resolve_within_allows_a_nested_relative_path(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    resolved = files.resolve_within(root, ".omelet/project.yml")
    assert resolved == (root / ".omelet" / "project.yml").resolve()


# ---------------------------------------------------------------------------
# Route-level
# ---------------------------------------------------------------------------

@pytest.fixture
def env(tmp_path):
    config = AgentConfig(projects_root=tmp_path / "projects",
                         state_db=tmp_path / "state.db")
    app = create_app(config=config)
    with TestClient(app) as client:
        yield client, config


def _create(client, pid="blog"):
    resp = client.post("/projects", json={"id": pid})
    assert resp.status_code == 201, resp.text
    return resp


def test_upload_route_rejects_a_traversal_archive(env):
    client, _config = env
    _create(client)
    archive = _tar_bytes(add_default_file=False, entries=[
        (_entry("../../etc/passwd", size=4), b"pwn\n"),
    ])
    resp = client.post("/projects/blog/files", content=archive,
                       headers={"Content-Type": "application/gzip"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "path_traversal"


def test_upload_route_rejects_a_non_gzip_body(env):
    client, _config = env
    _create(client)
    resp = client.post("/projects/blog/files", content=b"not a tarball",
                       headers={"Content-Type": "application/gzip"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "bad_archive"


def test_upload_to_an_unknown_project_is_project_not_found(env):
    client, _config = env
    resp = client.post("/projects/nope/files", content=_tar_bytes())
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "project_not_found"


def test_upload_merges_and_tree_lists_tracked_and_untracked_files(env):
    client, config = env
    _create(client)

    first = _tar_bytes(add_default_file=False, entries=[
        (_entry("docker-compose.yml", size=8), b"services"),
    ])
    assert client.post("/projects/blog/files", content=first).status_code == 200

    # A file the upload never touches - a bind-mounted data directory, say.
    (config.projects_root / "blog" / "data").mkdir()
    (config.projects_root / "blog" / "data" / "state.db").write_text("keep-me")

    second = _tar_bytes(add_default_file=False, entries=[
        (_entry("docker-compose.yml", size=11), b"new-compose"),
    ])
    assert client.post("/projects/blog/files", content=second).status_code == 200

    tree = {f["path"]: f["size"]
           for f in client.get("/projects/blog/files").json()["files"]}
    assert tree["docker-compose.yml"] == 11
    assert tree["data/state.db"] == len("keep-me")
    assert (config.projects_root / "blog" / "data" / "state.db").read_text() == "keep-me"


def test_put_get_delete_single_file_round_trip(env):
    client, _config = env
    _create(client)

    put = client.put("/projects/blog/files/.omelet/project.yml", content=b"id: blog\n")
    assert put.status_code == 200, put.text

    got = client.get("/projects/blog/files/.omelet/project.yml")
    assert got.status_code == 200
    assert got.content == b"id: blog\n"

    assert client.delete("/projects/blog/files/.omelet/project.yml").status_code == 200
    assert client.get("/projects/blog/files/.omelet/project.yml").status_code == 404


def test_get_missing_file_is_file_not_found(env):
    client, _config = env
    _create(client)
    resp = client.get("/projects/blog/files/nope.txt")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "file_not_found"


def test_get_file_route_rejects_traversal(env):
    client, _config = env
    _create(client)
    # httpx collapses a literal ".." in the URL before it ever leaves the
    # client, so this uses the percent-encoded form to prove the *server*
    # rejects it too, not just well-behaved HTTP clients.
    resp = client.get("/projects/blog/files/%2e%2e/%2e%2e/etc/passwd")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "path_traversal"


def test_a_5mb_archive_round_trips_proving_the_command_line_ceiling_is_gone(env):
    client, _config = env
    _create(client)

    payload = (b"omelet-poc-" * 500_000)  # ~5.5 MB, well past the old ~24 KB cap
    assert len(payload) > 5 * 1024 * 1024
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo("big.bin")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))

    resp = client.post("/projects/blog/files", content=buf.getvalue())
    assert resp.status_code == 200, resp.text

    got = client.get("/projects/blog/files/big.bin")
    assert got.status_code == 200
    assert got.content == payload
