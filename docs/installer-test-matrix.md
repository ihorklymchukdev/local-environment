# Installer manual test matrix

This is the release gate for the Windows installer. None of these cases run in
CI — each row must be exercised by hand on real (or virtualized) Windows
machines before a build ships. Record the date, the build tested
(`LocalRuntimeSetup-<version>.exe`), and the verbatim output/observations for
every run. Do not mark a case passed without recording evidence for it.

| # | Machine state | What it proves | Pass condition | Date | Build tested | Outcome |
|---|---|---|---|---|---|---|
| 1 | Windows with WSL2 already installed | The upgrade path | Setup completes, verify step returns 200 | UNRUN | UNRUN | UNRUN |
| 2 | **Clean Windows VM, WSL2 never enabled** | The real first-run path *including the reboot* — this is the release gate | UAC prompt appears once; after restart, setup resumes unattended and completes | UNRUN | UNRUN | UNRUN |
| 3 | Windows VM with virtualization disabled in firmware | The dead-end message | Setup stops at preflight with the BIOS instruction and no stack trace | UNRUN | UNRUN | UNRUN |
| 4 | Re-run setup on an already-provisioned machine | Idempotency | All steps report skipped; exits 0 quickly | UNRUN | UNRUN | UNRUN |
| 5 | Uninstall (`runtime uninstall --purge`, invoked by the Inno `[UninstallRun]` entry) | Cleanup | `wsl -l -v` no longer lists `runtime-vm`; cache directory gone | UNRUN | UNRUN | UNRUN |
| 6 | Setup window (`runtime/setup_app/app.py`) observed during cases 1-5 | The tkinter progress window itself — it has no automated coverage of any kind and cannot even be imported on this dev machine (no tkinter), so this row is its only verification | Window appears, shows per-step progress, and can be closed on every outcome (success, dead end, and failure) | UNRUN | UNRUN | UNRUN |

## Notes for the operator

- **Case 2** requires nested virtualization under Hyper-V (WSL2 itself
  virtualizes). If nested virtualization is unavailable in the test
  environment, record that fact explicitly in the Outcome column for case 2
  rather than marking it passed or skipping the row.
- **Case 5** exercises `runtime uninstall --purge`, which is destructive: it
  destroys the VM and every project inside it. Only run it against a machine
  whose VM state is disposable.
- **Case 6** has no fixed machine state of its own — observe the setup window
  while running cases 1, 2, 3, and 5 (any path that launches
  `runtime.exe setup`) and record what was seen for each: does the window
  appear, does progress update per step, does closing it behave correctly
  whether setup succeeded, hit a dead end, or failed.
- Cases 1, 4, and 5 can be run on the development machine. Cases 2 and 3
  require a VM.
