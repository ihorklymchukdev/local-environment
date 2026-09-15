# Lima / macOS verification — confirmed once, mostly still unverified

**Status: a VM created from this project's own config has run, once, and was
found rather than made under a controlled session.** On 2026-09-15, on macOS
26.6.2 (build 25G83) arm64 with Lima 2.2.0, a VM named `omelet-vm` was created
from the pre-`33571da` revision of `host/providers/omelet.yaml` (`create()`'s
own `limactl start --name=omelet-vm --tty=false <config>` invocation), booted
under `vz`, ran the full engine bootstrap to `engine-v0.0.1`, and answered
both declared `portForwards` — `curl 127.0.0.1:39099/health` returns 200 with
`docker.reachable: true`. `~/.lima/omelet-vm/ssh.config` exists at exactly the
path `forward()` and `access()` assume. This was established by inspecting
the VM after the fact (`limactl list`, `limactl shell omelet-vm cat
/opt/omelet/engine.version`, reading `ssh.config` directly) on 2026-09-15,
roughly six hours after the VM's creation — **nobody ran this as a recorded,
controlled session**, so treat it as real evidence of what the code path can
do, not as a rehearsed, repeatable install.

**Still unproven, and what a next session should target:** `forward()`
tunnelling a *distinct* port through the ssh control master (only the two
`portForwards` declared in `omelet.yaml` have been exercised); `forwards()`
listing anything; `stop()`/`destroy()` and the uninstall path; whether Lima
honours `omelet.yaml`'s `ssh.localPort` at all — the VM found predates that
field, so this is untested, not disproven; the `x86_64` image, added after
this VM was created; and whether `rosetta.enabled: true` is functional inside
the guest, as opposed to merely not preventing boot (all that this VM proves).
**The UNVERIFIED banners in `host/providers/lima.py` and
`host/providers/omelet.yaml` stay** — rewritten to say what is and is not
confirmed, not removed — because one arm64 machine, one now-superseded config
revision, and half the provider surface are not the whole contract.

What has now run on a real Apple Silicon Mac is recorded under
"2026-09-15" below — steps 1 and 2 of `lima-spike-checklist.md`, and nothing past
them, plus the `install_runtime` and after-the-fact-inspection sections that
follow. A repeatable, recorded run of `create_vm` through to `verify` is still
the session this page is waiting for.

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

**No VM has been created by this work** — `install_runtime` only fetches and
verifies `limactl` itself. That is correctly scoped to this section. What is
**not** correctly scoped, and is fixed below rather than here: `create_vm`
is not "the first unproven step" project-wide — see the next section, which
records a VM that was found already running this exact config, created
before this work began. `forwards()` still returns an empty list on Lima;
that open question is not touched by this work.

## 2026-09-15 — the pre-existing `omelet-vm`, inspected after the fact

While doing the `install_runtime` run above, `~/.lima/omelet-vm` was found
already on this machine, `limactl list` showing it `Running`. It was
inspected read-only — no `create`, `start`, `stop` or `destroy` call was made
against it — and the results are the "confirmed once" claims in the Status
section above. The commands and their output:

```
$ diff <(cat ~/.lima/omelet-vm/lima.yaml) <(git show 3560692:host/providers/omelet.yaml)
(no output -- byte-identical, banner and portForwards comments included)

$ limactl list
NAME         STATUS     SSH                VMTYPE    ARCH       CPUS    MEMORY    DISK     DIR
omelet-vm    Running    127.0.0.1:50998    vz        aarch64    4       4GiB      60GiB    ~/.lima/omelet-vm

$ limactl shell omelet-vm cat /opt/omelet/engine.version
engine-v0.0.1

$ curl 127.0.0.1:39099/health
{"...", "docker": {"reachable": true, ...}}
```

`/opt/omelet` inside the guest holds `agent.token`, `stack.yml`, `state.db`
and a populated `projects/` — the full engine install ran, not just a boot.
`~/.lima/omelet-vm/ssh.config` exists with a quoted `IdentityFile` and `Port
50998` (the live ssh port Lima picked — not `39022`, the value
`omelet.yaml`'s now-unexecuted `ssh.localPort` requests; see the port finding
below). The `lima.yaml` on disk is byte-identical to `git show
3560692:host/providers/omelet.yaml`, which predates both the `x86_64` image
and the `ssh:` block — this VM was created by exactly `LimaProvider.create()`
against that revision, most likely by a human running this project's own
`omelet setup` (see below for why the timing points at `setup` rather than a
bare `limactl start`), not by any automated test.

**Correcting a misreading in an earlier draft of this page — twice now.**
`~/.local/share/omelet/install-state.json` on this machine shows
`{"completed": ["preflight"]}`. A first draft read that as evidence the VM's
creation was unaccounted for by `omelet setup`'s own tracked steps — backwards,
since `install-state.json` never persists an `always_run` step, and *every*
step in `default_steps` after `preflight` (`install_runtime`, `create_vm`,
`bootstrap`, `connect`, `verify`, `finish`) is `always_run`. A second draft
then overcorrected the other way, calling `{"completed": ["preflight"]}`
"exactly the state a fully successful run leaves behind" and the VM's
creation "not a hand-run `limactl start`" — but for the same reason nothing
after `preflight` is ever persisted, this file is equally consistent with a
run that died at any of those later steps. It cannot by itself tell success
from interruption, and a 2.5-hour gap between the VM's creation (10:37) and
the engine install finishing (~13:10) is not what an uninterrupted run looks
like either — that gap is itself evidence against "one ordinary,
uninterrupted run", not for it.

The evidence that actually says something is a timestamp, not the file's
contents: `install-state.json`, `~/.lima/omelet-vm/lima.yaml` and
`~/.lima/omelet-vm/lima-version` were all written in the same second,
`2026-09-15 10:37:54` (confirmed directly: `stat -f "%Sm" -t "%Y-%m-%d
%H:%M:%S" ~/.local/share/omelet/install-state.json
~/.lima/omelet-vm/lima.yaml ~/.lima/omelet-vm/lima-version`, all three lines
identical). `install-state.json` is written only by `InstallState.mark()`,
called only from inside `run_install()` immediately after `preflight`
succeeds — nothing about a bare `limactl start` touches that path at all.
For it to land in the same second as the files Lima itself writes when
`create()` runs, `preflight` finishing and `create_vm` starting must have
been roughly one second apart, which is what one continuous `omelet setup`
process looks like far more than two separately-timed invocations
coincidentally landing in the same second. **What this does and does not
show:** it is good evidence that `omelet setup`'s own code path, not a
bare `limactl start`, is what created this VM. It says nothing about
whether that same run went on to reach `bootstrap`, `connect`, `verify` or
`finish` — none of those are persisted either, so the engine actually being
installed (confirmed separately, above) is evidence for `bootstrap` having
run, not for the run as a whole having completed.

**One thing this VM cannot answer, and does not disprove:** whether Lima
honours `omelet.yaml`'s `ssh.localPort`. Its `lima.yaml` predates that field
entirely (it was added in `33571da`, after this VM was created), and Lima
stores the config it was started with verbatim — so the live SSH port being
50998 rather than 39022 proves only that the field was never passed, not that
Lima would ignore it if it were. Untested, not disproven.

**Do not delete this VM.** It is the only live macOS evidence this project
has, and `/opt/omelet/projects` may hold real project state.

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
