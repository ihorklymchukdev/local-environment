# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A PoC CLI (`omelet`) that creates a managed Linux VM, installs Docker inside it, runs any
`docker-compose` project in the guest, and hands back a working URL on the host.
Windows/WSL2 is the primary platform; macOS/Lima exists for parity and is **unverified**
(`host/providers/lima.py`, `host/providers/omelet.yaml` — both carry an UNVERIFIED banner).

`task.md` and `docs/superpowers/plans/2026-08-14-local-runtime-poc.md` hold the original blueprint
and task plan; `.superpowers/sdd/` holds the per-task execution ledger.

## Commands

```bash
pip install -e ".[dev]"

python3 -m pytest -q                                    # full suite (151 tests, ~0.3s)
python3 -m pytest tests/agent/test_project.py -q        # one file
python3 -m pytest -k classify -q                        # one test by name
```

In this WSL sandbox `/tmp/pytest-of-$USER` is root-owned, which breaks `tmp_path` fixtures.
Prefix with `TMPDIR=<writable dir>` if `tmp_path`-based tests error. Sandbox artifact, not a code bug.

There is no linter or formatter configured.

## Architecture

**The VM is abstracted, not Docker.** The guest is plain Ubuntu 24.04 running plain Docker on both
host platforms, so everything above the guest OS is platform-independent. The OS difference collapses
into the two provider classes.

```
host CLI (typer)  →  VmProvider.exec()  →  guest: dockerd + traefik + project containers
                                                   /opt/omelet/projects/<id>/
host localhost:39080 ──────────────────────────→  traefik :39080 → routes by Host header
```

### Hard invariant: no platform branching outside `host/providers/`

`tests/test_no_platform_leak.py` greps every `host/**/*.py` and `agent/**/*.py` outside
`providers/` for `sys.platform`, `platform.system()`, `os.name` and fails on any hit.
`host/providers/__init__.py` is the single place the host platform is resolved
(`get_provider()`, `default_install_dir()`).
Do not add an `if windows` anywhere else — push the difference into a provider method.

### Layers

- `host/core/provider.py` — the `VmProvider` Protocol plus `Completed` / `CheckResult` /
  `Diagnosis` value types. Providers are **duck-typed against the Protocol, not subclasses**.
- `host/providers/` — `Wsl2Provider` (shells `wsl.exe`), `LimaProvider` (shells `limactl`).
  Both take an injectable `runner` callable (defaults to `subprocess.run(..., capture_output=True)`),
  which is what makes them unit-testable.
- `agent/core/` — all platform-free logic: compose parsing, web detection, Traefik overlay
  generation, project identity, failure classification, guest lifecycle, sqlite state.
- `host/provision/` — `bootstrap.sh`, the only host-side asset pushed into the VM alongside
  `agent/deploy/stack.yml`: docker-ce from the official repo, the `edge` network, `/opt/omelet`
  made group-writable, then `docker compose -f /opt/omelet/stack.yml pull && up -d`. The list of
  pushed files is `host/core/bootstrap.guest_assets()`, which `cli.selfcheck` also reads.
- `agent/api/` — the FastAPI app the host talks to. `app.py::create_app(config, runner, state)` is
  a factory on purpose (no module-level `app`, so importing it opens no sqlite file); `jobs.py` is
  the in-process job registry that keeps slow compose work off the request; `__main__.py` is the
  uvicorn entrypoint on `0.0.0.0:39099`. Every non-2xx body is
  `{"error": {"code": ..., "message": ...}}`, produced by one exception handler.
- `agent/core/exec.py` — `LocalRunner`, the in-VM twin of `VmProvider.exec`: same `Completed`
  contract, never raises. `agent/core/config.py` — `AgentConfig`, the only place the domain and
  edge port may come from.
- `agent/core/files.py` — project file transfer over HTTP (`POST/GET /projects/{id}/files`,
  `PUT/GET/DELETE /projects/{id}/files/{path}`), replacing the 32,767-character `wsl.exe`
  command-line ceiling with a streamed request body. `extract_archive` merges an uploaded
  tar.gz into the project directory rather than replacing it, and rejects any entry (absolute
  path, `..` escape, symlink/hardlink escaping the tree) via `tarfile`'s `filter="data"` plus an
  explicit absolute-path check, since that filter silently normalizes an absolute name instead
  of refusing it.

