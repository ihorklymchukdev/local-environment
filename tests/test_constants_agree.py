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


def test_bootstrap_constants_live_only_on_the_host():
    # Bootstrap is host-side provisioning; the agent has no use for either and
    # must not become a second source of truth for the version marker.
    for name in ("BOOTSTRAP_VERSION", "BOOTSTRAP_MARKER"):
        assert not hasattr(agent_constants, name), f"{name} must not live in agent/core/constants.py"
        assert hasattr(host_constants, name), f"{name} must live in host/core/constants.py"


def test_agent_image_matches_the_stack_files_default():
    # Two places name the image: constants.AGENT_IMAGE (what the host expects to
    # be talking to) and stack.yml's OMELET_AGENT_IMAGE default (what the guest
    # actually pulls). Bumping one alone deploys an image the host never checks.
    import re
    from pathlib import Path

    stack = Path(__file__).resolve().parent.parent / "agent" / "deploy" / "stack.yml"
    match = re.search(r"\$\{OMELET_AGENT_IMAGE:-([^}]+)\}", stack.read_text())
    assert match, "stack.yml must default OMELET_AGENT_IMAGE"
    assert match[1] == host_constants.AGENT_IMAGE


def test_the_readiness_window_is_the_same_on_both_sides_of_the_seam():
    # Declared twice for the same reason as the constants above: the agent may
    # not import from host/. Both wait out the same behaviour -- Traefik
    # publishing a router a beat after the container starts -- so an agent with
    # the shorter window would diagnose a fault the host's own check waits out.
    from agent.core.health import READY_TIMEOUT as agent_timeout
    from host.core.install import READY_TIMEOUT as host_timeout

    assert host_timeout == agent_timeout


def test_the_agent_version_the_host_expects_is_the_one_the_image_reports():
    # Three files name this version: the tag in constants.AGENT_IMAGE, the
    # Dockerfile's AGENT_VERSION (which becomes GET /version's answer), and the
    # agent package's own __version__. A bump that misses one makes the host's
    # compatibility check report every VM as out of date.
    import re
    from pathlib import Path

    from agent import __version__ as package_version

    dockerfile = Path(__file__).resolve().parent.parent / "agent" / "Dockerfile"
    match = re.search(r"^ARG AGENT_VERSION=(\S+)", dockerfile.read_text(), re.M)
    assert match, "the Dockerfile must default AGENT_VERSION"
    assert match[1] == host_constants.EXPECTED_AGENT_VERSION == package_version
