# Lima spike — does the macOS provider work at all?

**Goal:** find out whether `LimaProvider` can create a VM and serve HTTP 200,
before anyone builds a `.pkg` around it. Output is an answer, not code to keep.

`runtime/providers/lima.py` and `runtime/providers/runtime.yaml` are marked
UNVERIFIED — written for parity against the `VmProvider` contract and never
executed. Their command construction is unit-tested; nothing else is.

**Time:** one sitting. **Machine:** Apple Silicon Mac, macOS 13+.
Record the actual output of every step, especially failures.

---

## Setup

```bash
brew install lima              # spike only — the real installer will bundle limactl
limactl --version              # record it
git clone <this repo> && cd poc
python3 --version              # must be 3.12+
pip install -e ".[dev]"
```

## Step 1 — the suite passes on macOS

```bash
pytest -q
```

Expect 82 passed. A failure here is a portability bug in code we believed was
platform-free, which would be a finding in itself.

## Step 2 — doctor

```bash
runtime doctor
```

Expect a single check, `limactl installed`, passing, and exit code 0.
`LimaProvider.is_supported()` only shells out to `which`, so this is a low bar —
it passing tells you almost nothing beyond "the factory picked the right
provider".

## Step 3 — VM create (the first real unknown)

```bash
runtime vm create
```

This runs `limactl start --name=runtime-vm --tty=false <repo>/runtime/providers/runtime.yaml`
and then the guest bootstrap. Watch for:

- Does `limactl start` accept a config path as a positional argument in your
  Lima version? **This is the single most likely breakage** — Lima's CLI surface
  has moved over releases.
- Does `vmType: vz` start, or does it need `qemu`?
- Does `rosetta.enabled: true` prompt for a license, block, or fail?
- Does the arm64 Ubuntu 24.04 cloud image download and boot?
- Does `limactl shell runtime-vm sudo ...` work without an interactive password
  prompt? `LimaProvider.exec(root=True)` just prepends `sudo` — if Lima's guest
  requires a TTY for sudo, this hangs or fails.

Then confirm the guest side:

```bash
limactl shell runtime-vm sudo docker ps           # traefik running?
limactl shell runtime-vm cat /opt/runtime/.bootstrapped   # should print 1
```

If bootstrap failed, it now raises with the guest's own stderr — capture that
message verbatim.

## Step 4 — end to end

```bash
runtime up ./runtime/templates/nginx-hello
```

Record the printed URL, then:

```bash
curl -v http://nginx-hello.127-0-0-1.sslip.io:39080
```

**HTTP 200 is the pass condition for the whole spike.** Anything less means the
macOS installer is sitting on unproven ground.

If it fails, isolate where:

```bash
curl -v http://127.0.0.1:39080                    # does the port forward work at all?
limactl shell runtime-vm sudo docker ps           # is the container up?
limactl shell runtime-vm sudo docker logs traefik # is Traefik routing?
```

The `portForwards` block in `runtime.yaml` is declarative and, like everything
else here, unverified — a failure at `127.0.0.1:39080` with a healthy container
points there.

## Step 5 — lifecycle

```bash
runtime status
runtime down nginx-hello
runtime vm stop
runtime vm destroy       # should leave no VM in `limactl list`
```

## Report

For each step: passed, or the exact command and its exact output. Then the
verdict:

- **All green** → the macOS spec is mostly packaging; the install engine from
  the Windows spec is reused unchanged.
- **Fails in `limactl` argv** (steps 3/5) → cheap fix, provider-local.
- **Fails in networking** (step 4) → the port-forwarding design needs rework
  before any packaging work is worth doing.

Also note anything that needed a manual step, a prompt, or a wait — every one of
those becomes something the installer must handle without a human present.
