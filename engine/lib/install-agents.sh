#!/usr/bin/env bash
# Writes Omelet's Codex instructions block and the ~/projects link into one
# home directory. Skills are installed separately, with npx.
# Run by install.sh as root, once per home:
#   install-agents.sh <engine-dir> <home> <owner uid:gid>
set -euo pipefail

SRC=$1
HOME_DIR=$2
OWNER=$3
BEGIN='<!-- omelet:begin -->'
END='<!-- omelet:end -->'
TARGET=/opt/omelet/projects

# Codex has no system-wide AGENTS.md, and the user may keep their own text in
# this one: only the block between the markers is ours to replace.
mkdir -p "$HOME_DIR/.codex"
AGENTS_MD="$HOME_DIR/.codex/AGENTS.md"
touch "$AGENTS_MD"
sed -i "\|^$BEGIN\$|,\|^$END\$|d" "$AGENTS_MD"
if [[ -s "$AGENTS_MD" && -n "$(tail -c1 "$AGENTS_MD")" ]]; then
  echo >> "$AGENTS_MD"
fi
{ echo "$BEGIN"; cat "$SRC/instructions/omelet.md"; echo "$END"; } >> "$AGENTS_MD"

if [[ ! -e "$HOME_DIR/projects" && ! -L "$HOME_DIR/projects" ]]; then
  ln -s "$TARGET" "$HOME_DIR/projects"
elif [[ -L "$HOME_DIR/projects" && "$(readlink "$HOME_DIR/projects")" == "$TARGET" ]]; then
  :
elif [[ -e "$HOME_DIR/projects" || -L "$HOME_DIR/projects" ]]; then
  echo "left $HOME_DIR/projects alone: it already exists and is not Omelet's link"
fi

chown "$OWNER" "$AGENTS_MD" "$HOME_DIR/.codex"
if [[ -L "$HOME_DIR/projects" && "$(readlink "$HOME_DIR/projects")" == "$TARGET" ]]; then
  chown -h "$OWNER" "$HOME_DIR/projects"
fi
