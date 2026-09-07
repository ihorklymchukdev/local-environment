# Blueprint: Omelet (VM + Docker + Exposed Port)

**PoC scope:** bring up a managed Linux VM, install Docker inside it, run a compose project, and hand back a working URL on the host. No UI, no AI, no deploy.

**Target platforms:** Windows 11 + WSL2 (primary dev platform), macOS 13+ Apple Silicon (partner testing).

---

## 1. Core decision: one guest system, two ways to launch it

Don't abstract Docker — abstract the **VM**. Everything above the guest OS must be identical on both platforms.

```
┌─────────────────────────────────────────────┐
│ HOST (Windows / macOS)                       │
│                                              │
│  omelet-cli (Python)                        │
│    └── VmProvider (abstraction)              │
│          ├── Wsl2Provider   → wsl.exe        │
│          └── LimaProvider   → limactl        │
│                                              │
│  localhost:39080 ─────────┐                  │
└───────────────────────────┼──────────────────┘
                            │
┌───────────────────────────▼──────────────────┐
│ GUEST: Ubuntu 24.04 (identical on both OSes) │
│                                              │
│  dockerd                                     │
│  ├── traefik  :80  ← single entry point      │
│  ├── proj-a_web    (labels → traefik)        │
│  ├── proj-a_db                               │
│  └── proj-b_web                              │
│                                              │
│  /opt/omelet/projects/<id>/  ← files live here │
└──────────────────────────────────────────────┘
```

**Why this shape:** the guest is plain Linux running plain Docker. That gives you parity with any VPS and makes all project logic platform-independent. The OS difference collapses into ~200 lines across two providers.

**Why not Docker Desktop:** commercial licensing, weight, and you don't control its state. **Why not Podman machine:** a single CLI across both OSes looks appealing, but compose compatibility is less predictable — and compose is exactly what you're building on.

---

## 2. Provider contract

Keep it minimal. Anything that doesn't fit these seven methods is a sign platform logic is leaking upward.

```python
class VmProvider(Protocol):
    def is_supported(self) -> Diagnosis: ...      # hypervisor present, versions, privileges
    def exists(self) -> bool: ...
    def create(self) -> None: ...                 # fetch rootfs, create the VM
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def destroy(self) -> None: ...
    def exec(self, argv: list[str], *, root=False) -> Completed: ...
    def forward(self, guest_port: int, host_port: int) -> None: ...
```

Everything else (installing Docker, Traefik, compose up) is implemented **once** on top of `exec`.

---

## 3. Windows: WSL2

**Don't touch the user's default distro.** Create your own, isolated one:

```
wsl --import omelet-vm %LOCALAPPDATA%\Omelet\vm ubuntu-24.04-rootfs.tar.gz --version 2
wsl -d omelet-vm -u root -- /bin/bash /opt/omelet/bootstrap.sh
```

The rootfs comes from `cloud-images.ubuntu.com` (WSL variant or the base rootfs).

