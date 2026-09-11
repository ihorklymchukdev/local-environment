"""What the Windows one-dir build is allowed to contain.

The agent ships as a Docker image the VM pulls; it is never frozen into the
host binary. Nothing enforced that except the import-boundary test, which says
nothing about `datas` -- and `datas` is how two host-side compose files came to
sit under `agent/` and get bundled from there.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "packaging" / "windows" / "omelet.spec"


def _datas() -> list[tuple[str, str]]:
    body = re.search(r"datas=\[(.*?)\]", SPEC.read_text(), re.S)
    assert body, f"no datas list in {SPEC}"
    quoted = re.findall(r'"([^"]+)"', body[1])
    assert len(quoted) % 2 == 0, f"datas entries are not (source, dest) pairs: {quoted}"
    return list(zip(quoted[::2], quoted[1::2]))


def test_the_frozen_binary_bundles_nothing_from_the_agent():
    entries = _datas()
    assert entries, "the spec bundles no assets at all -- this test guards nothing"
    offenders = [src for src, dest in entries
                 if "agent/" in src or dest.startswith("agent")]
    assert not offenders, (
        f"the frozen host binary bundles agent files: {offenders}. The agent is "
        "pulled as an image; anything the host must push into a VM that has no "
        "agent yet belongs under host/provision/.")


def test_every_bundled_source_exists_and_lands_where_its_reader_looks():
    # A `datas` dest that disagrees with the module resolving it produces a
    # binary that passes `omelet version` and fails minutes into a real setup.
    from host.core.bootstrap import guest_assets
    from host.core.install import VERIFY_TEMPLATE

    entries = _datas()
    for source, _dest in entries:
        assert (SPEC.parent / source).resolve().is_file(), f"{source} does not exist"

    dests = {dest for _src, dest in entries}
    expected = {local.parent.relative_to(ROOT).as_posix()
                for local, _remote in guest_assets()}
    expected.add(VERIFY_TEMPLATE.relative_to(ROOT).as_posix())
    missing = expected - dests
    assert not missing, f"assets the host reads at runtime are not bundled: {missing}"


def test_the_build_stays_one_dir():
    # One-file unpacks to a temp directory on every launch, which is both slower
    # and the shape antivirus heuristics dislike most. The Inno installer is
    # already the single artifact users download.
    text = SPEC.read_text()
    assert "COLLECT(" in text, "one-dir builds go through COLLECT"
    assert "exclude_binaries=True" in text
