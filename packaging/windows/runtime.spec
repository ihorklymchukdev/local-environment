# PyInstaller one-dir. One-file unpacks to a temp dir on every launch and is
# the mode antivirus heuristics dislike most; the installer wraps this anyway.

a = Analysis(
    ["../../runtime/cli.py"],
    pathex=["../.."],
    datas=[
        ("../../runtime/guest/bootstrap.sh", "runtime/guest"),
        ("../../runtime/guest/traefik.yml", "runtime/guest"),
        ("../../runtime/templates/nginx-hello/docker-compose.yml",
         "runtime/templates/nginx-hello"),
        ("../../runtime/providers/runtime.yaml", "runtime/providers"),
    ],
    hiddenimports=["runtime.setup_app.app"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, name="runtime", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="LocalRuntime")