**Preconditions to check in `is_supported()`:**
- Windows 10 2004+ / Windows 11
- `VirtualMachinePlatform` and `Microsoft-Windows-Subsystem-Linux` enabled
- `wsl --version` returns a version (old in-box WSL doesn't have it → needs `wsl --update`)
- virtualization enabled in BIOS
- conflicts with Hyper-V / VirtualBox / antivirus — a common failure cause, detect it separately

**Ports:** WSL2 defaults to `localhostForwarding=true`, so anything listening in the guest is reachable on the host's `localhost`. It works, but it's not a contract:
- behaviour differs under `networkingMode=mirrored` (Win11)
- binds to `127.0.0.1` only inside the guest sometimes don't get through → **always bind to `0.0.0.0` in the guest**

**VM config** (`%USERPROFILE%\.wslconfig`) — set this or `vmmem` will eat all available memory:
```ini
[wsl2]
memory=4GB
processors=4
autoMemoryReclaim=gradual
```
Note: `.wslconfig` is global across all of the user's distros. If you're changing something that isn't yours, ask first.

---

## 4. macOS: Lima

```
limactl start --name=omelet-vm --tty=false ./omelet.yaml
limactl shell omelet-vm sudo /opt/omelet/bootstrap.sh
```

`omelet.yaml`:
```yaml
vmType: vz                 # Apple Virtualization, macOS 13+; qemu on Intel
rosetta:
  enabled: true            # x86 images on Apple Silicon
images:
  - location: "https://cloud-images.ubuntu.com/releases/24.04/release/ubuntu-24.04-server-cloudimg-arm64.img"
    arch: "aarch64"
cpus: 4
memory: "4GiB"
disk: "60GiB"
mounts: []                 # see §7 — no host mounts needed for the PoC
portForwards:
  - guestPort: 80
    hostPort: 39080
```

Lima auto-forwards ports bound to `0.0.0.0` in the guest, but an explicit `portForwards` entry is more reliable.

**Distribution:** `brew install lima` for the PoC. For release, bundle `limactl` into the app (Apache 2.0 permits this). Homebrew as a product dependency is unacceptable.

---

## 5. Guest bootstrap

One idempotent script, shared across both OSes. Safe to run repeatedly.

```bash
#!/usr/bin/env bash
set -euo pipefail

# 1. docker-ce from the official repo (not Ubuntu's docker.io)
# 2. systemctl enable --now docker
#    IMPORTANT: systemd is off by default in WSL →
#    /etc/wsl.conf: [boot]\nsystemd=true, then wsl --terminate
# 3. docker network create edge
# 4. mkdir -p /opt/omelet/projects
# 5. traefik as a container: docker provider, entrypoint :80, --restart=always
# 6. write /opt/omelet/.bootstrapped with a version
```

Version the marker (`.bootstrapped` with a number). App update → new bootstrap → migration without recreating the VM.

---

## 6. Routing: one port, many projects

**Don't forward a port per project.** Port collisions are the main source of pain, and the user should never have to learn the word "port".

Exactly one port is forwarded: `guest:80 → host:39080`. Traefik then routes by hostname via docker labels.

**Key rule: Omelet never edits the user's compose file.** It generates a separate overlay and runs:

```
docker compose -f docker-compose.yml -f .omelet/overlay.yml up -d
```

`overlay.yml` is generated from the project metadata and attaches the `edge` network and a Traefik router to the right service:

```yaml
services:
  <web_service>:                     # name from the user's compose, never hardcoded
    networks: [default, edge]
    labels:
      traefik.enable: "true"
      traefik.http.routers.<proj>.rule: "Host(`<proj>.<domain>`)"
      traefik.http.services.<proj>.loadbalancer.server.port: "<internal_port>"
networks:
  edge:
    external: true
```

The user gets `http://myproj.<domain>:39080`.

The compose file stays clean and runnable with a plain `docker compose up` on any VPS without Omelet — that's the parity this whole design exists for.

**Gotcha to settle during the PoC:** `*.localhost` resolves to `127.0.0.1` in Chrome, Edge and Firefox, but **Safari does not do this**. Options, best first:
1. `<proj>.127-0-0-1.sslip.io` — public DNS, works everywhere, zero setup, but requires internet
2. a `/etc/hosts` entry (Mac) / `%WINDIR%\System32\drivers\etc\hosts` (Windows) — requires admin rights
3. fall back to a direct `localhost:PORT` for a single active project

For the PoC use (1) with (3) as fallback — test both browsers immediately, this decision is hard to reverse later.

---

## 6.5. Project contract: exactly two metadata fields

Omelet **knows nothing about stacks**. It doesn't know what WordPress, Laravel, Next.js or Django are. It knows one thing: a project is a directory containing a `docker-compose.yml`.

Everything Omelet adds is derived from two fields in `.omelet/project.yml`:

```yaml
id: myproj
web:
  service: app          # which service serves HTTP
  port: 8080            # which port it listens on inside the container
```

Both have sensible defaults: if there's only one service, take it; if it declares `ports:` or `EXPOSE`, read it from there. The user (or later, the agent) only edits when auto-detection misses.

**Consequences to support from day one, because none of them are stack-specific:**

- **Multiple HTTP services.** `web` is a list, not an object. Frontend + API in one compose file is normal (`myproj.<domain>` and `api.myproj.<domain>`).
- **Non-HTTP services.** Redis, workers, queues — no labels at all, they just run on the project's `default` network.
- **Raw TCP exposure.** Users will want to connect DBeaver/TablePlus to their database. Traefik won't help here — you need a separate mechanism: a dynamic `guest:<random> → host:<allocated>` forward for a specific service, with the port recorded in state. This is the second most common request after "show me the URL".
- **`build:` instead of `image:`.** A compose file with a local Dockerfile must work without exceptions. The first build is slow — show progress, don't go silent.
- **`.env` / `env_file`.** Look for them in the project root; don't touch them.

**Templates (`templates/`) are not part of the engine.** They're just ready-made compose files for a quick start. The engine must accept a compose file generated by an agent, downloaded from GitHub, or hand-written, all the same way. If a stack name appears anywhere in the core code, something has gone wrong.

---

## 7. Project files: the canonical copy lives inside the VM

The most common mistake is keeping files on the host and mounting them into the VM.

- **WSL2:** `/mnt/c/...` over 9p is several times slower. Any project with thousands of small files (`vendor/`, `node_modules/`) will crawl.
- **macOS:** virtiofs is decent, but not native.

**PoC approach:** the canonical copy lives in the guest (`/opt/omelet/projects/<id>`), and the host gets access over a network share:
- Windows: `\\wsl$\omelet-vm\opt\omelet\projects\<id>` — works out of the box
- macOS: a reverse `limactl` mount, or SSHFS over Lima's SSH port

Archive import: copy into the guest, then unpack there. Never unpack on the host.

---

## 8. Repository structure

```
omelet/
├── cli.py                  # Typer: up, down, status, logs, destroy
├── core/
│   ├── provider.py         # Protocol + platform factory
│   ├── project.py          # compose lifecycle (stack-agnostic)
│   ├── overlay.py          # generates the Omelet overlay from project.yml
│   ├── detect.py           # auto-detects web service and port from compose
│   ├── state.py            # SQLite: projects, ports, snapshots
│   └── diagnose.py         # preconditions + human-readable error messages
├── providers/
│   ├── wsl2.py
│   └── lima.py
├── guest/
│   ├── bootstrap.sh
│   └── traefik.yml
├── templates/              # NOT part of the engine — just starter compose files
└── api/
    └── server.py           # 127.0.0.1 JSON-RPC — attachment point for GUI/MCP later
```

**Language:** Python for the entire core. No shell needed yet, but build the local API server in from the start — otherwise you'll be rewriting the CLI for the GUI later.

**Important:** `providers/` is the only place in the codebase where `if platform` may appear. If `if sys.platform` shows up anywhere else, the abstraction is leaking.

---

## 9. Milestones

| # | Deliverable | Done when |
|---|---|---|
| M0 | `omelet doctor` | tells the user honestly what's missing and how to fix it, on both OSes |
| M1 | `omelet vm create` | VM exists, `exec("uname -a")` works |
| M2 | bootstrap | `docker info` works in the guest, idempotent on re-run |
| M3 | traefik + port | `curl localhost:39080` returns a Traefik 404 (that's success) |
| M4 | `omelet up <dir>` | single-service compose (nginx) resolves in the browser |
| M5 | state and dependencies | multi-service compose with a DB; data survives a VM restart |
| M6 | concurrency | 3+ projects on different stacks running simultaneously, no collisions |
| M7 | auto-detection | `detect.py` correctly guesses web service and port across all test compose files |
| M8 | lifecycle | stop/start VM, destroy a project, full reset |

**PoC acceptance test — the most important thing in this document:**

Take **five arbitrary `docker-compose.yml` files from GitHub** that you didn't write: something on PHP-FPM + nginx + MySQL, something on Node + Postgres, something on Python + Redis, something using `build:` instead of `image:`, and something with two HTTP services. Zero stack-specific code in Omelet.

Success = all five come up with a single command, on Windows and on Mac, and each returns a working URL.

If any of them required adding something to the core, the abstraction is wrong — and it's far cheaper to fix now than after the GUI exists. How many of the five pass on the first attempt is your real stack-agnosticism metric.

---

## 10. Deliberately out of scope for the PoC

- GUI, tray icon, auto-update
- any agent integration
- deploy, VPS, secret manager
- snapshots and backups (but structure `state.py` so they can be added)
- Linux as a host platform (trivial to add later — provider = "none", Docker directly)
- code signing and notarization

---

## 11. Risks worth budgeting time for

1. **systemd in WSL** — without it there's no proper `docker.service`. Fixed via `wsl.conf`, but it requires a `wsl --terminate` and a restart. Build this into the `create()` state machine, not into the docs.
2. **First run.** Downloading the rootfs plus images means gigabytes. Measure the real elapsed time on an ordinary connection; if it's 15+ minutes the product is dead, and that needs thinking about now, not after the UI.
3. **Antivirus on Windows** silently breaks VM creation. Catch the specific error and surface a clear message.
4. **Apple Silicon vs x86 images.** Arbitrary compose files from the internet regularly reference images with no arm64 build. Rosetta in Lima covers this, but slower and not always. Omelet must **recognize** the situation and explain it clearly rather than dying with `exec format error` — this is the same class of problem you'll hit again on VPS deploy, so the mechanism pays for itself twice.
5. **Port 39080 already in use.** Keep a range and record the chosen port in state.
6. **Compose files that don't come up on their own.** Some GitHub projects need a `.env`, migrations, or a seed step. Omelet shouldn't try to fix this — but it must **clearly distinguish** "failed to start" from "started, but the service is crashing", and expose logs, exit codes and restart-loop causes. That's the same interface an agent will consume later.
