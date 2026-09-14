"""The host and the agent each own a constants module (Task 9 forbids `host/`
importing `agent/`), so a handful of names are declared twice. Nothing stops the
two copies drifting except this test: a guest path or port that disagrees across
the seam produces a VM the host cannot talk to, with no error naming the cause.
"""
from agent.core import constants as agent_constants
from host.core import constants as host_constants


def _public(module) -> dict:
    return {name: value for name, value in vars(module).items()
            if name.isupper()}


def test_names_declared_in_both_constants_modules_hold_the_same_value():
    agent = _public(agent_constants)
    host = _public(host_constants)
    shared = sorted(set(agent) & set(host))
    assert shared, "the two modules share no names -- this test is no longer guarding anything"
    diverged = {name: (host[name], agent[name])
                for name in shared if host[name] != agent[name]}
    assert not diverged, f"host/agent constants diverged (host, agent): {diverged}"


def test_the_engine_entrypoint_constants_live_only_on_the_host():
    # The agent has no use for either, and must not become a second source of
    # truth for where the engine comes from.
    for name in ("ENGINE_URL", "ENGINE_MARKER"):
        assert not hasattr(agent_constants, name), f"{name} must not live in agent/core/constants.py"
        assert hasattr(host_constants, name), f"{name} must live in host/core/constants.py"


def test_the_readiness_window_is_the_same_on_both_sides_of_the_seam():
    # Declared twice for the same reason as the constants above: the agent may
    # not import from host/. Both wait out the same behaviour -- Traefik
    # publishing a router a beat after the container starts -- so an agent with
    # the shorter window would diagnose a fault the host's own check waits out.
    from agent.core.health import READY_TIMEOUT as agent_timeout
    from host.core.install import READY_TIMEOUT as host_timeout

    assert host_timeout == agent_timeout


def test_the_stack_deploys_the_image_version_the_agent_reports():
    # Three files name this version and are bumped together on an engine
    # release: the stack's image tag (what the VM pulls), the Dockerfile's
    # AGENT_VERSION (GET /version's answer) and the package __version__.
    import re
    from pathlib import Path

    from agent import __version__ as package_version

    root = Path(__file__).resolve().parent.parent
    stack = re.search(r"\$\{OMELET_AGENT_IMAGE:-[^}]+:([^}:]+)\}",
                      (root / "host" / "provision" / "stack.yml").read_text())
    dockerfile = re.search(r"^ARG AGENT_VERSION=(\S+)",
                           (root / "agent" / "Dockerfile").read_text(), re.M)
    assert stack, "stack.yml must default OMELET_AGENT_IMAGE with a tag"
    assert dockerfile, "the Dockerfile must default AGENT_VERSION"
    assert stack[1] == dockerfile[1] == package_version


def test_the_host_speaks_the_api_the_agent_serves():
    assert agent_constants.API_VERSION in host_constants.SUPPORTED_API


def test_the_guest_cli_holds_the_same_values_as_the_host_and_the_agent():
    # The guest CLI is copied into the VM on its own and can import neither
    # side, so its copies of the shared names are held equal here.
    from tests.guest.loader import load

    guest = _public(load())
    for side, other in (("agent", _public(agent_constants)),
                        ("host", _public(host_constants))):
        shared = sorted(set(guest) & set(other))
        assert shared, f"the guest CLI shares no names with the {side}"
        diverged = {name: (guest[name], other[name])
                    for name in shared if guest[name] != other[name]}
        assert not diverged, f"guest/{side} constants diverged: {diverged}"
