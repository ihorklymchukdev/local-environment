from __future__ import annotations

import tarfile
from pathlib import Path, PurePosixPath

# No size cap here on an uploaded archive or a single file: removing the old
# ~24 KB command-line ceiling is this module's entire purpose. A cap belongs
# with the auth work, not here.


class PathTraversalError(Exception):
    """An archive entry, or a requested file path, resolves outside the
    project directory."""


class BadArchiveError(Exception):
    """The body handed to `POST /files` is not a readable tar.gz."""


def extract_archive(archive_path: Path, dest_dir: Path) -> None:
    """Unpack `archive_path` into `dest_dir`, merging with what is already
    there. Files the archive contains are overwritten; everything else in
    `dest_dir` - a database's bind-mounted data directory, say - is left
    untouched. Never `rmtree` dest_dir first; deletion only ever happens
    through the explicit DELETE route.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(archive_path, mode="r:gz") as tar:
            # tarfile's "data" filter is permissive with an absolute member
            # name: it strips the leading "/" and keeps the now-relative
            # entry, rather than refusing it. That is safe (the write still
            # lands inside dest_dir) but not what this API promises its
            # caller, so absolute names are rejected outright, before the
            # filter gets a chance to be lenient about them.
            for member in tar.getmembers():
                if PurePosixPath(member.name).is_absolute():
                    raise PathTraversalError(
                        f"'{member.name}' is an absolute path")
            # The filter handles everything else: `..` escapes, and symlinks
            # or hardlinks whose target resolves outside dest_dir. Hand-rolled
            # checks in this area have a long history of being subtly wrong.
            tar.extractall(dest_dir, filter="data")
    except tarfile.FilterError as e:
        raise PathTraversalError(str(e)) from e
    except (tarfile.TarError, OSError, EOFError) as e:
        raise BadArchiveError(str(e)) from e


def resolve_within(root: Path, rel_path: str) -> Path:
    """Resolve `rel_path` under `root`, refusing anything that would read or
    write outside it. `root / rel_path` alone is not enough: pathlib silently
    discards `root` when `rel_path` is absolute, and `..` components need
    resolving before the containment check means anything.
    """
    if not rel_path or PurePosixPath(rel_path).is_absolute():
        raise PathTraversalError(f"'{rel_path}' is not a relative path")
    root = root.resolve()
    candidate = (root / rel_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise PathTraversalError(f"'{rel_path}' escapes the project directory")
    return candidate


def list_tree(root: Path) -> list[dict]:
    """Relative paths and sizes of every file under `root`. `root` is always
    a project directory built by the caller, so nothing here re-validates it
    the way `resolve_within` validates a request-supplied path."""
    if not root.exists():
        return []
    return [
        {"path": str(path.relative_to(root)), "size": path.stat().st_size}
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]
