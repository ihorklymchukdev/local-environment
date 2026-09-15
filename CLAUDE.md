# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A PoC CLI (`omelet`) that creates a managed Linux VM, installs Docker inside it, runs any
`docker-compose` project in the guest, and hands back a working URL on the host.
Windows/WSL2 is the primary platform; macOS/Lima exists for parity and is **unverified below the
installer** (`host/providers/lima.py`, `host/providers/omelet.yaml` — both carry an UNVERIFIED
banner; no Lima VM has ever been created). Both platforms have a packaged installer, and on macOS
`omelet setup` is known to run as far as its first check — `docs/lima-verification-report.md`
records exactly what has and has not run there.

`task.md` and `docs/superpowers/plans/2026-08-14-local-runtime-poc.md` hold the original blueprint
and task plan; `.superpowers/sdd/` holds the per-task execution ledger.

## Architecture shape: the host is a VM shell, the engine is everything inside

Two halves, shipped and versioned independently:

- **Host** (`host/`, a frozen desktop binary) — creates and runs the VM, runs one bootstrap
  command in it (fetch `OMELET_ENGINE_URL` → `bash`), reads the token, forwards ports, and talks
  to the agent over HTTP. It holds no guest files and no knowledge of what the engine installs.
- **Engine** (`engine/` + `agent/`) — everything inside the VM: Docker, the Traefik+agent stack,
  the in-VM `omelet` CLI, agent instructions and skills (via `npx skills add`). Released as
  `engine-v*` tags with a matching `omelet-agent` image. The same `get.sh` provisions a cloud VM.

The seam between them is a fixed contract — token path, agent port + `/health` `api` number, edge
port, `/opt/omelet/engine.version` — and nothing else. A change inside the VM must never need a
host release; if it does, the logic is on the wrong side.

### Releasing the engine (manual until CI exists)

Before the first shipped host can install anything:

- The repository is public.
- `engine/get.sh` exists on `main` — hosts fetch `ENGINE_URL` from `main`, not from a tag.
- At least one `engine-vX.Y.Z` tag exists.
- The ghcr image named by that tag's `engine/stack.yml` is published and public.
- `agent/__init__.py`, the Dockerfile's `AGENT_VERSION` and `engine/stack.yml` are bumped together
  before the first tag — the agent gained `/health`'s `api` field after 0.1.0.

`engine/get.sh` on `main` is a live contract for every shipped host: keep its env vars
(`OMELET_ENGINE_REPO`, `OMELET_ENGINE_REF`, `OMELET_ENGINE_REPAIR`), marker path and exit
semantics backward compatible.

1. Bump `agent/__init__.py`'s `__version__`, the Dockerfile's `AGENT_VERSION` and
   `engine/stack.yml`'s image tag together (`tests/test_constants_agree.py` holds them equal).
2. `docker build -t ghcr.io/ihorklymchukdev/omelet-agent:X.Y.Z agent/ && docker push ghcr.io/ihorklymchukdev/omelet-agent:X.Y.Z`
3. `git tag engine-vX.Y.Z && git push origin engine-vX.Y.Z`

