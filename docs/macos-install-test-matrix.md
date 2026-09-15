# macOS installer manual test matrix

The release gate for `dist/OmeletSetup-<version>.pkg`, built by
`packaging/macos/build.sh`. None of these run in CI. Record the date, the build,
and the verbatim output for every run; do not mark a case passed without it.

**The rows below are not independent of the Lima question.** Cases 1–3 are about
the package, and are answerable today. Cases 5–8 run through `LimaProvider`
end to end, which has been confirmed once — after the fact, not as a
recorded session — but is still mostly unverified; see
`docs/lima-verification-report.md`. Case 4 as rewritten below deliberately
does **not** run through `LimaProvider`: it calls `lima_install.install()`
directly, precisely to avoid touching `create_vm` against the VM that report
now documents. A failure in cases 5–8 is a provider finding, not a packaging
one, and it belongs in that report.

| # | Case | What it proves | Pass condition | Date | Build | Outcome |
|---|---|---|---|---|---|---|
| 1 | `bash packaging/macos/build.sh` on Apple Silicon | The build itself | Exits 0; `omelet version` and `omelet selfcheck` both pass against the frozen binary inside the .app | 2026-09-15 | local, 0.1.0, PyInstaller 6.22.3, Python 3.13.15 | **PASS.** `selfcheck` resolved both assets inside the bundle — `nginx-hello` through `Contents/Resources`, `omelet.yaml` through `Contents/Frameworks`. Two defects found and fixed by building: the two executables were named `Omelet` and `omelet`, which are one file on a case-insensitive filesystem, and BUNDLE wrote `CFBundleExecutable=omelet` with `LSBackgroundOnly=true` — a double-click would have run the CLI, windowless. Both are asserted in `build.sh` now. |
| 2 | Install the .pkg on a machine that has never had Omelet | The real first-run path | Installer completes; `/Applications/Omelet.app` exists; `omelet version` works in a **new** shell (the symlink is on PATH) | UNRUN | UNRUN | UNRUN |
| 3 | Open Omelet.app from Finder | The setup window is the app, not the CLI | The tkinter window opens with a Dock icon and runs the steps; it does not flash a terminal or exit immediately | **PASS, with two defects found and fixed** | 2026-09-15, local 0.1.0 | The window opened, listed every step, marked `preflight` failed, and showed both the raw error and the plain-language sentence above a working Close button. It also showed two things that were wrong, neither visible from the CLI: the step list included "Turning on Windows features" and "Restart needed" (now dropped for a provider with `remediable = False`), and preflight failed on a machine with Lima installed — an app started by LaunchServices has `PATH=/usr/bin:/bin:/usr/sbin:/sbin`, so Homebrew's `limactl` was invisible to it (now resolved by `lima.find_limactl`). Re-run to confirm both. |
| 4 | Setup on a Mac without Lima | Setup **installs** Lima itself | `install_runtime` completes; `~/.local/share/omelet/lima/bin/limactl --version` prints `limactl version 2.2.0` | 2026-09-15 | local source checkout, .venv Python 3.13.15 | **PASS.** Ran `host.providers.lima_install.install()` directly — the exact function `LimaProvider.runtime().run()` wraps — against the real `~/.local/share/omelet` on this machine, rather than through `omelet setup --headless`, so the run could not go on to touch `create_vm` and disturb the Lima VM already on this machine (see the Notes section). Completed in 3.51s: downloaded and checksum-verified `lima-2.2.0-Darwin-arm64.tar.gz`, extracted it, ran the staged binary before swapping it into place, and left `~/.local/share/omelet/lima/bin/limactl --version` printing `limactl version 2.2.0`. This machine already had Lima 2.2.0 on its Homebrew PATH; the managed copy was fetched and verified independently of it, which is the point — `find_limactl` never has to fall back to a user's Homebrew Lima once setup has run once. |
| 4 (superseded 2026-09-15) | Setup on a Mac without Lima | The dead end reads as an instruction | Setup stops at preflight saying `install Lima (brew install lima)`, with no stack trace | 2026-09-15, source checkout | source checkout | **SUPERSEDED by case 4 above, same day.** This was the right behavior before this branch: `omelet setup --headless` printed exactly that and exited 1, where before this branch it raised `AttributeError: 'LimaProvider' object has no attribute 'image'` before its first step. Kept for the record rather than deleted — the branch changed what "setup on a Mac without Lima" is supposed to do, not just how it's tested. |
| 4b | Setup with Lima installed, under a Finder-like environment | The Homebrew lookup, which is what case 3 tripped over | `omelet doctor` passes with `env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin` | **PASS** | 2026-09-15, frozen 0.1.0 | Checked against the binary inside the built `Omelet.app`, not just from source: `✓ limactl installed`, exit 0. Lima 2.2.0 at `/opt/homebrew/bin/limactl`. |
| 5 | Setup on a Mac with Lima installed | The whole install engine on macOS | Every step completes and `verify` returns a real HTTP 200; **record the wall-clock time** | UNRUN | UNRUN | UNRUN |
| 6 | Re-run setup on a provisioned Mac | Idempotency | `preflight`/`remediate`/`reboot_gate` report skipped, the rest re-run, exit 0 | UNRUN | UNRUN | UNRUN |
| 7 | `packaging/macos/uninstall.sh` | Cleanup | `limactl list` no longer shows `omelet-vm`; the app, the `/usr/local/bin/omelet` symlink and the pkg receipt are all gone; `~/.local/share/omelet` (cache, vm, **and the managed `lima/` install_runtime put there, ~100 MB**) no longer exists | UNRUN | UNRUN | UNRUN |
| 8 | Install the .pkg over an existing install | Upgrade | The new build replaces the old one in place; the existing VM is left alone and `omelet setup` finds it | UNRUN | UNRUN | UNRUN |
| 9 | Setup with no network at `install_runtime` | The download step fails in plain language, and resumes rather than restarting | The step fails with the sentence from `_ACTIONS["install_runtime"]`, no stack trace, and a re-run with the network back resumes the partial download rather than restarting it | UNRUN | UNRUN | UNRUN |
| 10 | Open Omelet.app on a provisioned Mac | The status screen, not the wizard, is what a set-up user sees | The status screen appears within a few seconds without running an install; the SSH command and the four fields are populated from `~/.lima/omelet-vm/ssh.config`; Copy puts them on the clipboard; `ssh -F … lima-omelet-vm` from Terminal gets a shell | UNRUN | UNRUN | UNRUN |
| 11 | The window in dark mode and in light mode | `theme.py`'s luminance-based palette, not an OS check | Text is legible in both, with no white-on-white card and no black-on-black label, switched live via System Settings with the app reopened | UNRUN | UNRUN | UNRUN |
| 12 | Setup on an Intel Mac (a build made there, per the native-arch note above) | Whether `rosetta.enabled: true` next to the `x86_64` image in `omelet.yaml` is coherent at all | `install_runtime` fetches the `x86_64` Lima archive and `create_vm` boots the `x86_64` image under `vz`; Rosetta itself is arm64-only and does nothing here, so its `enabled: true` should have no observable effect either way — a run that behaves identically with it removed would confirm that; a run that fails while `limactl` mentions Rosetta would not | UNRUN | UNRUN | UNRUN — nobody has run an Intel build; this is a doc-only flag pending that machine, not a code change (see the comment above `rosetta:` in `omelet.yaml`) |

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
  run it where that is disposable, and see the bullet below before running it
  on this machine specifically.