### Things that will bite you

- **Nothing is staged on the host.** `push_project` tars the local dir in memory, base64-encodes it,
  and pipes it through `bash -lc … base64 -d | tar -xzf -` in the guest. base64 is deliberate: it
  avoids quoting/newline mangling through `wsl -- bash -lc`. `bootstrap._push_file` does the same.
- **The user's `docker-compose.yml` is never modified.** A generated `.omelet/overlay.yml` adds the
  Traefik labels and the external `edge` network, and compose is invoked with both `-f` files.
  `compose ps` is invoked with only the base file.
- **`wsl.exe` output encoding is split**: meta commands (`-l`, `--version`, `--import`) emit UTF-16LE,
  command passthrough emits UTF-8. `decode_wsl()` sniffs NUL bytes to pick. Use `_meta()` for meta
  commands and `exec()` for passthrough — mixing them corrupts output.
- **Bootstrap idempotency is a version marker**, `/opt/omelet/.bootstrapped` compared against
  `host.core.constants.BOOTSTRAP_VERSION`. **Bump `BOOTSTRAP_VERSION` whenever
  `host/provision/bootstrap.sh` changes**, or existing VMs silently skip the new bootstrap.
- **The host and the agent each own a `constants.py`**, because nothing under `host/` may import
  `agent/`. `tests/test_constants_agree.py` holds every name declared in both modules equal — add
  a shared constant to one and it must go into the other with the same value.
- **The agent container runs as a non-root user** whose only shared credential with the VM is the
  `docker` group (`stack.yml`'s `group_add`). `bootstrap.sh` therefore `chgrp`s `/opt/omelet` to
  `docker` and sets setgid on its directories *before* `compose up`; skip that and the agent
  cannot open `/opt/omelet/state.db` and `restart: always` crash-loops it.
- **Guest failures must stay loud.** `provider.exec()` returns a `Completed` and never raises, so
  every caller has to check `.ok` itself. `bootstrap.py` routes its calls through `_run()`, which
  raises `BootstrapError` carrying the guest's stderr, and re-reads the marker afterwards to catch a
  script that exited 0 without finishing. Dropping an `exec` result turns a multi-minute provisioning
  failure into a silent `VM ready.` — that bug already happened once.
- **`forward(guest, host)` intentionally raises `NotImplementedError` when the ports differ.** The
  edge port is equal on both sides by design (WSL2 localhostForwarding / Lima `portForwards`), and
  dynamic distinct-port forwarding is out of the PoC slice. Don't "fix" it without a decision.
- **URLs** are `http://<project-id>.127-0-0-1.sslip.io:39080`. With multiple web services, the first
  keeps the bare project host and the rest get a `<service>.` subdomain prefix — see
  `project.load_project` / `overlay.host_for`.
- **`classify()` tolerates both JSON-array and NDJSON `docker compose ps --format json` output** —
  the format differs across compose versions.
- CLI command bodies use **function-local imports** deliberately (keeps `omelet --help` and the
  smoke test fast, and avoids importing provider code on unsupported hosts). `cli._provider_factory`
  is a module attribute so tests can monkeypatch the provider.

## Testing conventions

- No test ever spawns a real subprocess or touches a real VM. Provider tests inject a `FakeRunner`
  that records `argv` and returns scripted bytes; CLI tests monkeypatch `cli._provider_factory` with
  a `FakeProvider`. Assertions are about **constructed argv and decoded output**, not side effects.
- `tests/agent/test_acceptance_detection.py` runs the five real-world compose shapes in
  `tests/fixtures/compose/` through `detect_web` — add a fixture there when changing detection rules.
- `tests/host/test_bootstrap_shell.py` shells `bash -n` over `bootstrap.sh` and asserts on its text
  (official Docker repo, marker path). It's the only check on the guest script.

## Conventions

- Python 3.12+, `from __future__ import annotations`, frozen dataclasses for value types.
- Runtime deps are only `typer` and `pyyaml` — keep it that way unless there's a reason.
- Live WSL2 run needs an Ubuntu 24.04 rootfs tarball path in `OMELET_ROOTFS` (README has the
  current download URL); the provider factory reads it, and `omelet vm create` without it raises
  `ValueError`. The value must be a Windows path — it goes straight to `wsl.exe --import`.
