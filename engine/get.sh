#!/usr/bin/env bash
# The engine's entrypoint: choose an engine ref, unpack that ref's engine/ into
# /opt/omelet/engine and run its install.sh. Fetched on its own (the host's
# bootstrap, or `curl -fsSL <url> | sudo bash` on a cloud VM), so it can rely
# on nothing beside it. Run as root.
set -euo pipefail

REPO="${OMELET_ENGINE_REPO:-https://github.com/ihorklymchukdev/local-environment}"
MARKER=/opt/omelet/engine.version
ENGINE_DIR=/opt/omelet/engine

# resolve_ref <repo> <marker>: an explicit ref wins, a repair keeps what is
# installed, anything else takes the highest engine-v* tag.
resolve_ref() {
  local repo=$1 marker=$2 tags latest
  if [[ -n "${OMELET_ENGINE_REF:-}" ]]; then
    echo "$OMELET_ENGINE_REF"
    return
  fi
  if [[ "${OMELET_ENGINE_REPAIR:-}" == 1 && -s "$marker" ]]; then
    cat "$marker"
    return
  fi
  if ! tags="$(git ls-remote --tags --refs "$repo" 'engine-v*')"; then
    echo "could not reach $repo to find the latest Omelet engine" >&2
    return 1
  fi
  latest="$(sed -n 's#.*refs/tags/##p' <<<"$tags" | sort -V | tail -n 1)"
  if [[ -z "$latest" ]]; then
    echo "$repo has no engine-v* release to install" >&2
    return 1
  fi
  echo "$latest"
}

main() {
  export DEBIAN_FRONTEND=noninteractive
  local missing=() pkg
  for pkg in ca-certificates curl git; do
    dpkg -s "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
  done
  if (( ${#missing[@]} )); then
    if ! apt-get update || ! apt-get install -y "${missing[@]}"; then
      echo "could not install ${missing[@]}: the Ubuntu package mirrors may be unreachable" >&2
      exit 1
    fi
  fi

  local ref tmp
  ref="$(resolve_ref "$REPO" "$MARKER")"
  echo "installing Omelet engine $ref"

  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  if ! curl -fsSL "$REPO/archive/$ref.tar.gz" -o "$tmp/engine.tar.gz"; then
    echo "could not download Omelet engine $ref from $REPO" >&2
    exit 1
  fi
  if ! tar -xzf "$tmp/engine.tar.gz" -C "$tmp" --strip-components=1 --wildcards '*/engine/' 2>/dev/null; then
    echo "$ref of $REPO has no engine/ directory" >&2
    exit 1
  fi
  if [[ ! -f "$tmp/engine/install.sh" ]]; then
    echo "$ref of $REPO has no engine/install.sh" >&2
    exit 1
  fi
  # Replaced, not merged: a file dropped from the engine must not linger.
  mkdir -p /opt/omelet
  rm -rf "$ENGINE_DIR"
  mv "$tmp/engine" "$ENGINE_DIR"
  chmod 755 "$ENGINE_DIR"

  local args=("$ref")
  if [[ "${OMELET_ENGINE_REPAIR:-}" == 1 ]]; then
    args+=(--repair)
  fi
  bash "$ENGINE_DIR/install.sh" "${args[@]}"
}

# `return` only succeeds when sourced (the tests); under `bash -c` or a pipe it
# fails and the install runs.
(return 0 2>/dev/null) || main "$@"
