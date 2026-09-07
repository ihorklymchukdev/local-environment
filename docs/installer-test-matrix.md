# Installer manual test matrix

This is the release gate for the Windows installer. None of these cases run in
CI — each row must be exercised by hand on real (or virtualized) Windows
machines before a build ships. Record the date, the build tested
(`OmeletSetup-<version>.exe`), and the verbatim output/observations for
every run. Do not mark a case passed without recording evidence for it.

| # | Machine state | What it proves | Pass condition | Date | Build tested | Outcome |
|---|---|---|---|---|---|---|
| 1 | Windows with WSL2 already installed | The upgrade path | Setup completes, verify step returns 200 | UNRUN | UNRUN | UNRUN |
| 2 | **Clean Windows VM, WSL2 never enabled** | The real first-run path *including the reboot* — this is the release gate | UAC prompt appears once; after restart, setup resumes unattended and completes | UNRUN | UNRUN | UNRUN |
| 3 | Windows VM with virtualization disabled in firmware | The dead-end message | Setup stops at preflight with the BIOS instruction and no stack trace | UNRUN | UNRUN | UNRUN |
| 4 | Re-run setup on an already-provisioned machine | Idempotency | All steps report skipped; exits 0 quickly | UNRUN | UNRUN | UNRUN |
| 5 | Uninstall (`omelet uninstall --purge`, invoked by the Inno `[UninstallRun]` entry) | Cleanup | `wsl -l -v` no longer lists `omelet-vm`; cache directory gone | UNRUN | UNRUN | UNRUN |
| 6 | Setup window (`host/setup_app/app.py`) observed during cases 1-5 | The tkinter progress window itself — it has no automated coverage of any kind and cannot even be imported on this dev machine (no tkinter), so this row is its only verification | Window appears, shows per-step progress, and can be closed on every outcome (success, dead end, and failure) | **PARTIAL** | 2026-08-19, Windows 11 26200, frozen `setup.exe` | Failure path confirmed on a real machine: window opened, rendered all 8 steps, marked ✓/✗ per step, and showed both the raw guest error and the suggested action. Still unverified: the SUCCESS path, the dead-end path, and closing the window mid-install (which must report a non-zero exit). |
| 7 | `dist\Omelet\omelet.exe selfcheck` run directly against the frozen build (any machine from cases 1-5) | That the bundled assets (`bootstrap.sh`, `traefik.yml`, the nginx-hello template, `omelet.yaml`) actually resolve inside the frozen exe, not just in the source tree | Prints `OK` for all four assets and exits 0 | **PASS** | 2026-08-19, Windows 11 26200, Python 3.14.0, PyInstaller 6.22.2 | Caught a real defect on the first run: the template resolved to `_internal\templates\` because `cli.py` is the frozen entry script and its `__file__` points at the bundle root, not `_internal\runtime\`. Fixed by resolving `VERIFY_TEMPLATE` from `host/core/install.py` (an imported module). Re-run: all four `OK`. |
| 8 | PATH before vs. after uninstall (case 5's machine) | Uninstall does not corrupt other applications' PATH entries — it only ever appends, and deliberately leaves its own stale segment behind rather than editing the value | Every PATH entry present before uninstall other than `{app}` is still present, unmodified, after uninstall | UNRUN | UNRUN | UNRUN |

## Notes for the operator

- **Case 2** requires nested virtualization under Hyper-V (WSL2 itself
  virtualizes). If nested virtualization is unavailable in the test
  environment, record that fact explicitly in the Outcome column for case 2
  rather than marking it passed or skipping the row.
- **Case 5** exercises `omelet uninstall --purge`, which is destructive: it
  destroys the VM and every project inside it. Only run it against a machine
  whose VM state is disposable. The uninstaller now shows a confirmation
  dialog naming that consequence before it runs; declining it must abort the
  uninstall entirely (files and registry entries left in place).
- **Case 6** has no fixed machine state of its own — observe the setup window
  while running cases 1, 2, 3, and 5 (any path that launches
  `setup.exe setup`) and record what was seen for each: does the window
  appear, does progress update per step, does the success panel name the
  install location and `omelet up <folder>`, does closing it behave correctly
  whether setup succeeded, hit a dead end, or failed. Also confirm no black
  console windows flash while the guest commands run.
- **Case 7** is also run automatically inside `build.ps1` as part of the
  build's own smoke test; this row is for confirming it still reports OK
  against the actual installed copy on a target machine, not just at build
  time on the build machine.
- **Case 8** should be checked with
  `reg query HKCU\Environment /v Path` captured right before and right after
  case 5's uninstall. Expect an unchanged value except that the `{app}`
  segment remains (this is the accepted, deliberate limitation — see the
  `[Registry]` comment in `installer.iss`), not any other entry disturbed.
- Cases 1, 4, 5, 7, and 8 can be run on the development machine. Cases 2 and 3
  require a VM.
