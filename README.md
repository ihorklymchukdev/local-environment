# Local Runtime (PoC)

Bring up a Linux VM, install Docker in it, run any `docker-compose` project, and
get a working URL on the host. Windows/WSL2 (verified by unit tests) and
macOS/Lima (parity, unverified).

## Setup (Windows)

Run this from the repo root in PowerShell. It is the whole install:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

`-ExecutionPolicy Bypass` applies to that one invocation only; it changes
nothing on your machine. The script finds a Python 3.12+, builds `.venv`,
installs the package, downloads and checksums the Ubuntu 24.04 rootfs into
`%LOCALAPPDATA%\Runtime\cache` (~400 MB, once), then creates the VM and
installs Docker + Traefik in it. Expect several minutes on the first run.

It also drops a `runtime.cmd` shim in the repo, so afterwards:

```powershell
.\runtime up .\my-project   # prints http://my-project.127-0-0-1.sslip.io:39080
.\runtime status
```

Useful flags: `-Rootfs <path>` to use a rootfs you already have,
`-NoCreate` to install without touching the VM.

**Important:** the CLI must run on Windows, not inside WSL. It drives
`wsl.exe`, and `get_provider()` raises `unsupported host platform: linux` if
you run it from a WSL shell.

## Setup (manual, or macOS)

```bash
pip install -e ".[dev]"
runtime doctor            # reports what this host is missing, non-zero if unsupported
```

On Windows, `runtime vm create` additionally needs `RUNTIME_ROOTFS` pointing at
an Ubuntu 24.04 rootfs — Canonical's official WSL image, the same file
Microsoft's WSL distro manifest points at:

- amd64: <https://releases.ubuntu.com/24.04.4/ubuntu-24.04.4-wsl-amd64.wsl>
  (391 MB, sha256 `9b2f7730dc68227dd04a9f3e5eab86ad85caf556b8606ad94f1f29ff5c4fd3f5`)
- arm64: <https://cdimages.ubuntu.com/releases/24.04.4/release/ubuntu-24.04.4-wsl-arm64.wsl>

A `.wsl` file is a gzipped rootfs tarball; `wsl --import` takes it as-is. The
value must be a **Windows** path — it goes straight to `wsl.exe --import`,
which cannot resolve a WSL-side `/home/...` path.

```powershell
$env:RUNTIME_ROOTFS = "C:\Users\you\Downloads\ubuntu-24.04.4-wsl-amd64.wsl"
runtime vm create
```

`vm create` imports the `runtime-vm` distro under `%LOCALAPPDATA%\Runtime\vm`,
enables systemd, and bootstraps Docker + Traefik inside it. The imported distro
runs as root: `create()` replaces `/etc/wsl.conf` with a `[boot] systemd=true`
stanza, dropping the image's default-user setting. `RUNTIME_ROOTFS` is read
only by `vm create`; no other command needs it.

Manage running projects and the VM:

```bash
runtime status            # list known projects and their status
runtime logs <id>         # show a project's container logs
runtime down <id>         # stop a project's containers
runtime destroy <id>      # stop and forget a project
runtime vm stop           # stop the VM
runtime vm destroy        # destroy the VM
```

## Looking inside the VM

There is no `runtime shell` command; use `wsl.exe`. Note that every WSL distro
reports your Windows machine name as its hostname, so the prompt does not tell
you which one you are in — always pass `-d runtime-vm`.

```powershell
wsl -d runtime-vm -u root                                     # a shell in the VM
wsl -d runtime-vm -u root -- docker ps                        # traefik + projects
wsl -d runtime-vm -u root -- cat /opt/runtime/.bootstrapped   # bootstrap version
wsl -d runtime-vm -u root -- bash /opt/runtime/bin/bootstrap.sh 1   # re-run, live output
```

Projects land in `/opt/runtime/projects/<id>/`, with the generated Traefik
overlay at `<id>/.runtime/overlay.yml` beside your `docker-compose.yml`.

## Verified vs live

- Verified here: all core logic (detection, overlay, state, failure
  classification), provider command construction, the WSL encoding decoder, and
  the platform-boundary invariant.
- Left for the live run: the rootfs/image download, the browser check,
  and the five-compose acceptance test on real Windows and macOS hosts.
- Note: in this sandbox, `/tmp/pytest-of-ihor` is root-owned, which breaks
  `tmp_path`-based tests unless `TMPDIR` is redirected to a writable directory
  when running the suite — a sandbox artifact, not a code issue.
