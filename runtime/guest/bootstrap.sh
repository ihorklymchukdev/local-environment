#!/usr/bin/env bash
set -euo pipefail

MARKER=/opt/runtime/.bootstrapped
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

# 4. project root
mkdir -p /opt/runtime/projects

# 5. traefik as a container, single entrypoint on :39080
# v3.6 or newer is required: earlier releases ask the daemon for Docker API
# 1.24, which docker-ce 29 refuses, leaving the docker provider empty and
# every route answering 404.
mkdir -p /opt/runtime/traefik
cp "$(dirname "$0")/traefik.yml" /opt/runtime/traefik/traefik.yml 2>/dev/null || true
/usr/bin/docker rm -f traefik >/dev/null 2>&1 || true
/usr/bin/docker run -d --name traefik --restart=always --network edge \
  -p 39080:39080 \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  -v /opt/runtime/traefik/traefik.yml:/etc/traefik/traefik.yml:ro \
  traefik:v3.7

# 6. marker
echo "$WANT_VERSION" > /opt/runtime/.bootstrapped
echo "bootstrap complete at version $WANT_VERSION"
