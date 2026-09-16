"""Each recipe's compose skeleton is what a coding agent copies for a new project;
a skeleton that compose itself rejects, or that breaks the Omelet contract, turns
the first plan step of every project built from it into a failure."""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RECIPES = ROOT / "engine" / "skills" / "omelet-stack" / "references"

_COMPOSE_BLOCK = re.compile(r"## docker-compose\.yml\n```yaml\n(.*?)```", re.S)


def _skeletons() -> dict[str, dict]:
    found = {}
    for recipe in RECIPES.glob("*.md"):
        m = _COMPOSE_BLOCK.search(recipe.read_text())
        if m:
            found[recipe.name] = yaml.safe_load(m.group(1))
    assert len(found) >= 8, f"scanned {RECIPES}, parsed {sorted(found)}"
    return found


def test_no_recipe_publishes_host_ports():
    for name, compose in _skeletons().items():
        for service, spec in compose["services"].items():
            assert "ports" not in spec, f"{name}: {service} publishes ports; Omelet routes by name"


def test_every_named_volume_a_service_mounts_is_declared():
    # `docker compose up` refuses a named volume with no top-level declaration;
    # the WordPress recipe shipped without one once.
    for name, compose in _skeletons().items():
        declared = set(compose.get("volumes") or {})
        for service, spec in compose["services"].items():
            for mount in spec.get("volumes", []):
                source = mount.split(":", 1)[0]
                if source.startswith((".", "/", "$")):
                    continue
                assert source in declared, f"{name}: {service} mounts undeclared volume {source!r}"


def test_dev_servers_listen_on_all_interfaces():
    # A server bound to 127.0.0.1 answers only inside its container and the
    # project's URL never loads; the recipes exist to make that mistake impossible.
    for name, compose in _skeletons().items():
        for service, spec in compose["services"].items():
            command = spec.get("command", "")
            if isinstance(command, list):
                command = " ".join(command)
            if "127.0.0.1" in command or "localhost" in command:
                raise AssertionError(f"{name}: {service} binds loopback: {command}")
