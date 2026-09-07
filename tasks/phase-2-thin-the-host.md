# Phase 2: Thin the host

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Prerequisite: Phase 1 is complete and merged.** Its closing test — no module under `host/`
> imports from `agent/` — must already be green. If it is not, stop and finish Phase 1.

**Goal:** Reduce the host to VM lifecycle and installation, and nothing else. When this phase
lands, each platform's code is a few hundred lines of "make a Linux VM exist and forward a
port", macOS becomes verifiable for the first time, and the raw TCP forwarding gap that blocks
database access is closed.

**Architecture:** The `VmProvider` Protocol loses every method that exists to carry project
logic and keeps only lifecycle. Whatever the agent now owns is deleted from the host rather
than left as dead code. `forward()` stops raising `NotImplementedError` for distinct ports.

**Tech stack:** Python 3.12. Host dependencies: `typer` plus stdlib. No additions.

**Context:** `docs/architecture-and-roadmap.md` (Part 2.2 and Part 5), `tasks/phase-1-agent-in-the-vm.md`.

---

## Global constraints

- **The host's dependency list must shrink, never grow.** `pyyaml` should already be gone after
  Phase 1 Task 9. Nothing replaces it.
- **Platform-boundary invariant holds and gets stricter.** After this phase the *only* code that
  may mention `sys.platform`, `platform.system()` or `os.name` is `host/providers/`. The agent
  never touches it at all, because the agent does not know what a host is.
- **Guest failures stay loud.** `provider.exec()` returns a `Completed` and never raises. Every
  caller checks `.ok`.
- **`wsl.exe` output encoding is split.** Meta commands (`-l`, `--version`, `--import`) emit
  UTF-16LE; command passthrough emits UTF-8. `decode_wsl()` sniffs NUL bytes to choose. Use
  `_meta()` for meta commands and `exec()` for passthrough. Mixing them corrupts output.
- **No test spawns a real subprocess or VM.** Provider tests inject a `FakeRunner` that records
  argv and returns scripted bytes. Assertions are about **constructed argv and decoded output**,
  never side effects.
- **Running tests:** `python3 -m pytest -q`, prefixed with `TMPDIR=<writable dir>` in this
  sandbox. Baseline is whatever Phase 1 closed at — record it before starting.

---

## File structure

**Modify:**

| File | Change |
|---|---|
| `host/core/provider.py` | Reduce the Protocol to lifecycle. Delete carrier methods. |
| `host/providers/wsl2.py` | Implement real distinct-port forwarding. Drop anything not lifecycle. |
| `host/providers/lima.py` | Same, plus the parity pass that removes the UNVERIFIED banner. |
| `host/providers/omelet.yaml` | Lima VM config; port forwards reviewed. |
| `host/cli.py` | Remove any remaining logic that belongs to the agent. |
| `tests/test_no_platform_leak.py` | Tighten to the final layout. |
| `packaging/windows/omelet.spec` | Stop bundling agent code into the frozen binary. |

**Create:**

| File | Responsibility |
|---|---|
| `tests/host/test_forward.py` | Distinct-port forwarding argv on both providers. |
| `tests/host/test_provider_surface.py` | The Protocol has not regrown. |
| `docs/lima-verification-report.md` | Evidence from the first real macOS run. |

**Delete:** every host-side module whose responsibility moved to the agent in Phase 1, once
Task 2 proves nothing references it.

---

## Task 1: Reduce the provider contract

**Files:** modify `host/core/provider.py`; test `tests/host/test_provider_surface.py`.

The Protocol should describe one idea: *make a Linux VM exist, and let me reach it*. Anything
that exists to carry project logic across the boundary is now the agent's job.

Target surface:

```python
class VmProvider(Protocol):
    def is_supported(self) -> Diagnosis: ...
    def preflight(self) -> Diagnosis: ...
    def apply_remedy(self, remedy: str) -> None: ...
    def reboot_required(self) -> bool: ...
    def exists(self) -> bool: ...
    def create(self) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def destroy(self) -> None: ...
    def exec(self, argv: list[str], *, root: bool = False) -> Completed: ...
    def forward(self, guest_port: int, host_port: int) -> None: ...
```

`exec()` stays. It is still needed to bootstrap the VM and to read the agent token — but after
this phase it must have **no caller that carries project logic**.

- [ ] **Step 1:** Write a failing test that pins this method set exactly, so the Protocol cannot
      quietly regrow later. A future method that carries project data should break this test.
- [ ] **Step 2:** Reduce the Protocol. Keep providers duck-typed against it rather than
      subclassing, as they are today.
- [ ] **Step 3:** Add a test that every `exec()` call site under `host/` is either bootstrap or
      token reading. Anything else is logic that should have moved in Phase 1.

---

## Task 2: Delete what the agent now owns

**Files:** delete host-side modules; modify `host/cli.py`.

Dead code that still compiles is the most expensive kind, because the next reader cannot tell
which copy is authoritative.

- [ ] **Step 1:** List every module under `host/` with no remaining inbound reference. Include
      the check in the run, do not do it from memory.
- [ ] **Step 2:** Delete them, along with their tests. A test for deleted code is not coverage
      you are losing.
- [ ] **Step 3:** Walk `host/cli.py` command by command. Anything that still shapes, parses or
      interprets project data belongs to the agent — move it or delete it.