Bump `agent/core/constants.API_VERSION` (and the host's `SUPPORTED_API`) only when a route the host
calls changes incompatibly — that one needs a host release.

## Commands

```bash
pip install -e ".[dev]"

python3 -m pytest -q                                    # full suite (444 tests, ~8s)
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
host CLI (typer)  →  AgentClient (urllib)  →  127.0.0.1:39099 → agent (FastAPI in the VM)
                  →  VmProvider.exec()     →  guest: the engine bootstrap, the token read
                                              /opt/omelet/projects/<id>/
host localhost:39080 ─────────────────────────→  traefik :39080 → routes by Host header
```

### Hard invariant: `host/` never imports `agent/`

The host ships as a PyInstaller-frozen binary and reaches the agent over HTTP; the agent ships as a
Docker image built from `agent/` alone. `tests/host/test_no_agent_import.py` and
`tests/agent/test_no_host_import.py` enforce both directions by AST, anchored to `__file__`. The
host's only runtime dependency is `typer` — it parses no YAML, and
`tests/host/test_host_dependencies.py` fails on a declared or imported one. Names both packages
need are declared twice and held equal by `tests/test_constants_agree.py`.

### Hard invariant: no platform branching outside `host/providers/`

`tests/test_no_platform_leak.py` greps every `host/**/*.py` and `agent/**/*.py` outside
`providers/` for `sys.platform`, `platform.system()`, `os.name` and fails on any hit. Like the
two import-boundary tests it resolves the tree from `__file__` and asserts it scanned something
— a cwd-relative `Path("host")` passes vacuously from any other directory, which has now bitten
this repo three times. Reach for repo files that way in every test.
`host/providers/__init__.py` is the single place the host platform is resolved
(`get_provider()`, `default_install_dir()`).
Do not add an `if windows` anywhere else — push the difference into a provider method.

### Layers

- `host/core/provider.py` — the `VmProvider` Protocol plus `Completed` / `CheckResult` /
  `Diagnosis` value types. Providers are **duck-typed against the Protocol, not subclasses**.
- `host/providers/` — `Wsl2Provider` (shells `wsl.exe`), `LimaProvider` (shells `limactl`).
  Both take an injectable `runner` callable (defaults to `subprocess.run(..., capture_output=True)`),
  which is what makes them unit-testable.
- `host/client.py` — the only way the host reaches project logic: `AgentClient` over stdlib
  `urllib.request` (the host is PyInstaller-frozen, so it may never gain an HTTP dependency).
  It reads `/opt/omelet/agent.token` through `provider.exec()`, turns every non-2xx body into
  `AgentError(code, message, status)`, a refused connection into `AgentUnavailableError`, and a
  failed job into `JobFailedError` carrying the guest's own stderr.
- `agent/core/` — all platform-free logic: compose parsing, web detection, Traefik overlay
  generation, project identity, failure classification, guest lifecycle, sqlite state.
- `host/core/bootstrap.py` — the host's whole share of provisioning: unless
  `/opt/omelet/engine.version` exists (or `repair=True`), it runs a base64 stub as one `bash -lc`
  argument that downloads `OMELET_ENGINE_URL` in full and runs it, forwarding `OMELET_ENGINE_REF`
  when set and `OMELET_ENGINE_REPAIR=1` on repair. Values are checked against a shell-safe pattern
  because the argument is re-parsed by wsl.exe/ssh. `host/provision/` holds only the installer's
  `nginx-hello` smoke-test project (`tests/host/test_no_guest_assets.py`).
- `engine/get.sh` — the entrypoint: `resolve_ref` (explicit `OMELET_ENGINE_REF` → installed ref on
  repair → highest `engine-v*` tag by `sort -V`), downloads that ref's tarball, replaces
  `/opt/omelet/engine/` with its `engine/`, runs `install.sh <ref> [--repair]`.
- `engine/install.sh` — Docker, `edge`, `/opt/omelet` permissions, token, the stack (recreating the
  agent on a new token or repair), Node ≥ 22.20 from NodeSource, `/usr/local/bin/omelet`,
  `/etc/claude-code/CLAUDE.md`, then per account (root + `lib/login-users.sh`) the Codex block and
  `~/projects` link (`lib/install-agents.sh`) and
  `npx -y skills@1.5.26 add /opt/omelet/engine/skills -s '*' -g -a claude-code codex -y </dev/null`.
  Writes `engine.version` last.
- `engine/cli/omelet.py` — the `omelet` command **inside** the VM, used by coding agents:
  `up`/`new`/`clone`/`status`/`logs`/`down` over the agent API with the guest token. One
  stdlib-only file, loaded by tests by path (`tests/engine/cli/loader.py`); it shares constants
  with both sides, held equal by `tests/test_constants_agree.py`. `engine/instructions/` and
  `engine/skills/` hold what those agents read. Nothing is written into user repositories.
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

- **Project files travel over HTTP, not the command line.** `AgentClient.upload_directory` tars the
  local directory into a temp file and POSTs it as a raw `application/gzip` body, skipping
  `EXCLUDED_DIRS` (`.git`, `node_modules`, `.venv`, `__pycache__`, at any depth) and the generated
  `.omelet/overlay.yml` — but never `.omelet/project.yml`, which is the user's own configuration. The old
  `lifecycle.push_project` (base64 through `bash -lc`, and its ~24 KB command-line ceiling) is gone.
- **`omelet port add/remove/list` is the only caller of `forward()`.** Without it the
  distinct-port machinery would be dead code the Protocol still advertises. Ports the VM publishes
  itself (the edge port) need no entry here.
- **The host CLI holds no project logic.** Compose parsing, web detection, URLs and project state
  are all agent-side; `host/cli.py` creates the project, uploads it, starts a job, polls, and prints
  what comes back. Its error messages are the agent's own sentences — never a status code.
- **The user's `docker-compose.yml` is never modified.** A generated `.omelet/overlay.yml` adds the
  Traefik labels and the external `edge` network, and compose is invoked with both `-f` files.
  `compose ps` is invoked with only the base file.
- **`wsl.exe` output encoding is split**: meta commands (`-l`, `--version`, `--import`) emit UTF-16LE,
  command passthrough emits UTF-8. `decode_wsl()` sniffs NUL bytes to pick. Use `_meta()` for meta
  commands and `exec()` for passthrough — mixing them corrupts output.
- **Existing VMs update only when the engine is installed again.** Setup skips an installed engine;
  the connect step's token repair and a fresh VM are the only reinstall paths today (self-update is
  deferred — `docs/future/engine-self-update.md`). Accounts created after install get no skills
  until then.
