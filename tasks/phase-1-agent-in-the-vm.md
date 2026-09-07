# Phase 1: Agent in the VM

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** All project logic moves off the host and into a containerised agent running inside
the VM. The host CLI stops importing `core` and talks to the agent over HTTP. When this phase
lands, a project of any size can be pushed, files can be written without a full re-push, and a
container bound to the wrong address is reported honestly instead of being called healthy.

**Architecture:** `omelet/core/` becomes `agent/core/` essentially unchanged and is wrapped in
an HTTP service. The agent ships as a Docker image, runs inside the VM next to Traefik from a
single compose stack, and holds the Docker socket so it can manage sibling containers. The host
keeps VM lifecycle and the installer, and reaches the agent on a forwarded loopback port.

**Tech stack:** Python 3.12. Host: `typer` + stdlib only. Agent: `fastapi`, `uvicorn`, `pyyaml`
— shipped inside the image, so they never touch the host's frozen binary.

**Context:** `docs/architecture-and-roadmap.md` (Part 2 and Part 5), `task.md` (original
blueprint), `CLAUDE.md` (invariants).

---

## Decisions already settled

Do not reopen these. They are recorded here so no task has to guess.

| Decision | Value |
|---|---|
| Agent delivery | **Always pull from a registry. Never bundle the image in the installer.** Simplicity of delivery wins over offline first-install. |
| Agent image | `ghcr.io/<org>/omelet-agent:<version>` — set `<org>` once in `constants.py`. Pin an exact tag, never `latest`. |
| Agent port | 39099, the port already reserved for the local API. Same on both sides of the boundary. |
| Agent language | Python. `core/` moves unchanged — that is what makes this phase cheap. |
| Agent dependencies | Free to grow. The `typer` + `pyyaml` limit is a **host** constraint, because the host is frozen by PyInstaller. The agent ships as an image and has its own list. |
| State location | Moves into the VM at `/opt/omelet/state.db`. The existing host-side `state.db` is **not** migrated — the project list is rebuildable from `/opt/omelet/projects` plus `docker ps`. |
| Repo layout | One repo, two top-level packages. Split into two repos no earlier than Phase 5. |

---

## Global constraints

Every task's requirements implicitly include this section.

- **Python 3.12+.**
- **Host runtime dependencies must not grow.** The host HTTP client uses `urllib.request` from
  the stdlib, the way `omelet/core/install.py::_default_http_get` already does. Do not add
  `httpx` or `requests` to the host.
- **Platform-boundary invariant still holds** and its test must be updated, not weakened: no
  `sys.platform`, `platform.system()` or `os.name` outside the provider package. See
  `tests/test_no_platform_leak.py`.
- **Existing constants are authoritative.** `EDGE_PORT = 39080`, `DEFAULT_DOMAIN =
  "127-0-0-1.sslip.io"`, `GUEST_ROOT = "/opt/omelet"`, `EDGE_NETWORK = "edge"`. Never
  re-declare them.
- **`BOOTSTRAP_VERSION` must be bumped to 4** in this phase, because `bootstrap.sh` changes.
  Forgetting this makes every existing VM silently skip the new provisioning.
- **Absolute `/usr/bin/docker` everywhere in the guest.** A bare `docker` can reach Docker
  Desktop's engine when its WSL integration is on. This bug has already been fixed once.
- **Guest failures must stay loud.** `provider.exec()` returns a `Completed` and never raises.
  Every caller checks `.ok`. A dropped result turns a multi-minute provisioning failure into a
  silent success — that bug has already happened once.
- **No test spawns a real subprocess, container or VM.** Providers take an injected `runner`;
  agent tests use FastAPI's `TestClient` with a fake Docker layer.
- **Running tests:** `python3 -m pytest -q`. In this sandbox prefix with `TMPDIR=<writable dir>`
  or `tmp_path` fixtures error. **Baseline before this plan: 151 passed.**

---

## The one gotcha that will cost a day if missed

The agent manages **sibling** containers through the mounted Docker socket. Compose files are
parsed by the agent but the resulting bind-mount paths are resolved by **dockerd, in the VM**,
not inside the agent container. So `/opt/omelet` must be mounted into the agent **at the same
path it has on the VM filesystem**. Mount it anywhere else and every user project with a
relative volume silently mounts an empty directory.

