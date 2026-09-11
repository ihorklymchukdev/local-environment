import re

import yaml

from pathlib import Path

STACK = Path(__file__).resolve().parents[2] / "host" / "provision" / "stack.yml"

# Compose interpolation: ${VAR} or ${VAR:-default}. Stripping the whole
# expression, not just the default, is what makes the "no bare literal" test
# below meaningful -- a naive strip that kept the default text would let a
# hardcoded 39080 slip back in disguised as someone's idea of a default.
_INTERPOLATION = re.compile(r"\$\{[^}]*\}")


def _text() -> str:
    return STACK.read_text()


def _without_interpolation() -> str:
    return _INTERPOLATION.sub("", _text())


def test_stack_yml_hardcodes_no_domain_or_port_outside_a_default():
    # This is the one rule that keeps Phase 5 from becoming a rewrite: every
    # environment injects its own domain and ports through OMELET_DOMAIN /
    # OMELET_EDGE_PORT / OMELET_AGENT_PORT, so nothing here may assume the
    # local values.
    stripped = _without_interpolation()
    assert "39080" not in stripped
    assert "39099" not in stripped
    assert "127-0-0-1.sslip.io" not in stripped


def test_the_agent_binds_the_port_it_is_published_on():
    # AgentConfig already reads OMELET_AGENT_PORT; publishing a fixed port
    # while the process binds a configured one forwards the host to nothing.
    agent = yaml.safe_load(_text())["services"]["agent"]
    assert agent["ports"] == ["${OMELET_AGENT_PORT:-39099}:"
                              "${OMELET_AGENT_PORT:-39099}"]
    assert "OMELET_AGENT_PORT=${OMELET_AGENT_PORT:-39099}" in agent["environment"]


def test_stack_yml_parses_and_has_no_version_key():
    doc = yaml.safe_load(_text())
    assert "version" not in doc


def test_stack_yml_both_services_restart_always_on_the_external_edge_network():
    doc = yaml.safe_load(_text())
    for name in ("traefik", "agent"):
        service = doc["services"][name]
        assert service["restart"] == "always"
        assert "edge" in service["networks"]
    assert doc["networks"]["edge"]["external"] is True


def test_stack_yml_mounts_opt_omelet_at_the_identical_path_on_both_sides():
    # The agent parses compose files, but dockerd on the VM resolves the
    # bind-mount paths inside them. A mismatched path here silently mounts
    # every user project's relative volume onto an empty directory.
    volumes = yaml.safe_load(_text())["services"]["agent"]["volumes"]
    assert "/opt/omelet:/opt/omelet" in volumes


def test_stack_yml_pins_exact_image_tags():
    doc = yaml.safe_load(_text())
    assert ":latest" not in doc["services"]["traefik"]["image"]
    assert ":latest" not in _text()


def test_bootstrap_pins_a_traefik_that_docker_still_talks_to():
    # Traefik <= 3.5 asks the daemon for Docker API 1.24. docker-ce 29 raised
    # MinAPIVersion to 1.40 and rejects it, so the docker provider loads no
    # containers at all and every request answers 404 — with the routing layer
    # looking healthy. 3.6 is the first release that negotiates.
    import re
    match = re.search(r"traefik:v(\d+)\.(\d+)", _text())
    assert match, "stack.yml must pin an explicit traefik version"
    assert (int(match[1]), int(match[2])) >= (3, 6), \
        f"traefik:v{match[1]}.{match[2]} requests Docker API 1.24, which docker-ce 29 refuses"