- [ ] **Step 4:** Confirm the host's declared dependencies are `typer` and nothing else.

---

## Task 3: Real distinct-port forwarding on WSL2

**Files:** modify `host/providers/wsl2.py`; test `tests/host/test_forward.py`.

`forward()` currently raises `NotImplementedError` whenever the guest and host ports differ.
That was a deliberate PoC boundary, not an oversight — the edge port is equal on both sides by
design. It now has to go, because reaching a database in the VM from a Windows tool is the most
requested thing after the URL itself.

- [ ] **Step 1:** Write a failing test asserting the constructed `netsh interface portproxy`
      argv for a distinct-port forward, against an injected `FakeRunner`. Assert on argv, never
      by running `netsh`.
- [ ] **Step 2:** Write a failing test that adding the same forward twice is idempotent, and one
      that removing a forward that is not there is not an error.
- [ ] **Step 3:** Write a failing test that a forward whose ports are equal still short-circuits
      to a no-op, since localhostForwarding already covers it.
- [ ] **Step 4:** Implement. Record allocated ports so they can be released, and so a restart
      does not leak them.
- [ ] **Step 5:** Document that `netsh portproxy` needs elevation, and route it through the same
      elevation path the installer already uses. Do not add a second UAC pathway.

---

## Task 4: Distinct-port forwarding on Lima

**Files:** modify `host/providers/lima.py`, `host/providers/omelet.yaml`;
test `tests/host/test_forward.py`.

- [ ] **Step 1:** Write the equivalent failing argv tests for `limactl`.
- [ ] **Step 2:** Implement, keeping the two providers behaviourally identical. The Protocol is
      the contract; a caller must not be able to tell which platform it is on.
- [ ] **Step 3:** Review `omelet.yaml`'s `portForwards`. Lima auto-forwards `0.0.0.0` binds,
      but an explicit entry is more reliable and the edge port should stay explicit.

---

## Task 5: Verify macOS for the first time

**Files:** modify `host/providers/lima.py`; create `docs/lima-verification-report.md`.

The Lima provider has never been executed. Both it and `omelet.yaml` carry an UNVERIFIED
banner. Phase 1 and Phase 2 together make this the first point where a real run is worth the
time, because almost nothing platform-specific is left to be wrong.

**This task requires a real Apple Silicon machine. It cannot be completed from CI or from a
Linux sandbox.** If no machine is available, stop, mark it blocked, and continue to Task 6 —
do not fake it and do not remove the banner.

- [ ] **Step 1:** Run `omelet doctor` on a clean macOS 13+ machine. Record the output verbatim.
- [ ] **Step 2:** Run the full install. Record elapsed time — the blueprint flags 15+ minutes as
      an existential product risk, so the number matters more than the pass.
- [ ] **Step 3:** Run the five acceptance compose files from `tests/fixtures/compose/`. Record
      how many came up untouched. That count is the real stack-agnosticism metric.
- [ ] **Step 4:** Confirm an arm64 image mismatch produces a clear explanation rather than a raw
      `exec format error`. Arbitrary compose files from GitHub regularly reference images with
      no arm64 build, and this is the same class of problem that will recur on cloud deploy.
- [ ] **Step 5:** Write the report. Remove the UNVERIFIED banners **only** for what the run
      actually covered, and say plainly what it did not.

---

## Task 6: Tighten the invariant test

**Files:** modify `tests/test_no_platform_leak.py`.

- [ ] **Step 1:** Scan `host/` and `agent/` under the final layout, exempting only
      `host/providers/`.
- [ ] **Step 2:** Add an assertion that `agent/` contains **no** platform reference at all, not
      even an exempted one. The agent runs on Linux in every deployment target it will ever
      have, including the cloud, so any platform branch there is a bug by construction.
- [ ] **Step 3:** Make the failure message say what to do — push the difference into a provider
      method — rather than only reporting the hit.

---

## Task 7: Package the host without the agent

**Files:** modify `packaging/windows/omelet.spec`, `packaging/windows/build.ps1`.

- [ ] **Step 1:** Stop bundling `agent/` into the frozen binary. It ships as an image and is
      always pulled.
- [ ] **Step 2:** Record the installer size before and after. The drop is the phase's most
      legible result, and download size is a real factor in first-run completion.
- [ ] **Step 3:** Keep PyInstaller **one-dir**, never one-file.
- [ ] **Step 4:** Confirm the frozen binary still resolves its bundled assets. `install.py`
      resolves `VERIFY_TEMPLATE` from its own module path rather than from `cli.py`, because
      `cli.py`'s `__file__` points at the bundle root when frozen. That fix must survive.

---

## Done when

- [ ] `python3 -m pytest -q` is green, with a stated new baseline.
- [ ] `VmProvider` has only the methods listed in Task 1, enforced by a test.
- [ ] No dead host-side module remains.
- [ ] The host's only declared dependency is `typer`.
- [ ] `forward()` handles distinct ports on both providers, and a database in the VM is
      reachable from a host tool.
- [ ] `agent/` contains no platform reference of any kind.
- [ ] macOS is either verified with a written report, or explicitly recorded as blocked with the
      banners left in place.
- [ ] The installer is measurably smaller.
