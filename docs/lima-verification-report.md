# Lima / macOS verification — still BLOCKED on the VM

**Status: the VM has never been created.** `LimaProvider.create/start/stop/destroy/
exec/forward` and every line of `host/providers/omelet.yaml` remain unexecuted, and
**the UNVERIFIED banners in both files stay until this page records a real VM.**

What has now run on a real Apple Silicon Mac is recorded under
"2026-09-15" below — steps 1 and 2 of `lima-spike-checklist.md`, and nothing past
them. Everything in the next section is still the run that has to happen.

## 2026-09-15 — steps 1 and 2, on macOS 26.6.2 (build 25G83), arm64

Run from a source checkout under Python 3.13.15, with Lima **not** installed.

- **Step 1, the suite: 437 passed, 7 failed.** None of the seven is a product
  bug on the host path, and none involves `LimaProvider`:
  - `tests/engine/test_install_agents.py` (4) and `tests/engine/test_get_sh.py`
    (2) run the guest shell scripts *on the host*, where BSD `sed` and BSD `tar`
    are not the GNU tools those scripts are written against
    (`sed: 1: "...": invalid command code v`). The scripts themselves only ever
    run inside Ubuntu. This is the test harness being Linux-only, not the
    engine.
  - `tests/agent/test_health.py::test_proc_net_addresses_decode_byte_order_correctly`
    is a Python version difference, not a platform one: 3.13's `ipaddress`
    renders an IPv4-mapped address as `::ffff:127.0.0.1` where the expectation
    says `::ffff:7f00:1`. The decoder is right; the literal in the test is
    version-specific.

  Both classes would fail the same way on a Linux dev machine with Python 3.13,
  so "the suite is green" currently means "on Windows, on 3.12". Worth fixing
  before macOS is a supported dev platform; neither blocks the spike.
- **Step 2, `omelet doctor`:** one check, `limactl installed`, failing with
  `install Lima (brew install lima) or bundle limactl`, exit 1. Correct, and as
  low a bar as the checklist says it is.
- **`omelet setup --headless` reached its first step**, which it could not do
  before: `default_steps` called `provider.image()` and `LimaProvider` had no
  such method, so setup died with an `AttributeError` before preflight ran. It
  now stops at preflight with the Lima instruction above. See
  `docs/macos-install-test-matrix.md` case 4.

Steps 3 to 5 — VM create, end to end, lifecycle — are untouched: they need a
multi-gigabyte image download that was not run. **Lima 2.2.0 is now installed on
this machine** (`/opt/homebrew/bin/limactl`), so the spike is no longer blocked
on its prerequisite; `limactl start` has still never been called.

One finding came out of installing it, from the setup window rather than the
CLI: an app launched by LaunchServices is given
`PATH=/usr/bin:/bin:/usr/sbin:/sbin`, which contains neither Homebrew prefix, so
`is_supported()` reported Lima missing on a machine that had just installed it.
`lima.find_limactl` now falls back to `/opt/homebrew/bin` and `/usr/local/bin`
and the factory hands the provider an absolute path. Two things follow for the
run that is still pending: the same blindness applies to **anything else the
host shells out to by name** on macOS, and `limactl` itself will run with that
minimal PATH — whether it needs more is one of the unknowns step 3 answers.

## 2026-09-15 — `install_runtime`, run directly (Task 10)

`install_runtime` is the first macOS path that can be verified **without
booting a VM**: it ends by running the downloaded `limactl` and reading its
version back. Called `host.providers.lima_install.install()` directly — the
function `LimaProvider.runtime().run()` wraps — against this machine's real
`~/.local/share/omelet`, on the same macOS 26.6.2 (build 25G83) arm64 machine
as the run above. It completed in 3.51s: downloaded and checksum-verified
`lima-2.2.0-Darwin-arm64.tar.gz`, extracted it, ran the staged binary before
swapping it into place, and left `~/.local/share/omelet/lima/bin/limactl
--version` printing `limactl version 2.2.0`. See
`docs/macos-install-test-matrix.md` case 4.

`~/.lima/<name>/ssh.config` now has **two** readers — `LimaProvider.forward()`
and `LimaProvider.access()`. Its existence, name and layout are still an
assumption no live run has confirmed; the difference this work makes is that a
wrong assumption now shows on the status screen a user looks at first, instead
of only inside a port forward nobody exercises.

`omelet.yaml` now declares an `x86_64` image alongside the `aarch64` one, but
it still sets `rosetta.enabled: true`. Rosetta is an arm64-only feature.
Nobody has run an Intel build, so this is an open question for that run, not a
defect or a fix.

**Everything else is unchanged.** No VM has been created by this work.
`create_vm` is still the first unproven step, and `vz`, Rosetta, the port
forwards and the ssh control master are all still assumptions. **The
UNVERIFIED banners in `host/providers/lima.py` and `host/providers/omelet.yaml`
stay.** `forwards()` still returns an empty list on Lima; that open question is
not touched by this work.

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
