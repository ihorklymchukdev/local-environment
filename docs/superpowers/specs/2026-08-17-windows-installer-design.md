# Design: Windows installer for non-technical users

**Status:** approved design, pending implementation plan
**Scope:** Windows/WSL2 end-to-end, plus the platform-free install engine both
platforms will share. macOS is deferred to a second spec (see §13).

---

## 1. Purpose

A person who does not use a terminal downloads one file from our website,
double-clicks it, and ends up with a working local runtime: a Linux VM with
Docker and Traefik inside it, proven by a real HTTP request.

Today the only path is `pip install -e .` followed by `runtime vm create` with a
`RUNTIME_ROOTFS` environment variable pointing at a manually downloaded rootfs.
Every step of that is out of reach for the target user.

Distribution is pilot-first (a handful of known testers) moving to public
download from our website. The build is therefore **unsigned but sign-ready**:
signing is a drop-in step, not a rewrite (§10).

## 2. Non-goals

- **A way to run projects without a terminal.** After setup the user still needs
  `runtime up <dir>`. A drag-and-drop launcher is the agreed next phase; this
  design only ensures it has something to call (§4).
- **Automatic updates.** Out of scope; a new installer is a new download.
- **Telemetry.** Diagnostics are copied to the clipboard by the user, never
  transmitted.
- **Supporting machines that cannot run WSL2 at all** (virtualization disabled
  with no BIOS access, unsupported Windows edition). These are detected and
  explained, not worked around.

## 3. Constraints and established facts

- **Enabling WSL2 requires administrator rights and a reboot.** `wsl --install`
  turns on Windows optional features. No installer can avoid the UAC prompt or
  the restart. The design absorbs this rather than pretending otherwise.
- **The CLI must run on Windows, not inside WSL.** `get_provider()` raises
  `unsupported host platform: linux` on a WSL-side Python.
- **Rootfs source** (verified live 2026-08-17): Canonical's official WSL image,
  the file Microsoft's own WSL distro manifest points at.
  - amd64: `https://releases.ubuntu.com/24.04.4/ubuntu-24.04.4-wsl-amd64.wsl`
    391 MB, sha256 `9b2f7730dc68227dd04a9f3e5eab86ad85caf556b8606ad94f1f29ff5c4fd3f5`
  - arm64: `https://cdimages.ubuntu.com/releases/24.04.4/release/ubuntu-24.04.4-wsl-arm64.wsl`
    sha256 `6b244d89f412a68f51e58f396fab65bed3b5896a25c045a99bef9c78a07df507`
  - `cloud-images.ubuntu.com/wsl/` now holds **only manifests** — it is not a
    valid source and must not be used.
- **PyInstaller cannot cross-compile.** Windows artifacts are built on Windows,
  macOS artifacts on macOS. CI is optional (§9).
- **The platform-boundary invariant holds.** `tests/test_no_platform_leak.py`
  forbids `sys.platform` / `platform.system()` / `os.name` outside
  `runtime/providers/`. The installer must not weaken it.

## 4. Architecture

Two artifacts with different jobs and different lifetimes. This split is the
central structural decision.

| Artifact | Job | Duration | Admin? |
|---|---|---|---|
| `LocalRuntimeSetup-<version>.exe` | Lay down files, PATH entry, Start Menu shortcut, uninstaller | seconds | No (per-user install) |
| **Setup app** (`runtime.exe setup`) | Preflight → enable WSL2 → reboot → resume → fetch rootfs → create VM → bootstrap → verify | minutes, may span a restart | Only for one scoped command |

Rationale: the reboot happens inside our own app, where we control resume, not
inside an installer transaction where it is painful. Provisioning failures never
leave the *installed files* in a half-state — the user just relaunches the setup
app. "Installed" and "provisioned" become separately inspectable, which matters
for support.

### Module layout

```
runtime/
  core/
    install.py        # NEW — platform-free state machine, steps, progress events
    download.py       # NEW — resumable download + SHA256 verification
    provider.py       # extended — CheckResult gains a remedy field
  providers/
    wsl2.py           # extended — preflight probes, feature enablement, reboot signal
    lima.py           # extended later (macOS spec)
  setup_app/
    __init__.py       # NEW — tkinter progress window, log pane, diagnostics
packaging/
  windows/
    runtime.spec      # PyInstaller (one-dir)
    installer.iss     # Inno Setup
    build.ps1         # freeze + package, runs identically locally and in CI
```

### Keeping the platform boundary

`core/install.py` knows the *order* of steps and nothing about Windows. Each
step delegates its platform-specific part to the provider. This extends
contracts that already exist:

- `is_supported() -> Diagnosis` is already a preflight. It gains checks.
- `render_diagnosis()` already renders checks with fix hints for humans.
- `CheckResult` gains `remedy: str | None` — an identifier the engine maps to an
  action. `None` means "the user must fix this themselves" (BIOS), a value means
  "we can fix it" (`enable_wsl_features`).

New provider methods, added to the `VmProvider` Protocol:

```python
def preflight(self) -> Diagnosis: ...          # richer than is_supported()
def apply_remedy(self, remedy: str) -> None: ...  # may require elevation
def reboot_required(self) -> bool: ...
```

`LimaProvider` implements the same three, which is what makes the macOS spec
mostly packaging work.

### Hook for the future launcher

The frozen binary keeps the existing Typer CLI and gains `runtime setup`. The
Start Menu shortcut, the reboot-resume registry value, and the future
drag-and-drop launcher all invoke the same binary. No third artifact.

## 5. The state machine

Eight ordered steps. Each is idempotent and records completion to
`%LOCALAPPDATA%\Runtime\install-state.json`, so a re-run or a post-reboot
resume skips finished work.

| # | Step | Fails how |
|---|---|---|
| 1 | `preflight` | Dead-end checks stop with instructions |
| 2 | `remediate` | Elevation declined, or feature enablement fails |
| 3 | `reboot_gate` | Cannot fail; either required or skipped |
| 4 | `fetch_image` | Network, disk space, checksum mismatch |
| 5 | `create_vm` | `wsl --import` non-zero, bad rootfs |
| 6 | `bootstrap` | apt/Docker/Traefik failure, with guest stderr |
| 7 | `verify` | Container did not serve HTTP 200 |
| 8 | `finish` | — |

### Step 1 — preflight

Windows checks, each classified auto-fixable or dead-end:

| Check | Source | Class |
|---|---|---|
| Windows build ≥ 19045 | `sys.getwindowsversion()` | dead-end |
| Virtualization enabled in firmware | `Win32_ComputerSystem.HypervisorPresent`, `Win32_Processor.VirtualizationFirmwareEnabled` | dead-end (BIOS) |
| `VirtualMachinePlatform` + WSL features | `dism`/feature query | auto-fix |
| `wsl --version` reports Store WSL | `wsl --version` | auto-fix (`wsl --update`) |
| ≥ 10 GB free on the system drive | `shutil.disk_usage` | dead-end |

The firmware-virtualization check earns its place: it is a common consumer-machine
blocker that otherwise surfaces as an opaque WSL error, and no code can fix it —
only a plain-language "restart into BIOS/UEFI and enable Intel VT-x or AMD-V".

### Step 2 — remediate, with elevation scoped to one command

The app runs **unelevated**. When a remedy needs admin, it re-launches only that
command via `ShellExecuteW` with the `runas` verb, then returns to the
unelevated process.

This is not fastidiousness. If the whole app ran elevated, `%LOCALAPPDATA%`
would resolve to the *administrator's* profile, and the 391 MB rootfs cache plus
the install state would be written into the wrong user's directory — an
invisible failure that only appears on machines where the admin account differs
from the logged-in user. Scoping elevation eliminates the class.

