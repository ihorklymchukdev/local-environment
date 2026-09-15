# macOS installer manual test matrix

The release gate for `dist/OmeletSetup-<version>.pkg`, built by
`packaging/macos/build.sh`. None of these run in CI. Record the date, the build,
and the verbatim output for every run; do not mark a case passed without it.

**The rows below are not independent of the Lima question.** Cases 1–3 are about
the package, and are answerable today. Cases 4–8 all run through
`LimaProvider`, which has never created a VM — see
`docs/lima-verification-report.md`. A failure there is a provider finding, not a
packaging one, and it belongs in that report.

| # | Case | What it proves | Pass condition | Date | Build | Outcome |
|---|---|---|---|---|---|---|
| 1 | `bash packaging/macos/build.sh` on Apple Silicon | The build itself | Exits 0; `omelet version` and `omelet selfcheck` both pass against the frozen binary inside the .app | 2026-09-15 | local, 0.1.0, PyInstaller 6.22.3, Python 3.13.15 | **PASS.** `selfcheck` resolved both assets inside the bundle — `nginx-hello` through `Contents/Resources`, `omelet.yaml` through `Contents/Frameworks`. Two defects found and fixed by building: the two executables were named `Omelet` and `omelet`, which are one file on a case-insensitive filesystem, and BUNDLE wrote `CFBundleExecutable=omelet` with `LSBackgroundOnly=true` — a double-click would have run the CLI, windowless. Both are asserted in `build.sh` now. |
| 2 | Install the .pkg on a machine that has never had Omelet | The real first-run path | Installer completes; `/Applications/Omelet.app` exists; `omelet version` works in a **new** shell (the symlink is on PATH) | UNRUN | UNRUN | UNRUN |
| 3 | Open Omelet.app from Finder | The setup window is the app, not the CLI | The tkinter window opens with a Dock icon and runs the steps; it does not flash a terminal or exit immediately | **PASS, with two defects found and fixed** | 2026-09-15, local 0.1.0 | The window opened, listed every step, marked `preflight` failed, and showed both the raw error and the plain-language sentence above a working Close button. It also showed two things that were wrong, neither visible from the CLI: the step list included "Turning on Windows features" and "Restart needed" (now dropped for a provider with `remediable = False`), and preflight failed on a machine with Lima installed — an app started by LaunchServices has `PATH=/usr/bin:/bin:/usr/sbin:/sbin`, so Homebrew's `limactl` was invisible to it (now resolved by `lima.find_limactl`). Re-run to confirm both. |
| 4 | Setup on a Mac without Lima | The dead end reads as an instruction | Setup stops at preflight saying `install Lima (brew install lima)`, with no stack trace | **PASS (from source)** | 2026-09-15, source checkout | `omelet setup --headless` printed exactly that and exited 1. Before this branch it raised `AttributeError: 'LimaProvider' object has no attribute 'image'` before its first step. Re-run against the installed .pkg. |
| 4b | Setup with Lima installed, under a Finder-like environment | The Homebrew lookup, which is what case 3 tripped over | `omelet doctor` passes with `env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin` | **PASS** | 2026-09-15, frozen 0.1.0 | Checked against the binary inside the built `Omelet.app`, not just from source: `✓ limactl installed`, exit 0. Lima 2.2.0 at `/opt/homebrew/bin/limactl`. |
| 5 | Setup on a Mac with Lima installed | The whole install engine on macOS | Every step completes and `verify` returns a real HTTP 200; **record the wall-clock time** | UNRUN | UNRUN | UNRUN |
| 6 | Re-run setup on a provisioned Mac | Idempotency | `preflight`/`remediate`/`reboot_gate` report skipped, the rest re-run, exit 0 | UNRUN | UNRUN | UNRUN |
| 7 | `packaging/macos/uninstall.sh` | Cleanup | `limactl list` no longer shows `omelet-vm`; the app, the `/usr/local/bin/omelet` symlink and the pkg receipt are all gone | UNRUN | UNRUN | UNRUN |
| 8 | Install the .pkg over an existing install | Upgrade | The new build replaces the old one in place; the existing VM is left alone and `omelet setup` finds it | UNRUN | UNRUN | UNRUN |

## Notes for the operator

- **The build is native-arch, not universal.** `distribution.xml` stamps the
  building machine's `uname -m` into `hostArchitectures`, so an Apple Silicon
  build refuses to install on Intel rather than installing binaries it cannot
  run. An Intel Mac needs its own build from an Intel machine.
- **Unsigned builds are blocked by Gatekeeper on a double-click** once the file
  has been downloaded (a locally-built .pkg carries no quarantine flag, so it
  opens normally — which means case 2 must be run against a *downloaded* copy to
  mean anything). Right-click > Open, or
  `sudo installer -pkg dist/OmeletSetup-<version>.pkg -target /`. Set
  `OMELET_CODESIGN_ID` and `OMELET_INSTALLER_ID` to sign; notarization is not
  wired up.
- **Nothing in the installer runs setup for the user**, unlike the Windows
  installer's postinstall checkbox. Lima keeps VMs per user under `~/.lima` and
  the postinstall script runs as root, so a VM built there would belong to a
  user who cannot see it. Case 3 is the affordance that replaces it.
- **Case 7 is destructive** — it deletes the VM and every project in it. Only
  run it where that is disposable.
