# Local Runtime (PoC)

Bring up a Linux VM, install Docker in it, run any `docker-compose` project, and
get a working URL on the host. Windows/WSL2 (verified by unit tests) and
macOS/Lima (parity, unverified).

## Install

```bash
pip install -e ".[dev]"
```

## Check your host

```bash
runtime doctor
```

Reports whether this host can run the VM (WSL2 on Windows, Lima on macOS) and
how to fix what's missing. Exits non-zero if unsupported.

## Live run (Windows/WSL2)

The CLI shells out to `wsl.exe`. Provide an Ubuntu 24.04 rootfs tarball (from
`https://cloud-images.ubuntu.com`) via the `RUNTIME_ROOTFS` environment
variable — the provider factory reads it when constructing the WSL2 provider:

```bash
RUNTIME_ROOTFS=C:\path\ubuntu-24.04-rootfs.tar.gz runtime vm create
```

`vm create` imports the `runtime-vm` distro, enables systemd, and bootstraps
Docker + Traefik inside it.

```bash
runtime up ./my-project   # prints http://my-project.127-0-0-1.sslip.io:39080
```

Manage running projects and the VM:

```bash
runtime status            # list known projects and their status
runtime logs <id>         # show a project's container logs
runtime down <id>         # stop a project's containers
runtime destroy <id>      # stop and forget a project
runtime vm stop           # stop the VM
runtime vm destroy        # destroy the VM
```

## Verified vs live

- Verified here: all core logic (detection, overlay, state, failure
  classification), provider command construction, the WSL encoding decoder, and
  the platform-boundary invariant.
- Left for the live run: the multi-GB rootfs/image download, the browser check,
  and the five-compose acceptance test on real Windows and macOS hosts.
- Note: in this sandbox, `/tmp/pytest-of-ihor` is root-owned, which breaks
  `tmp_path`-based tests unless `TMPDIR` is redirected to a writable directory
  when running the suite — a sandbox artifact, not a code issue.
