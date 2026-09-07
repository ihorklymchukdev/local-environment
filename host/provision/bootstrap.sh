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

# 5. traefik + the agent, as one compose stack.
# Always pull: this is how an agent update reaches an already-provisioned VM,
# so both the first install and every update need the network.
test -f /opt/omelet/stack.yml || { echo 'stack.yml was never pushed to the VM' >&2; exit 1; }
if ! /usr/bin/docker compose -f /opt/omelet/stack.yml pull; then
  echo "could not pull the Omelet images: the registry was unreachable." >&2
  echo "Check the network connection or proxy and run setup again." >&2
  exit 1
fi
/usr/bin/docker compose -f /opt/omelet/stack.yml up -d

# 6. marker, last: a failure above must leave no marker behind.
echo "$WANT_VERSION" > /opt/omelet/.bootstrapped
echo "bootstrap complete at version $WANT_VERSION"
