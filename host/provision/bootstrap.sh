#!/usr/bin/env bash
# One-time OS-level provisioning only. Everything above the OS -- Traefik, the
# agent, their versions -- lives in stack.yml and is updated by re-running this.
set -euo pipefail

MARKER=/opt/omelet/.bootstrapped
WANT_VERSION="${1:-1}"

if [[ -f "$MARKER" ]] && [[ "$(cat "$MARKER")" == "$WANT_VERSION" ]]; then
  echo "already bootstrapped at version $WANT_VERSION"
  exit 0
fi

export DEBIAN_FRONTEND=noninteractive

# 1. docker-ce from the official repo.
# Guard on the package, not on `command -v docker`: Docker Desktop's WSL
# integration puts its own docker CLI on PATH, which made this skip the install
# and then fail at `systemctl enable` with no docker.service.
if ! dpkg -s docker-ce >/dev/null 2>&1; then
  apt-get update
  apt-get install -y ca-certificates curl
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi

# Absolute path throughout: if Docker Desktop's CLI is on PATH it would
# talk to Desktop's engine instead of this VM's dockerd.
test -x /usr/bin/docker || { echo 'docker-ce did not install /usr/bin/docker' >&2; exit 1; }

# 2. enable docker (systemd must be on — set via wsl.conf during create())
systemctl enable --now docker

# 3. edge network (idempotent)
/usr/bin/docker network inspect edge >/dev/null 2>&1 || /usr/bin/docker network create edge

# 4. project root, group-writable before anything starts.
# The agent container runs as a non-root user, and its only shared credential
# with this VM is the docker group it joins via stack.yml's group_add -- so the
# group, not an image-specific uid the host would have to keep in sync, is what
# /opt/omelet opens up to. Anything in the docker group is already root-
# equivalent here, so this grants no access it did not have. setgid makes the
# project directories the agent creates later inherit the group; without it the
# agent cannot even open /opt/omelet/state.db and restart:always loops it.
mkdir -p /opt/omelet/projects
chgrp -R docker /opt/omelet
chmod -R g+rwX /opt/omelet
find /opt/omelet -type d -exec chmod g+s {} +

# 5. this VM's real docker GID, for stack.yml's group_add.
# The chgrp above used whatever GID this VM's docker group has, while the agent
# image bakes in 999 -- where those differ the agent can write neither
# /opt/omelet nor the socket. Compose reads .env from the directory holding the
# compose file, so writing it here is all the wiring needed.
if ! DOCKER_GID="$(getent group docker | cut -d: -f3)" || [[ -z "$DOCKER_GID" ]]; then
  echo 'no docker group in this VM after installing docker-ce' >&2
  exit 1
fi
printf 'OMELET_DOCKER_GID=%s\n' "$DOCKER_GID" > /opt/omelet/.env

# 6. the shared secret between the host and the agent.
# Only if absent: bootstrap re-runs are normal, and regenerating it every
# time would invalidate a token the host is already holding. Must land
# before the agent starts, and after the chmod sweep above or its mode gets
# widened along with everything else.
# The pipeline reads exactly 32 bytes from /dev/urandom before anything
# downstream sees them: bounding an infinite `tr < /dev/urandom` with a
# later `head -c` instead kills tr with SIGPIPE the moment head stops
# reading, and set -o pipefail then fails the whole script over a byte count
# that was never wrong.
if [[ ! -s /opt/omelet/agent.token ]]; then
  # `install` sets the mode on creation, before any content lands in the
  # file -- a plain `>` redirect creates it under root's umask (644) first
  # and only narrows it on the next line, leaving it briefly world-readable.
  install -m 640 /dev/null /opt/omelet/agent.token
  head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n' > /opt/omelet/agent.token
fi
# Root-owned but group-readable: the agent's own uid is non-root, and docker
# group membership is already root-equivalent here (it owns the socket), so
# it is the group a credential the agent itself must read has to grant.
# Reasserted every run, not just on first creation, so a pre-existing file
# from before this ever ran still ends up correct.
chgrp docker /opt/omelet/agent.token
chmod 640 /opt/omelet/agent.token

# 7. traefik + the agent, as one compose stack.
# Always pull: this is how an agent update reaches an already-provisioned VM,
# so both the first install and every update need the network.
test -f /opt/omelet/stack.yml || { echo 'stack.yml was never pushed to the VM' >&2; exit 1; }
if ! /usr/bin/docker compose -f /opt/omelet/stack.yml pull; then
  echo "could not pull the Omelet images: the registry was unreachable." >&2
  echo "Check the network connection or proxy and run setup again." >&2
  exit 1
fi
/usr/bin/docker compose -f /opt/omelet/stack.yml up -d

# 8. coding agents: the in-VM `omelet` command, and what each agent reads.
if ! dpkg -s git >/dev/null 2>&1; then
  apt-get update
  apt-get install -y git
fi
command -v python3 >/dev/null || { echo 'python3 is missing; the omelet command needs it' >&2; exit 1; }
install -m 755 /opt/omelet/bin/omelet /usr/local/bin/omelet

# System-wide where the agent has such a place, so which user runs the
# session does not matter.
install -d /etc/claude-code /etc/codex/skills
install -m 644 /opt/omelet/agents/omelet.md /etc/claude-code/CLAUDE.md
rm -rf /etc/codex/skills/omelet-setup
cp -r /opt/omelet/agents/skills/omelet-setup /etc/codex/skills/

# Per home where it is not: root (WSL sessions), every login account (Lima's
# user) and /etc/skel for accounts made later. The docker group is the only
# way a non-root user can read the agent token.
bash /opt/omelet/bin/install-agents.sh /opt/omelet/agents /root 0:0
bash /opt/omelet/bin/install-agents.sh /opt/omelet/agents /etc/skel 0:0
while IFS=: read -r name uid gid home; do
  usermod -aG docker "$name"
  bash /opt/omelet/bin/install-agents.sh /opt/omelet/agents "$home" "$uid:$gid"
done < <(getent passwd | bash /opt/omelet/bin/login-users.sh /etc/shells)

# 9. marker, last: a failure above must leave no marker behind.
echo "$WANT_VERSION" > /opt/omelet/.bootstrapped
echo "bootstrap complete at version $WANT_VERSION"
