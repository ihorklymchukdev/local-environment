#!/usr/bin/env bash
set -euo pipefail

MARKER=/opt/runtime/.bootstrapped
WANT_VERSION="${1:-1}"

if [[ -f "$MARKER" ]] && [[ "$(cat "$MARKER")" == "$WANT_VERSION" ]]; then
  echo "already bootstrapped at version $WANT_VERSION"
  exit 0
fi

export DEBIAN_FRONTEND=noninteractive

# 1. docker-ce from the official repo
if ! command -v docker >/dev/null 2>&1; then
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

# 2. enable docker (systemd must be on — set via wsl.conf during create())
systemctl enable --now docker

# 3. edge network (idempotent)
docker network inspect edge >/dev/null 2>&1 || docker network create edge

# 4. project root
mkdir -p /opt/runtime/projects

# 5. traefik as a container, single entrypoint on :39080
mkdir -p /opt/runtime/traefik
cp "$(dirname "$0")/traefik.yml" /opt/runtime/traefik/traefik.yml 2>/dev/null || true
docker rm -f traefik >/dev/null 2>&1 || true
docker run -d --name traefik --restart=always --network edge \
  -p 39080:39080 \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  -v /opt/runtime/traefik/traefik.yml:/etc/traefik/traefik.yml:ro \
  traefik:v3.1

# 6. marker
echo "$WANT_VERSION" > /opt/runtime/.bootstrapped
echo "bootstrap complete at version $WANT_VERSION"
