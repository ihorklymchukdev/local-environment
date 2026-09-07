"""Host-side constants.

Deliberately separate from `agent/core/constants.py`: nothing under `host/` may
import `agent/`. Names appearing in both modules are held equal by
`tests/test_constants_agree.py` -- that test, not a shared import, is what stops
the two copies drifting.
"""

GUEST_ROOT = "/opt/omelet"
AGENT_PORT = 39099
VERIFY_PROJECT_ID = "omelet-selftest"

# Bootstrap is purely host-side provisioning; the agent never reads either.
# Bump the version whenever host/provision/bootstrap.sh changes, or every
# existing VM silently skips the new provisioning.
BOOTSTRAP_VERSION = 4
BOOTSTRAP_MARKER = "/opt/omelet/.bootstrapped"

# Where the pushed copy of agent/deploy/stack.yml lands in the guest.
GUEST_STACK = "/opt/omelet/stack.yml"

# Must match stack.yml's OMELET_AGENT_IMAGE default; a test holds the two equal.
AGENT_IMAGE = "ghcr.io/ihorklymchukdev/omelet-agent:0.1.0"
