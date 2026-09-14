#!/usr/bin/env bash
# Installs the engine into this VM. Run as root by get.sh from the unpacked
# engine directory; re-running it is safe.
set -euo pipefail

ENGINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

REF="${1:?usage: install.sh <engine ref> [--repair]}"
REPAIR=0
if [[ "${2:-}" == --repair ]]; then
  REPAIR=1
fi
SKILLS_CLI=skills@1.5.26
# skills@1.5.26 declares node >=22.20.0; Ubuntu 24.04's own nodejs is 18.
NODE_MIN=22.20.0
TOKEN_CREATED=0

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
  TOKEN_CREATED=1
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
install -m 644 "$ENGINE_DIR/stack.yml" /opt/omelet/stack.yml
if ! /usr/bin/docker compose -f /opt/omelet/stack.yml pull; then
  echo "could not pull the Omelet images: the registry was unreachable." >&2
  echo "Check the network connection or proxy and run setup again." >&2
  exit 1
fi
/usr/bin/docker compose -f /opt/omelet/stack.yml up -d
# The agent reads its token once, at startup, and `up -d` leaves an unchanged
# container running.
if (( TOKEN_CREATED || REPAIR )); then
  /usr/bin/docker compose -f /opt/omelet/stack.yml up -d --force-recreate agent
fi

# 8. git for `omelet clone`, Node for `npx skills`.
if ! dpkg -s git >/dev/null 2>&1; then
  apt-get update
  apt-get install -y git
fi
node_ok() {
  command -v node >/dev/null 2>&1 || return 1
  local have
  have="$(node -p 'process.versions.node')" || return 1
  [[ "$(printf '%s\n' "$NODE_MIN" "$have" | sort -V | head -n 1)" == "$NODE_MIN" ]]
}
if ! node_ok; then
  if ! command -v gpg >/dev/null 2>&1; then
    if ! { apt-get update && apt-get install -y gnupg; }; then
      echo "could not install gnupg: the Ubuntu package mirrors may be unreachable" >&2
      exit 1
    fi
  fi
  install -m 0755 -d /etc/apt/keyrings
  if ! curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
      | gpg --dearmor --yes -o /etc/apt/keyrings/nodesource.gpg; then
    echo "could not reach NodeSource to install Node.js 22" >&2
    exit 1
  fi
  echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" \
    > /etc/apt/sources.list.d/nodesource.list
  if ! { apt-get update && apt-get install -y nodejs; }; then
    echo "could not reach NodeSource to install Node.js 22" >&2
    exit 1
  fi
  node_ok || { echo "Node.js $NODE_MIN or newer did not install" >&2; exit 1; }
fi

# 9. the in-VM omelet command and the instructions every session loads.
install -m 755 "$ENGINE_DIR/cli/omelet.py" /usr/local/bin/omelet
install -d /etc/claude-code
install -m 644 "$ENGINE_DIR/instructions/omelet.md" /etc/claude-code/CLAUDE.md

# 10. copies earlier provisioning made, which npx now owns or nothing reads.
rm -rf /etc/codex/skills/omelet-setup /opt/omelet/bin /opt/omelet/agents \
  /opt/omelet/.bootstrapped \
  /etc/skel/.claude/skills/omelet-setup /etc/skel/.agents/skills/omelet-setup

# 11. per account: docker group, Codex block, ~/projects, skills.
accounts() {
  echo "root:0:0:/root"
  getent passwd | bash "$ENGINE_DIR/lib/login-users.sh" /etc/shells
}
while IFS=: read -r name uid gid home; do
  if [[ "$name" != root ]]; then
    usermod -aG docker "$name"
  fi
  bash "$ENGINE_DIR/lib/install-agents.sh" "$ENGINE_DIR" "$home" "$uid:$gid"
  # npx symlinks ~/.claude/skills/<name>; a real directory left there by the
  # old copy-based install would block it.
  for old in "$home/.claude/skills/omelet-setup" "$home/.agents/skills/omelet-setup"; do
    if [[ -d "$old" && ! -L "$old" ]]; then
      rm -rf "$old"
    fi
  done
  # stdin is the account list this loop is reading.
  if ! runuser -u "$name" -- env HOME="$home" DISABLE_TELEMETRY=1 npx -y "$SKILLS_CLI" add "$ENGINE_DIR/skills" -s '*' -g -a claude-code codex -y </dev/null; then
    echo "could not install Omelet's skills for $name: the npm registry may be unreachable" >&2
    exit 1
  fi
done < <(accounts)

# 12. marker, last: a failure above must leave no marker behind.
echo "$REF" > /opt/omelet/engine.version
echo "Omelet engine $REF installed"
