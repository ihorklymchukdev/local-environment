"""The host carries nothing that runs inside the VM: a guest script or skill
under host/ would need a desktop release to change."""
from pathlib import Path

PROVISION = Path(__file__).resolve().parents[2] / "host" / "provision"
# The installer's smoke-test project is the host's own check, sent over HTTP.
HOST_OWNED = PROVISION / "nginx-hello"
GUEST_SHAPED = {".sh", ".py", ".md", ".yml", ".yaml", ".json"}


def test_host_provision_holds_only_the_smoke_test_project():
    assert (HOST_OWNED / "docker-compose.yml").is_file(), f"scanned the wrong tree: {PROVISION}"
    strays = sorted(p.relative_to(PROVISION).as_posix()
                    for p in PROVISION.rglob("*")
                    if p.is_file() and p.suffix in GUEST_SHAPED
                    and HOST_OWNED not in p.parents)
    assert not strays, f"guest assets under host/provision belong in engine/: {strays}"