```
-v /var/run/docker.sock:/var/run/docker.sock
-v /opt/omelet:/opt/omelet          # same path on both sides. Not negotiable.
```

---

## File structure

**Move** (pure `git mv`, history preserved, no content change in Task 1):

| From | To |
|---|---|
| `omelet/core/{compose,detect,overlay,project,lifecycle,state,constants}.py` | `agent/core/` |
| `omelet/api/server.py` | `agent/api/` |
| `omelet/core/{bootstrap,install,download,images,diagnose,provider}.py` | `host/core/` |
| `omelet/providers/` | `host/providers/` |
| `omelet/setup_app/` | `host/setup_app/` |
| `omelet/cli.py` | `host/cli.py` |
| `omelet/guest/` | `host/provision/` |
| `omelet/templates/` | `agent/templates/` |
| `tests/{core,api}` | `tests/agent/` |
| `tests/{providers,guest}` | `tests/host/` |

**Create:**

| File | Responsibility |
|---|---|
| `agent/pyproject.toml` | Agent package and its own dependency list. |
| `agent/Dockerfile` | Builds the agent image. |
| `agent/deploy/stack.yml` | Traefik + agent, parameterised by domain and entry port. |
| `agent/deploy/traefik.yml` | Traefik static config, moved from `omelet/guest/`. |
| `agent/api/app.py` | FastAPI application: routes, job model. |
| `agent/api/jobs.py` | In-process job registry with status and log streaming. |
| `agent/core/files.py` | Project file storage: upload, write, read, list, delete. |
| `agent/core/health.py` | Post-start probe that catches a wrong bind address. |
| `agent/core/migrate.py` | State schema versioning, applied at startup. |
| `host/client.py` | stdlib HTTP client for the agent API. |
| `tests/agent/test_api_routes.py` | Route contract and error shapes. |
| `tests/agent/test_jobs.py` | Job lifecycle and log streaming. |
| `tests/agent/test_files.py` | Upload, overwrite, path traversal rejection. |
| `tests/agent/test_health.py` | The 127.0.0.1 detection. |
| `tests/agent/test_migrate.py` | Schema upgrade and idempotency. |
| `tests/host/test_client.py` | Client argv, error translation, timeouts. |

**Modify:**

| File | Change |
|---|---|
| `host/provision/bootstrap.sh` | Install Docker, create `edge`, pull and start the stack. Drop the inline `docker run traefik`. |
| `host/core/bootstrap.py` | Push the stack files; bump marker to 4; re-read marker after. |
| `host/cli.py` | Every command routes through `host/client.py`. No `core` imports. |
| `pyproject.toml` | Host package only. Drop `pyyaml` once nothing on the host parses YAML. |
| `tests/test_no_platform_leak.py` | Scan `host/` and `agent/` under the new layout. |

---

## Task 1: Split the tree, change nothing else

**Files:** every path in the Move table above.

**Interfaces:** produces the `host/` and `agent/` packages. Consumes nothing.

This is a mechanical commit. Its whole value is that afterwards, every import crossing from
`host/` into `agent/` is a visible item on the rest of this plan's checklist.

- [ ] **Step 1:** `git mv` every path in the Move table. Use `git mv` so history survives.
- [ ] **Step 2:** Fix imports until the suite is green. Do not restructure, rename or improve
      anything while doing it. Cross-package imports are expected at this point and are the
      work list for Tasks 9 and onward.
- [ ] **Step 3:** Update `tests/test_no_platform_leak.py` to scan both new roots, keeping the
      provider package as the only exemption.
- [ ] **Step 4:** `python3 -m pytest -q` reports **151 passed**. Any other number means content
      changed and the commit is no longer a pure move.

---

## Task 2: Give the agent its own package and dependencies

**Files:** create `agent/pyproject.toml`; modify root `pyproject.toml`.

- [ ] **Step 1:** Write `agent/pyproject.toml` declaring `fastapi`, `uvicorn[standard]` and
      `pyyaml`. Python 3.12+.
