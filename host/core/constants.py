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

# Bootstrap is purely host-side provisioning; the agent never reads any of these.
# Bump the version whenever host/provision/bootstrap.sh changes, or every
# existing VM silently skips the new provisioning.
BOOTSTRAP_VERSION = 6
BOOTSTRAP_MARKER = f"{GUEST_ROOT}/.bootstrapped"

# Where the pushed copy of host/provision/stack.yml lands. Compose reads its
# interpolation values from a `.env` beside the compose file, which is why
# bootstrap.sh writes one directly under GUEST_ROOT too; no host code opens
# that file, so it has no constant here.
GUEST_STACK = f"{GUEST_ROOT}/stack.yml"

# Generated in the guest by bootstrap.sh, never pushed from the host. The host
# reads it fresh per client via provider.exec(root=True) rather than caching a
# copy -- see host/client.py.
GUEST_TOKEN = f"{GUEST_ROOT}/agent.token"

# Must match stack.yml's OMELET_AGENT_IMAGE default; a test holds the two equal.
AGENT_IMAGE = "ghcr.io/ihorklymchukdev/omelet-agent:0.1.0"
# The agent version this host expects to talk to, derived from the tag it
# deploys rather than written out again: two literals would let a bumped image
# leave the compatibility check comparing against a version nothing runs.
EXPECTED_AGENT_VERSION = AGENT_IMAGE.rsplit(":", 1)[-1]