- **`npx` inside `install.sh`'s account loop must read `</dev/null`**: the loop reads accounts from
  stdin, and anything else reading it eats the remaining accounts.
- **Nothing under `agent/` or `engine/` is bundled into the frozen host binary**, and
  `tests/host/test_frozen_bundle.py` fails if a `datas` entry reappears — for *every* spec under
  `packaging/`, not just the platform you are on. The VM pulls the image and fetches the engine
  itself; only the `nginx-hello` smoke test and `omelet.yaml` ship with the host.
- **The install step list is built from the provider, not from the platform.** Beyond the
  `VmProvider` Protocol, `default_steps` reads seven members off whichever provider it was handed:
  `image()`, `register_resume()`, `location`, `terminal`, `remediable`, `runtime()` and `access()`.
  Three of them **remove steps**: `image()` returning None means the VM platform fetches its own
  guest image (Lima does, from `omelet.yaml`) and `fetch_image` disappears; `remediable = False`
  means the host OS has nothing to turn on and `remediate`/`reboot_gate` disappear with it;
  `runtime()` returning None means the VM platform ships with the host OS and `install_runtime`
  disappears — a value names the step and installs what the platform needs (Lima, on macOS). A
  step that would be shown and skipped is a step describing the other platform — the mac setup
  window listed "Turning on Windows features". `access()` is how the status screen shows a user
  the way into the VM without knowing what SSH is. `tests/host/test_provider_surface.py::test_
  every_provider_answers_what_the_install_list_asks_of_it` holds both providers to the surface;
  LimaProvider was missing two of these, so `omelet setup` on macOS died with an `AttributeError`
  before its first step.