- [ ] **Step 2:** Leave the root `pyproject.toml` as the host package. Its dependencies stay
      `typer` plus, for now, `pyyaml`; the `pyyaml` removal is Task 9's closing step.
- [ ] **Step 3:** Add a test asserting the host package's declared dependencies do not include
      `fastapi` or `uvicorn`. This invariant is what keeps the frozen installer small, and it
      will be violated by accident otherwise.

---

## Task 3: The agent HTTP API

**Files:** create `agent/api/app.py`, `agent/api/jobs.py`; test `tests/agent/test_api_routes.py`,
`tests/agent/test_jobs.py`. Replaces `agent/api/server.py`.

**Interfaces:**
- Produces: a FastAPI app exposing the routes below.
- Consumes: `agent/core/` as it already exists.

Routes:

| Method | Path | Notes |
|---|---|---|
| `GET` | `/health` | Agent liveness, version, Docker reachability. |
| `GET` | `/version` | Agent version, for the host compatibility check. |
| `POST` | `/projects` | Create; body carries id and optional overrides. |
| `GET` | `/projects` | List, with status and URLs. |
| `GET` | `/projects/{id}` | One project. |
| `DELETE` | `/projects/{id}` | Stop and forget. |
| `POST` | `/projects/{id}/up` | Returns `{job_id}`. |
| `POST` | `/projects/{id}/down` | Returns `{job_id}`. |
| `GET` | `/projects/{id}/logs` | Streaming. |
| `GET` | `/jobs/{job_id}` | Status, exit detail. |
| `GET` | `/jobs/{job_id}/logs` | Streaming job output. |

- [ ] **Step 1:** Write failing tests for the route contract using FastAPI's `TestClient`: a
      missing project returns 404 with a structured body, `up` returns a job id, and an unknown
      job returns 404.
- [ ] **Step 2:** Write failing tests for the job registry: a job moves running → done, a failed
      job keeps the guest's own stderr, and logs can be read while the job is still running.
- [ ] **Step 3:** Implement `jobs.py`, then `app.py`. **A first image build takes minutes, so no
      route may hold an HTTP request open for the duration of a compose operation.** Everything
      slow returns a job id immediately.
- [ ] **Step 4:** Preserve the existing failure classification. `classify()` already tolerates
      both JSON-array and NDJSON `docker compose ps --format json` output because the format
      differs across compose versions. Do not simplify it.

---

## Task 4: File transfer, and the end of the 24 KB ceiling

**Files:** create `agent/core/files.py`; test `tests/agent/test_files.py`.

The current push tars the project, base64-encodes it and passes it as one command-line argument
to `wsl.exe`. Windows caps a command line at 32,767 characters, which caps a project at roughly
24 KB compressed. This task removes that limit by moving the transfer into a request body.

**Interfaces:**
- Produces: `POST /projects/{id}/files` (tar.gz body, unpacked into the project dir),
  `PUT /projects/{id}/files/{path}`, `GET /projects/{id}/files/{path}`,
  `GET /projects/{id}/files` (tree), `DELETE /projects/{id}/files/{path}`.

- [ ] **Step 1:** Write a failing test that a tar entry named `../../etc/passwd` is rejected.
      Path traversal through an uploaded archive is the obvious hole here.
- [ ] **Step 2:** Write a failing test that an upload overwrites tracked files but leaves
      untracked ones alone — a database's data directory inside the project must survive.
- [ ] **Step 3:** Write a failing test that a 5 MB archive round-trips, proving the ceiling is
      gone.
- [ ] **Step 4:** Implement. Stream to disk; never hold a whole archive in memory.
- [ ] **Step 5:** Delete `push_project`'s base64 path from `agent/core/lifecycle.py` once
      nothing calls it.

---

## Task 5: The agent image

**Files:** create `agent/Dockerfile`.

- [ ] **Step 1:** Multi-stage build on `python:3.12-slim`. Install the Docker **CLI** only —
      the daemon is the VM's.
- [ ] **Step 2:** Run as a non-root user that is a member of the `docker` group so the mounted
      socket is usable.
