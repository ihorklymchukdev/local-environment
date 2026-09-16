# PyInstaller one-dir. One-file unpacks to a temp dir on every launch and is
# the mode antivirus heuristics dislike most; the installer wraps this anyway.

# setup_app is reached only through cli.setup()'s function-local import, so
# PyInstaller's static analysis never sees it -- a bundle missing one of these
# launches, shows a window, and dies on the first draw.
HIDDEN = ["host.setup_app.app", "host.setup_app.wizard", "host.setup_app.status",
          "host.setup_app.theme", "host.setup_app.widgets"]

a = Analysis(
    ["../../host/cli.py"],
    pathex=["../.."],
    datas=[
        ("../../host/provision/nginx-hello/docker-compose.yml",
         "host/provision/nginx-hello"),
        ("../../host/providers/omelet.yaml", "host/providers"),
    ],
    # Nothing from agent/ or engine/ is bundled: the VM pulls the image and
    # fetches the engine itself, and tests/host/test_frozen_bundle.py fails if
    # an entry reappears. Every dest mirrors the repo path its reader resolves
    # from __file__, so the bundle and a source checkout look identical.
    hiddenimports=HIDDEN,
)
pyz = PYZ(a.pure)

# Two executables, one Analysis, one entry point. A GUI-subsystem exe has no
# console, so anything typer echoes from it is discarded and PowerShell does
# not wait on it ($LASTEXITCODE would be stale). The CLI therefore must be
# console; the setup window must not be, or it flashes a console behind itself.
cli_exe = EXE(pyz, a.scripts, exclude_binaries=True, name="omelet", console=True)
setup_exe = EXE(pyz, a.scripts, exclude_binaries=True, name="setup", console=False)

coll = COLLECT(cli_exe, setup_exe, a.binaries, a.datas, name="Omelet")
