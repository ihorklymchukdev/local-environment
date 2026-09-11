# PyInstaller one-dir. One-file unpacks to a temp dir on every launch and is
# the mode antivirus heuristics dislike most; the installer wraps this anyway.

a = Analysis(
    ["../../host/cli.py"],
    pathex=["../.."],
    datas=[
        ("../../host/provision/bootstrap.sh", "host/provision"),
        ("../../host/provision/stack.yml", "host/provision"),
        ("../../host/provision/guest/omelet.py", "host/provision/guest"),
        ("../../host/provision/install-agents.sh", "host/provision"),
        ("../../host/provision/login-users.sh", "host/provision"),
        ("../../host/provision/agents/omelet.md", "host/provision/agents"),
        ("../../host/provision/agents/skills/omelet-setup/SKILL.md",
         "host/provision/agents/skills/omelet-setup"),
        ("../../host/provision/nginx-hello/docker-compose.yml",
         "host/provision/nginx-hello"),
        ("../../host/providers/omelet.yaml", "host/providers"),
    ],
    # Nothing from agent/ is bundled: it ships as an image the VM pulls, and
    # tests/host/test_frozen_bundle.py fails if an entry reappears. Every dest
    # above mirrors the repo path its reader resolves from __file__, so the
    # bundle and a source checkout look identical to the code.
    hiddenimports=["host.setup_app.app"],
)
pyz = PYZ(a.pure)

# Two executables, one Analysis, one entry point. A GUI-subsystem exe has no
# console, so anything typer echoes from it is discarded and PowerShell does
# not wait on it ($LASTEXITCODE would be stale). The CLI therefore must be
# console; the setup window must not be, or it flashes a console behind itself.
cli_exe = EXE(pyz, a.scripts, exclude_binaries=True, name="omelet", console=True)
setup_exe = EXE(pyz, a.scripts, exclude_binaries=True, name="setup", console=False)

coll = COLLECT(cli_exe, setup_exe, a.binaries, a.datas, name="Omelet")