- [ ] **Step 3:** Declare the agent version as a build arg, surfaced by `GET /version`.
- [ ] **Step 4:** Add a `HEALTHCHECK` hitting `/health`.
- [ ] **Step 5:** No project data in the image. Everything durable is a bind mount. A pull must
      never be able to destroy a user's work.

---

## Task 6: The deployable stack

**Files:** create `agent/deploy/stack.yml`; move `agent/deploy/traefik.yml`.

This file is the Phase 5 payoff. It must be the *same* file locally and in the cloud, differing
only by injected environment.

- [ ] **Step 1:** Write `stack.yml` with two services, `traefik` and `agent`, both
      `restart: always`, on the external `edge` network.
- [ ] **Step 2:** Parameterise **the domain and the entry port as environment variables** with
      the current values as defaults: `OMELET_DOMAIN=127-0-0-1.sslip.io`, `OMELET_EDGE_PORT=39080`.
      Nothing anywhere may hardcode either value outside a config object. This single rule is
      what keeps Phase 5 from becoming a rewrite.
- [ ] **Step 3:** Mount `/var/run/docker.sock` and `/opt/omelet` into the agent, `/opt/omelet`
      at the identical path. Re-read the gotcha section above before writing this.
- [ ] **Step 4:** Bind the agent to `0.0.0.0:39099` inside the guest. WSL2's localhostForwarding
      only surfaces guest sockets bound to `0.0.0.0`; binding loopback makes it unreachable from
      the host. Task 8 covers the exposure this creates.
- [ ] **Step 5:** Add a test asserting `stack.yml` contains no literal `39080` or
      `127-0-0-1.sslip.io` outside a default value.

---

## Task 7: Rewrite the bootstrap around the stack

**Files:** modify `host/provision/bootstrap.sh`, `host/core/bootstrap.py`,
`agent/core/constants.py`; test `tests/host/test_bootstrap_shell.py`.

- [ ] **Step 1:** Reduce `bootstrap.sh` to the genuinely one-time OS-level work: install
      docker-ce from the official repo, enable it, create the `edge` network, make
      `/opt/omelet/projects`.
- [ ] **Step 2:** Replace the inline `docker run traefik` with `docker compose -f
      /opt/omelet/stack.yml pull` followed by `up -d`. **Always pull** — that is the delivery
      decision, and it means the first install and every update both need network.
- [ ] **Step 3:** Keep the guard on the *package* (`dpkg -s docker-ce`), not on
      `command -v docker`. Docker Desktop's WSL integration puts its own CLI on PATH, which
      previously made this skip the install and then fail at `systemctl enable`.
- [ ] **Step 4:** Bump `BOOTSTRAP_VERSION` to **4**.
- [ ] **Step 5:** Keep writing the marker last and keep `bootstrap.py` re-reading it afterwards,
      so a script that exits 0 without finishing is still caught.
- [ ] **Step 6:** Extend the existing `bash -n` shell test to assert the compose invocation and
      the pull are present.

---

## Task 8: A shared token between host and agent

**Files:** modify `host/core/bootstrap.py`, `host/client.py`, `agent/api/app.py`;
test `tests/agent/test_api_auth.py`.

Task 6 binds the agent to `0.0.0.0` inside the VM, which means every container in the VM can
reach it, and the agent holds the Docker socket. Ten lines now closes that; retrofitting it
after Phase 3 does not.

- [ ] **Step 1:** Write a failing test that a request without the token is rejected with 401 and
      that `/health` is exempt.
- [ ] **Step 2:** Generate a random token at bootstrap, write it to `/opt/omelet/agent.token`
      with mode 600, and have the agent read it at startup.
- [ ] **Step 3:** Have the host read it once via `provider.exec()` and send it as a header.
- [ ] **Step 4:** Note in the file that Phase 3 replaces this with the service-issued device
      token.

---

## Task 9: Point the host at the agent

**Files:** create `host/client.py`; modify `host/cli.py`; test `tests/host/test_client.py`.

This is the task that actually cuts the seam. It is done when `host/` contains no import from
`agent/`.