- **A Mac app gets no shell PATH.** LaunchServices starts one with
  `/usr/bin:/bin:/usr/sbin:/sbin`, so Homebrew's prefix is absent and `shutil.which("limactl")`
  answers no inside `Omelet.app` on a machine where `brew install lima` just succeeded. Setup now
  installs its own pinned Lima into `~/.local/share/omelet/lima` (`host/providers/lima_install.py`),
  and `find_limactl()` prefers that managed copy over anything on the PATH or in a Homebrew prefix
  — a user's own Lima is never touched, and every assumption the provider makes about Lima's
  on-disk layout is an assumption about the version setup put there. The Homebrew-prefix fallback
  stays for a source checkout that has never run setup. The PATH finding still holds for anything
  else the host ever shells out to by name on macOS; `ssh` is safe only because it lives in
  `/usr/bin`.
- **The two mac executables must not differ only in case.** `Omelet` and `omelet` are one file on a
  default macOS filesystem: COLLECT wrote both into `Contents/MacOS`, the second replaced the first,
  and the app launched the CLI windowlessly. The GUI binary is `omelet-setup` for that reason, and
  `build.sh` counts the binaries rather than trusting the build. `BUNDLE` also infers
  `CFBundleExecutable` (from COLLECT's sorted table) and `LSBackgroundOnly` (from the console flag)
  wrongly here — both are set explicitly in `info_plist` and asserted after the build.
- **The host and the agent each own a `constants.py`**, because nothing under `host/` may import
  `agent/`. `tests/test_constants_agree.py` holds every name declared in both modules equal — add
  a shared constant to one and it must go into the other with the same value.
- **The agent container runs as a non-root user** whose only shared credential with the VM is the
  `docker` group (`stack.yml`'s `group_add`). `engine/install.sh` therefore `chgrp`s `/opt/omelet` to
  `docker` and sets setgid on its directories *before* `compose up`; skip that and the agent
  cannot open `/opt/omelet/state.db` and `restart: always` crash-loops it.
- **The agent holds no project paths of its own.** `agent/core/lifecycle.py` builds every compose
  `-f` path from the directory the API hands it (`Path(config.projects_root) / project_id`), never
  from `constants.GUEST_PROJECTS` — the two used to disagree, so `OMELET_PROJECTS_ROOT` uploaded
  into one directory and ran compose against another. `compose_up` returns `(status, detail)`;
  URLs are built in `app.py`, the only place holding the configured edge port.
- **Guest failures must stay loud.** `provider.exec()` returns a `Completed` and never raises, so
  every caller has to check `.ok` itself. `bootstrap.py` routes its calls through `_run()`, which
  raises `BootstrapError` carrying the guest's stderr, and re-checks `engine.version` afterwards to catch a
  script that exited 0 without finishing. Dropping an `exec` result turns a multi-minute provisioning
  failure into a silent `VM ready.` — that bug already happened once.
- **`forward(guest, host)` is a no-op when the ports are equal**, on both platforms: WSL2
  localhostForwarding and Lima's `portForwards` already cover the edge port, and a proxy on top
  would add a hop and, on Windows, a UAC prompt. Distinct ports are real forwards — WSL2 writes a
  `netsh interface portproxy` rule between two loopback ports through the installer's existing
  elevator (never a second UAC pathway), Lima asks its ssh control master for a tunnel. Both
  delete-then-add, so a repeat is idempotent without parsing a localized error. `forwards()` is
  netsh's registry table on Windows and always empty on Lima, where the tunnels die with the VM —
  the asymmetry is the mechanism, not a gap.
- **URLs** are `http://<project-id>.127-0-0-1.sslip.io:39080`. With multiple web services, the first
  keeps the bare project host and the rest get a `<service>.` subdomain prefix — see
  `project.load_project` / `overlay.host_for`.
- **`classify()` tolerates both JSON-array and NDJSON `docker compose ps --format json` output** —
  the format differs across compose versions.
- **`ProjectLocks` covers every write to a project**, lifecycle *and* files: an upload landing
  between the overlay being written and compose reading `docker-compose.yml` starts a project from
  two versions of itself. A held project answers 409 `project_busy`; the host client retries that
  itself (`_while_busy`), rewinding the archive per attempt. Reads are never locked.
- **`install.verify_step` is the installer's smoke test and a real HTTP 200**, not "the job
  succeeded": it drives `host/provision/nginx-hello` through `AgentClient` under the reserved id
  `omelet-selftest` (never derived from the template's folder name, or a re-run could tear down a
  user project), polls the URL for `READY_TIMEOUT` seconds because Traefik publishes a router a beat
  after the container starts, and deletes the project in a `finally`. `connect_step` runs just before it: an agent whose `/health` `api` is not in
  `constants.SUPPORTED_API` is reported in one sentence and never repaired, and an agent answering
  `agent_unconfigured` or `unauthorized` gets one `bootstrap(repair=True)` — `/health` is exempt from
  the token check, so `restart: always` never restarts a container refusing every other route, and
  the agent reads its token **once, at startup**, which is why repair recreates the container — then
  the host re-reads the token and dials again.
- **The setup window is two screens, and the app opens on the status one.** `host/setup_app/app.py`
  routes on `host/core/status.py::probe` — VM exists, guest reachable, `engine.version` present,
  agent API supported — and starts the wizard by itself only when nothing is provisioned. `theme.py`
  picks light or dark from the luminance of the ttk background rather than by asking which OS this
  is, which is what keeps the no-platform-branching invariant true in the UI layer. Fonts are
  tkinter's named system fonts; a hardcoded family name is how every label came to ask macOS for
  "Segoe UI".
- CLI command bodies use **function-local imports** deliberately (keeps `omelet --help` and the
  smoke test fast, and avoids importing provider code on unsupported hosts). `cli._provider_factory`
  is a module attribute so tests can monkeypatch the provider.

## Testing conventions

- No test spawns `wsl.exe`/`limactl`, touches a real VM, or reaches the network. Provider tests
  inject a `FakeRunner` that records `argv` and returns scripted bytes; CLI tests monkeypatch
  `cli._provider_factory` with a `FakeProvider`. Assertions are about **constructed argv and decoded
  output**, not side effects. Engine shell scripts are the exception that still runs a real process:
  they are exercised with `bash` against fakes on `PATH` (see the engine-scripts bullet below).
- `tests/agent/test_acceptance_detection.py` runs the five real-world compose shapes in
  `tests/fixtures/compose/` through `detect_web` — add a fixture there when changing detection rules.
- Engine scripts are tested under `tests/engine/`: `bash -n` plus text assertions over
  `install.sh`, `resolve_ref` sourced from `get.sh` with a fake `git` on `PATH`, and
  `install-agents.sh`/`login-users.sh` run against temporary homes. Nothing there touches the
  network; the live-VM acceptance run covers apt, NodeSource, npm and ghcr.

## Conventions

- Python 3.12+, `from __future__ import annotations`, frozen dataclasses for value types.
- Host runtime deps are `typer` alone; the agent's are declared in `agent/pyproject.toml`. Keep
  it that way unless there's a reason.
- Packaging lives in `packaging/<platform>/`: Inno Setup on Windows (`build.ps1`), `pkgbuild`/
  `productbuild` on macOS (`build.sh` → `dist/OmeletSetup-<version>.pkg`). Both freeze with
  PyInstaller one-dir and smoke-test the frozen binary (`version`, then `selfcheck`) *before*
  packaging it. The mac build needs a Python 3.12+ with tkinter and is native-arch only. Manual
  release gates: `docs/installer-test-matrix.md`, `docs/macos-install-test-matrix.md`.
- Live WSL2 run needs an Ubuntu 24.04 rootfs tarball path in `OMELET_ROOTFS` (README has the
  current download URL); the provider factory reads it, and `omelet vm create` without it raises
  `ValueError`. The value must be a Windows path — it goes straight to `wsl.exe --import`.
