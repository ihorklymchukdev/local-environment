"""Host-side constants.

Deliberately separate from `agent/core/constants.py`: nothing under `host/` may
import `agent/`. Names appearing in both modules are held equal by
`tests/test_constants_agree.py` -- that test, not a shared import, is what stops
the two copies drifting.

Guest paths are derived from GUEST_ROOT rather than spelled out, and the shell
tests compare bootstrap.sh's literals against these names, so the host and the
script cannot end up pointing at different files.
"""

GUEST_ROOT = "/opt/omelet"
GUEST_PROJECTS = f"{GUEST_ROOT}/projects"
AGENT_PORT = 39099
# The host only needs the domain to hand the installer's smoke test a value;
# every project URL it prints comes from the agent's own payload.
DEFAULT_DOMAIN = "127-0-0-1.sslip.io"
VERIFY_PROJECT_ID = "omelet-selftest"

# Bootstrap is purely host-side provisioning; the agent never reads any of these.
# Bump the version whenever host/provision/bootstrap.sh changes, or every
# existing VM silently skips the new provisioning.
BOOTSTRAP_VERSION = 5
BOOTSTRAP_MARKER = f"{GUEST_ROOT}/.bootstrapped"

# Where the pushed copy of agent/deploy/stack.yml lands, and the file compose
# reads its interpolation values from -- compose looks for `.env` beside the
# compose file, which is why both live directly under GUEST_ROOT.
GUEST_STACK = f"{GUEST_ROOT}/stack.yml"
GUEST_ENV = f"{GUEST_ROOT}/.env"

# Generated in the guest by bootstrap.sh, never pushed from the host. The host
# reads it fresh per client via provider.exec(root=True) rather than caching a
# copy -- see host/client.py.
GUEST_TOKEN = f"{GUEST_ROOT}/agent.token"

# Must match stack.yml's OMELET_AGENT_IMAGE default; a test holds the two equal.
AGENT_IMAGE = "ghcr.io/ihorklymchukdev/omelet-agent:0.1.0"