- [ ] **Step 1:** Write failing tests for the client against a fake HTTP layer: it sends the
      token, translates a 404 into a clear message, polls a job to completion, and surfaces the
      guest's own stderr on failure rather than a bare status code.
- [ ] **Step 2:** Implement the client on `urllib.request`. No new host dependency.
- [ ] **Step 3:** Rewrite `up` as: create project → upload files → start job → poll → print URL.
      The compose parsing and web detection now happen agent-side.
- [ ] **Step 4:** Rewrite `down`, `status`, `logs`, `destroy` the same way. `status` reads the
      agent's list, not a host database.
- [ ] **Step 5:** Keep the function-local imports in CLI command bodies. They keep
      `omelet --help` and the smoke test fast and avoid importing provider code on unsupported
      hosts.
- [ ] **Step 6:** Add a test asserting no module under `host/` imports from `agent/`. This is
      the completion criterion for the phase, so it belongs in the suite.
- [ ] **Step 7:** Drop `pyyaml` from the host's dependencies once nothing there parses YAML.

---

## Task 10: Catch the wrong bind address

**Files:** create `agent/core/health.py`; test `tests/agent/test_health.py`.

Today an app listening on `127.0.0.1` instead of `0.0.0.0` inside its container starts fine and
stays running, so it is classified healthy, and the URL then returns a proxy error with no
explanation anywhere. The agent is the first place that can actually detect this.

- [ ] **Step 1:** Write a failing test: a container is running, but a request through Traefik
      returns 502, and the diagnosis names the bind address as the likely cause.
- [ ] **Step 2:** Write a failing test that a slow-but-healthy stack is not misreported.
      **Traefik publishes a router a beat after the container starts**, so the first request can
      404 on a perfectly healthy stack — `install.py` already polls up to 30 seconds for exactly
      this reason. Reuse that timeout, do not invent a shorter one.
- [ ] **Step 3:** Implement: after `up` reports started, probe the project URL through Traefik,
      and on a persistent 502 inspect the container's listening sockets to confirm.
- [ ] **Step 4:** Return the diagnosis as part of project status so the CLI, and later the web
      UI, both get it for free.

---

## Task 11: State migrations

**Files:** create `agent/core/migrate.py`; modify `agent/core/state.py`;
test `tests/agent/test_migrate.py`.

- [ ] **Step 1:** Write a failing test that an empty database is brought to the current schema,
      and that running the migration twice is a no-op.
- [ ] **Step 2:** Write a failing test that a database from a future version refuses to open
      rather than corrupting itself.
- [ ] **Step 3:** Implement a `schema_version` table and an ordered migration list applied at
      agent startup.
- [ ] **Step 4:** Point `State` at `/opt/omelet/state.db`. Do not migrate the old host-side
      file — the list is rebuildable from `/opt/omelet/projects` plus `docker ps`.

---

## Task 12: Prove it end to end

**Files:** modify `host/core/install.py`; test `tests/host/test_verify_step.py`.

- [ ] **Step 1:** Rewrite `verify_step` to drive the bundled `nginx-hello` template through the
      agent API rather than through direct `core` calls.
- [ ] **Step 2:** Keep the gate at a real **HTTP 200**, keep the 30-second readiness poll, and
      keep the `finally` that tears the smoke-test project down.
- [ ] **Step 3:** Keep `VERIFY_PROJECT_ID = "omelet-selftest"` reserved. Deriving it from the
      template directory name would let `verify` compose-down a user project that happened to
      share the name.
- [ ] **Step 4:** Add an agent-version compatibility check to the install flow: if the agent is
      older than the host expects, say so plainly instead of failing somewhere obscure.

---

## Done when

- [ ] `python3 -m pytest -q` is green, with a stated new baseline.
- [ ] No module under `host/` imports from `agent/`, enforced by a test.
- [ ] A project larger than 24 KB comes up and serves HTTP 200.
- [ ] A single file can be changed without re-pushing the whole project.
- [ ] A container bound to `127.0.0.1` is reported as such instead of as healthy.
- [ ] `docker compose pull && up -d` on the stack upgrades the agent, and projects survive it.
- [ ] `stack.yml` carries no hardcoded domain or entry port.
