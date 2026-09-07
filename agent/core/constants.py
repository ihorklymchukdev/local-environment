EDGE_PORT = 39080
BOOTSTRAP_VERSION = 3
GUEST_ROOT = "/opt/omelet"
GUEST_PROJECTS = "/opt/omelet/projects"
BOOTSTRAP_MARKER = "/opt/omelet/.bootstrapped"
EDGE_NETWORK = "edge"
DEFAULT_DOMAIN = "127-0-0-1.sslip.io"
# Reserved for the setup smoke test. Deriving it from the template directory
# name would let `verify` compose-down a user project that happened to share it.
VERIFY_PROJECT_ID = "omelet-selftest"
