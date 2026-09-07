# PyInstaller one-dir. One-file unpacks to a temp dir on every launch and is
# the mode antivirus heuristics dislike most; the installer wraps this anyway.

a = Analysis(
    ["../../omelet/cli.py"],
    pathex=["../.."],
    datas=[
        ("../../omelet/guest/bootstrap.sh", "omelet/guest"),
        ("../../omelet/guest/traefik.yml", "omelet/guest"),
        ("../../omelet/templates/nginx-hello/docker-compose.yml",
         "omelet/templates/nginx-hello"),
        ("../../omelet/providers/omelet.yaml", "omelet/providers"),
    ],
    hiddenimports=["omelet.setup_app.app"],
)
pyz = PYZ(a.pure)

# Two executables, one Analysis, one entry point. A GUI-subsystem exe has no
# console, so anything typer echoes from it is discarded and PowerShell does
# not wait on it ($LASTEXITCODE would be stale). The CLI therefore must be
# console; the setup window must not be, or it flashes a console behind itself.
cli_exe = EXE(pyz, a.scripts, exclude_binaries=True, name="omelet", console=True)
setup_exe = EXE(pyz, a.scripts, exclude_binaries=True, name="setup", console=False)

coll = COLLECT(cli_exe, setup_exe, a.binaries, a.datas, name="Omelet")
