# Engine self-update (deferred)

Not implemented. Recorded during the host-shell/engine split design
(`docs/superpowers/specs/2026-09-14-host-shell-engine-split-design.md`) so the shape is not
re-derived later. Revisit once the engine has a remote home (GitHub releases or an own domain).

## Why it will be needed

- The host deliberately does not update the engine: re-running setup on an installed VM does
  nothing. Today the only way to a newer engine is a repair or a fresh VM.
- Accounts created after install get no skills or Codex `AGENTS.md` block until the engine is
  installed again.
- A cloud VM has no host at all, so updating has to be something the guest can do itself.

## Proposed shape

**`omelet self-update [--repair]`** in the guest CLI (`engine/cli/omelet.py`):

- Reads `OMELET_ENGINE_URL` and `OMELET_ENGINE_REPO` from `/opt/omelet/engine.env`, which
  `get.sh` would start writing on every install so the update uses the same source the VM was
  installed from.
- Re-executes itself through `sudo` when not root (WSL sessions are root; Lima's user has
  passwordless sudo), then fetches and runs `get.sh` exactly as the host bootstrap does.
- Plain `self-update` resolves the newest `engine-v*` tag; `--repair` sets
  `OMELET_ENGINE_REPAIR=1`, which keeps the installed ref and recreates the agent container.
- `omelet version` prints the installed engine ref (`/opt/omelet/engine.version`) and the agent's
  own `/version`.

Once it exists, the host's connect-step repair can call `omelet self-update --repair` through
`exec(root=True)` instead of re-running the bootstrap command — same behaviour, one fewer place
that knows the entrypoint URL.

## Automatic updates, later

- A systemd timer calling `omelet self-update` on a schedule is the smallest step, but it replaces
  the agent container mid-session; it should skip while any project job is running (the agent's
  job registry already knows) or only run at boot.
- `npx skills update` is not the update path for Omelet's own skills: they are installed from the
  unpacked engine folder (`Source: local`), so re-running `install.sh` is what refreshes them.
  Third-party skills installed from GitHub URLs could use `npx skills update -g -y` per account.
- An `api` bump in an engine release must not reach a VM whose host does not speak it yet —
  auto-update needs to check the host's supported range, or the release has to keep serving the
  old `api` alongside the new one for a while.