- **The `codesign --deep` hazard for a bundled `limactl` no longer applies.**
  `build.sh`'s signing comment still describes it — re-signing every Mach-O in
  the bundle would strip `com.apple.security.virtualization` from a `limactl`
  shipped inside `Omelet.app`, breaking `vz` on signed builds only, on the
  user's machine — but Lima is now fetched by `install_runtime` at setup time,
  not bundled, so there is no third-party Mach-O under `Contents/MacOS` for
  `--deep` to touch. The paragraph stays in `build.sh` because it is the reason
  bundling was rejected in favor of fetching; deleting it would let a future
  reader re-propose bundling without knowing why that failed before.
- **This machine has a Lima VM named `omelet-vm`, and it is real evidence, not
  disposable leftover state — do not delete it.** `Running`, `vz`, `aarch64`,
  its `lima.yaml` byte-identical to a real revision of
  `host/providers/omelet.yaml`, engine installed to `engine-v0.0.1`, and
  `/opt/omelet/projects` populated. `~/.local/share/omelet/install-state.json`
  on this machine shows `{"completed": ["preflight"]}` — an earlier draft of
  this bullet read that as evidence the VM bypassed `omelet setup`'s tracked
  steps. That reading was backwards: `install-state.json` never records an
  `always_run` step, and every step after `preflight` is `always_run`, so
  `{"completed": ["preflight"]}` is **consistent with** a successful setup
  run — but it is consistent with a run that died at `create_vm`,
  `bootstrap`, `connect` or `verify` too, since none of those get persisted
  here either. This file alone cannot tell the two apart. Full details, the
  command trail, and the better evidence that does distinguish them are in
  `docs/lima-verification-report.md`. Case 4 above still calls the
  installer function directly rather than running `omelet setup --headless`
  end to end, so as not to run `create_vm` a second time against a VM of the
  same name — that reasoning holds regardless of how this VM is read. **Case 7
  in this table deletes a VM named `omelet-vm` by design; do not run it on
  this machine.**
