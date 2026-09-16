# Omelet (PoC)

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
`%LOCALAPPDATA%\Omelet\cache` (~400 MB, once), then creates the VM and
installs Docker + Traefik in it. Expect several minutes on the first run.

It also drops a `omelet.cmd` shim in the repo, so afterwards:

```powershell
.\omelet up .\my-project   # prints http://my-project.127-0-0-1.sslip.io:39080
.\omelet status
```

Useful flags: `-Rootfs <path>` to use a rootfs you already have,
`-NoCreate` to install without touching the VM.

**Important:** the CLI must run on Windows, not inside WSL. It drives
`wsl.exe`, and `get_provider()` raises `unsupported host platform: linux` if
you run it from a WSL shell.

## Setup (macOS)

Build the installer, then install it:

```bash
brew install lima                  # not bundled yet; setup stops without it
python3.12 -m venv .venv && .venv/bin/python -m pip install -e ".[dev]"
bash packaging/macos/build.sh      # -> dist/OmeletSetup-<version>.pkg
sudo installer -pkg dist/OmeletSetup-0.1.0.pkg -target /
```

The build needs a Python 3.12+ **with tkinter** (Homebrew splits it out:
`brew install python-tk@3.13`), and produces a native-architecture package — an
Apple Silicon build refuses to install on Intel rather than installing binaries
it cannot run. It is unsigned unless `OMELET_CODESIGN_ID` and
`OMELET_INSTALLER_ID` are set, so a *downloaded* copy needs right-click > Open;
a locally built one installs normally.

The package puts `Omelet.app` in `/Applications` and `omelet` on your PATH, and
stops there. Open Omelet from Applications to build the VM (or run
`omelet setup --headless`) — the installer deliberately does not do it for you:
its scripts run as root, and Lima keeps VMs per user under `~/.lima`.

To remove everything, including the VM and every project in it:
`bash packaging/macos/uninstall.sh`.

**Unverified below the packaging.** No Lima VM has ever been created; setup is
known to run as far as its first check. See `docs/lima-verification-report.md`
and `docs/macos-install-test-matrix.md` for exactly what has and has not been
run.

## Setup (manual)

```bash
pip install -e ".[dev]"
omelet doctor            # reports what this host is missing, non-zero if unsupported
```

On Windows, `omelet vm create` additionally needs `OMELET_ROOTFS` pointing at
an Ubuntu 24.04 rootfs — Canonical's official WSL image, the same file
Microsoft's WSL distro manifest points at:

- amd64: <https://releases.ubuntu.com/24.04.4/ubuntu-24.04.4-wsl-amd64.wsl>
  (391 MB, sha256 `9b2f7730dc68227dd04a9f3e5eab86ad85caf556b8606ad94f1f29ff5c4fd3f5`)
- arm64: <https://cdimages.ubuntu.com/releases/24.04.4/release/ubuntu-24.04.4-wsl-arm64.wsl>

A `.wsl` file is a gzipped rootfs tarball; `wsl --import` takes it as-is. The
value must be a **Windows** path — it goes straight to `wsl.exe --import`,
which cannot resolve a WSL-side `/home/...` path.

```powershell
$env:OMELET_ROOTFS = "C:\Users\you\Downloads\ubuntu-24.04.4-wsl-amd64.wsl"
omelet vm create
```

`vm create` imports the `omelet-vm` distro under `%LOCALAPPDATA%\Omelet\vm`,
enables systemd, and installs the Omelet engine inside it (fetched from `OMELET_ENGINE_URL`,
default `engine/get.sh` on GitHub; set `OMELET_ENGINE_REF` to a branch or tag to install
something other than the latest `engine-v*` release). The imported distro
runs as root: `create()` replaces `/etc/wsl.conf` with a `[boot] systemd=true`
stanza, dropping the image's default-user setting. `OMELET_ROOTFS` is read
only by `vm create`; no other command needs it.

Manage running projects and the VM:

```bash
omelet status            # list known projects and their status
omelet logs <id>         # show a project's container logs
omelet down <id>         # stop a project's containers
omelet destroy <id>      # stop and forget a project
omelet vm stop           # stop the VM
omelet vm destroy        # destroy the VM
```

## Looking inside the VM

There is no `omelet shell` command; use the VM tool for your platform.

### macOS

```bash
limactl shell omelet-vm                      # a shell in the VM, as your user
limactl shell omelet-vm -- sudo -i           # root
limactl shell omelet-vm -- sudo docker ps    # traefik + projects
limactl shell omelet-vm -- sudo cat /opt/omelet/engine.version
limactl shell omelet-vm -- sudo bash /opt/omelet/engine/install.sh engine-vX.Y.Z --repair
```

`sudo` needs no password and no TTY. `limactl list` shows the VM's status, ports
and directory.

**Nothing from the Mac is mounted.** `omelet.yaml` sets `mounts: []`, so the VM
cannot see your files; projects reach it over HTTP (`AgentClient.upload_directory`),
never through a shared folder.

### Windows

Use `wsl.exe`. Note that every WSL distro
reports your Windows machine name as its hostname, so the prompt does not tell
you which one you are in — always pass `-d omelet-vm`.

```powershell
wsl -d omelet-vm -u root                                     # a shell in the VM
wsl -d omelet-vm -u root -- docker ps                        # traefik + projects
wsl -d omelet-vm -u root -- cat /opt/omelet/engine.version            # installed engine ref
wsl -d omelet-vm -u root -- bash /opt/omelet/engine/install.sh engine-vX.Y.Z --repair   # re-run, live output
```

Projects land in `/opt/omelet/projects/<id>/`, with the generated Traefik
overlay at `<id>/.omelet/overlay.yml` beside your `docker-compose.yml`.

## Verified vs live

- Verified here: all core logic (detection, overlay, state, failure
  classification), provider command construction, the WSL encoding decoder, and
  the platform-boundary invariant.
- Left for the live run: the rootfs/image download, the browser check,
  and the five-compose acceptance test on real Windows and macOS hosts.
- Note: in this sandbox, `/tmp/pytest-of-ihor` is root-owned, which breaks
  `tmp_path`-based tests unless `TMPDIR` is redirected to a writable directory
  when running the suite — a sandbox artifact, not a code issue.
