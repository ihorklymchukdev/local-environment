# Lima / macOS verification — BLOCKED, not run

**Status: not verified.** Phase 2 Task 5 requires a real Apple Silicon machine and
none was available. No part of `host/providers/lima.py` or `host/providers/omelet.yaml`
has ever been executed. **The UNVERIFIED banners in both files stay until this page
records an actual run.**

Nothing below is a result. It is the run that has to happen.

## What Phase 2 changed on the Lima side, unverified

- `forward()` no longer raises for distinct ports. It asks the ssh control master
  Lima already maintains for one more tunnel:
  `ssh -F ~/.lima/<name>/ssh.config -O forward -L <host>:127.0.0.1:<guest> lima-<name>`,
  cancelling first so a repeat is idempotent. Argv is unit-tested; **that the
  control socket exists, is named `ssh.config`, and accepts `-O forward` is an
  assumption about Lima's on-disk layout that only a real run can confirm.**
- `create/start/stop/destroy` now raise on a non-zero `limactl` exit instead of
  dropping the result. Before this they reported success for a VM that never
  booted — the same bug the WSL2 provider was fixed for once already.
- `omelet.yaml` still declares only the two fixed ports. Runtime forwards are made
  over ssh and never edit this file, so no VM restart is involved.

## Known limitation to settle during that run

`LimaProvider.forwards()` returns an empty list unconditionally, so `omelet port list`
reports "No port forwards." on macOS even while tunnels are open. ssh offers no way to
enumerate the forwards a control master holds, and the WSL2 side gets its list from
netsh's registry table, which has no Lima equivalent. Decide during the real run whether
that is acceptable or whether Lima needs its own record of what it opened.

## The run this page is waiting for

1. `omelet doctor` on a clean macOS 13+ machine. Paste the output verbatim.
2. Full install. **Record elapsed wall-clock time** — the blueprint treats 15+
   minutes as an existential product risk, so the number matters more than the pass.
3. The five acceptance compose files in `tests/fixtures/compose/`. Record how many
   came up untouched; that count, not the install, is the stack-agnosticism metric.
4. An image with no arm64 build. Confirm the user sees an explanation, not a raw
   `exec format error`. This is the same class of failure that will recur on cloud
   deploy, so how it reads here is worth more than whether it happens.
5. A distinct-port forward end to end: a database in the VM reached from a host
   tool on a different host port, then released.

Remove the banners only for what the run actually covered, and say plainly what it
did not.
