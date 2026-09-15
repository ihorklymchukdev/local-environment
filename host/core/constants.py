"""Host-side constants.

Deliberately separate from `agent/core/constants.py`: nothing under `host/` may
import `agent/`. Names appearing in both modules are held equal by
`tests/test_constants_agree.py` -- that test, not a shared import, is what stops
the two copies drifting.

Guest paths are derived from GUEST_ROOT rather than spelled out, and the engine
shell tests compare install.sh's literals against these names, so the host and
the engine cannot end up pointing at different files.
"""

GUEST_ROOT = "/opt/omelet"
GUEST_PROJECTS = f"{GUEST_ROOT}/projects"
AGENT_PORT = 39099
# Forwarded by the providers, not used to build URLs on the host: the agent's
# payloads carry every URL the CLI prints.
EDGE_PORT = 39080
# The host only needs the domain to hand the installer's smoke test a value;
# every project URL it prints comes from the agent's own payload.
DEFAULT_DOMAIN = "127-0-0-1.sslip.io"
VERIFY_PROJECT_ID = "omelet-selftest"
# The agent decides what a project must contain; the host only needs the name to
# refuse an empty folder before uploading it. Declared on both sides so the
# constants test fails if the agent ever accepts a second spelling.
COMPOSE_FILE = "docker-compose.yml"

# The host knows only where the engine's entrypoint lives and which file says
# it finished; what gets installed, and which version, is decided in the VM.
ENGINE_URL = ("https://raw.githubusercontent.com/ihorklymchukdev/"
              "local-environment/main/engine/get.sh")
ENGINE_MARKER = f"{GUEST_ROOT}/engine.version"

# Generated in the guest by the engine installer, never pushed from the host. The host
# reads it fresh per client via provider.exec(root=True) rather than caching a
# copy -- see host/client.py.
GUEST_TOKEN = f"{GUEST_ROOT}/agent.token"

# The agent API numbers this host can drive. An engine release that keeps the
# routes compatible keeps the number, so it never needs a host release.
SUPPORTED_API = frozenset({1})