Primary remedy: `wsl --install --no-distribution` (enables features and installs
the WSL kernel without adding a distro we don't want).

### Step 3 — reboot gate and resume

If step 2 enabled Windows features, a restart is required. The app:

1. Writes `HKCU\Software\Microsoft\Windows\CurrentVersion\RunOnce` →
   `"<install dir>\runtime.exe" setup --resume`
2. Shows: *"Restart your computer. Setup will continue on its own when you log
   back in."*

`RunOnce` under `HKCU` fires at that user's next logon and deletes itself, so a
user who never restarts is not left with a permanent startup entry.

### Step 4 — fetch image

Resumable HTTP range download to `%LOCALAPPDATA%\Runtime\cache`, SHA256 verified
against the constant in §3. A cached file with a matching hash is reused; a
mismatched file is deleted rather than trusted.

### Steps 5–6 — create and bootstrap

`provider.create()` then `bootstrap(provider)`. Both now raise on failure with
the underlying error attached — `BootstrapError` carries the guest's own stderr.
This was previously silent: every `exec` result was discarded and `vm create`
printed `VM ready.` regardless. That defect is fixed; this design depends on it.

### Step 7 — verify

Run the repo's existing `runtime/templates/nginx-hello` compose project, request
the resulting URL, require **HTTP 200**, then tear it down.

Without this, "setup complete" means "nothing returned non-zero" — which we know
from direct experience is not the same thing. With it, success means a real
container served a real request through Traefik on the real port.

### Step 8 — finish

Write final state, show the install location and the exact next command.

## 6. Progress and error reporting

A tkinter window: a step list with per-step status, a progress bar for the long
steps, and a collapsible log pane. tkinter ships with CPython and PyInstaller
bundles it cleanly; the project's runtime dependencies are exactly `typer` and
`pyyaml`, and a progress bar does not justify adding a GUI framework and its
packaging problems to that list.

On failure the window shows the step, the underlying error, a suggested action,
and a **Copy diagnostics** button that puts the log tail plus host details
(Windows build, WSL version, architecture, free disk) on the clipboard for the
user to paste to us. Full log at
`%LOCALAPPDATA%\Runtime\logs\setup-<timestamp>.log`.

## 7. Packaging

**Freeze:** PyInstaller **one-dir**, not one-file. One-file unpacks to a temp
directory on every launch — slower startup, and it is the mode antivirus
heuristics dislike most. An installer wraps the output anyway, so one-file buys
nothing.

**Installer:** Inno Setup → `LocalRuntimeSetup-<version>.exe`, installing
**per-user** into `%LOCALAPPDATA%\Programs\LocalRuntime`
(`PrivilegesRequired=lowest`). Per-user is deliberate: the install itself needs
no admin, so the only UAC prompt in the entire experience is the scoped one in
step 2. Adds a Start Menu entry, a PATH entry, and an uninstaller.

Version is sourced from `pyproject.toml` and injected into both the PyInstaller
spec and the Inno script; it is not duplicated by hand.

## 8. Uninstall

The Inno uninstaller runs `runtime.exe uninstall --purge` before removing files:
`wsl --unregister runtime-vm`, delete the rootfs cache, delete install state and
`state.db`.

It must warn explicitly that **every project inside the VM is destroyed** —
project files live in the guest at `/opt/runtime/projects/`, not on the host.

## 9. Build pipeline

`packaging/windows/build.ps1` runs identically on a developer machine and in CI:
freeze → package → emit `dist/LocalRuntimeSetup-<version>.exe`.

CI is **optional**. PyInstaller's inability to cross-compile is the only reason
it came up, and the pilot already has both required machines. If adopted later,
GitHub Actions on `windows-latest` works in a private repo (2,000 free
minutes/month on Free, 3,000 on Pro/Team; Windows standard runners bill at
$0.010/min beyond that — well under a dollar per release). Private is mildly
preferable once signing secrets exist.

## 10. Signing — designed in, purchased later

Build scripts read certificate material from environment variables and skip
signing when absent, so unsigned pilot builds and signed public builds are the
same pipeline.

- **Windows:** `signtool` over both `runtime.exe` and the setup executable. An
  EV certificate carries immediate SmartScreen reputation; an OV certificate
  accumulates it over time. Unsigned produces a scary but clickable warning.
- **macOS (for the later spec):** notarization is **not optional the way Windows
  signing is.** Un-notarized apps are hard-blocked by Gatekeeper on current
  macOS. Pilot testers can right-click → Open; a website download cannot. This
  requires Apple Developer Program membership ($99/yr) before the Mac half goes
  public.

## 11. Testing

**Automated** — logic with branches where a wrong result is plausible:

- State machine: step ordering, resume-from-state after a simulated reboot,
  idempotent re-runs, auto-fix vs dead-end classification, and that a dead-end
  check stops the run instead of attempting a remedy.
- Preflight parsers against **captured real output** from `wsl --version`, the
  WMI queries, and `systeminfo`. This is the seam where our code meets an
  external contract whose format varies by Windows version.
- Download helper: checksum mismatch deletes the file; a matching cached file is
  reused without re-downloading.

Not worth writing: tests that re-assert tkinter, Inno Setup, or PyInstaller.

**Manual matrix** — the honest part:

1. Windows with WSL2 already present (the upgrade path) — available today
2. Clean Windows VM, WSL2 never enabled — the real first-run path *including the
   reboot*. The most important case and the least convenient to produce; nested
   virtualization under Hyper-V makes it possible but not pleasant.
3. Windows VM with virtualization disabled — verifies the dead-end message

**Untestable before it exists:** SmartScreen behavior prior to signing, and the
long tail of OEM firmware.

## 12. Risks

| Risk | Mitigation |
|---|---|
| Antivirus flags the frozen binary | One-dir over one-file; signing when purchased |
| Case 2 (clean machine) is awkward to reproduce, so the reboot path stays under-tested | Treat it as a release gate, not a nice-to-have |
| Corporate machines block WSL2 by policy | Out of scope (§2); preflight reports it clearly |
| Rootfs URL changes when Canonical ships 24.04.5 | URL + hash are constants in one module; a stale hash fails loudly at step 4 rather than installing a wrong image |

## 13. macOS — deferred, and why

macOS is agreed as a product requirement and is **not in this spec**. In pure
code the Mac delta is slightly *smaller* than Windows — no elevation dance, no
reboot, no registry. The risk profile is what differs: `LimaProvider` has never
executed. `limactl start` with our `runtime.yaml`, the `vz` VM type, Rosetta,
`limactl shell` with sudo, and port forwarding on 39080 are all tested only at
the level of "we built the right argv".

Bundling Lima is also the one genuinely fiddly packaging job: `limactl` **and**
its guest-agent binaries must ship together, and getting that layout wrong
yields a Lima that half-works confusingly. Lima is Apache-2.0, so
redistribution itself is fine.

**Therefore:** run the Lima spike (`docs/lima-spike-checklist.md`) on real
hardware first. If it reaches HTTP 200, the macOS spec is mostly packaging and
reuses the entire engine in §4–§6 unchanged. If it does not, that is discovered
for the cost of an afternoon instead of after building an installer around it.

## 14. Open decisions

- Code-signing certificate type and vendor (Windows), and whether to buy before
  or after the pilot.
- Whether the future launcher is a drag-and-drop window or a tray app — affects
  nothing here, but will reuse `runtime.exe`.
