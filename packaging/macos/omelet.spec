# PyInstaller one-dir, wrapped in an .app bundle. The Windows twin builds two
# executables from one Analysis because the difference there is only the
# subsystem; here they differ in their entry script — the bundle's main
# executable has to default to the setup command, since Finder passes no
# arguments (see setup_main.py).

# Spec files are exec'd with PyInstaller's own namespace, which does not
# include the standard library.
import os

DATAS = [
    ("../../host/provision/nginx-hello/docker-compose.yml",
     "host/provision/nginx-hello"),
    ("../../host/providers/omelet.yaml", "host/providers"),
]
# Nothing from agent/ or engine/ is bundled: the VM pulls the image and fetches
# the engine itself, and tests/host/test_frozen_bundle.py fails if an entry
# reappears. Every dest mirrors the repo path its reader resolves from __file__,
# so the bundle and a source checkout look identical.

# setup_app is reached only through cli.setup()'s function-local import, so
# PyInstaller's static analysis never sees it -- a bundle missing one of these
# launches, shows a Dock icon, and dies on the first draw.
HIDDEN = ["host.setup_app.app", "host.setup_app.wizard", "host.setup_app.status",
          "host.setup_app.theme", "host.setup_app.widgets"]

cli = Analysis(["../../host/cli.py"], pathex=["../.."], datas=DATAS,
               hiddenimports=HIDDEN)
gui = Analysis(["setup_main.py"], pathex=["../.."], datas=DATAS,
               hiddenimports=HIDDEN)

# The GUI executable comes first on purpose: BUNDLE takes CFBundleExecutable
# from the first EXECUTABLE in the COLLECT, and double-clicking Omelet.app must
# open the setup window, not a CLI with nothing to do. `omelet` lands beside it
# in Contents/MacOS, which is what the installer symlinks onto PATH.
#
# The name is not "Omelet": both executables share one directory, and a Mac
# filesystem is case-insensitive by default, so `Omelet` and `omelet` are one
# file. COLLECT wrote them in order and the second silently replaced the first
# -- the built app launched the CLI, printed its help to a console nobody was
# watching, and quit. Nothing about the build said so.
setup_exe = EXE(PYZ(gui.pure), gui.scripts, exclude_binaries=True,
                name="omelet-setup", console=False)
cli_exe = EXE(PYZ(cli.pure), cli.scripts, exclude_binaries=True,
              name="omelet", console=True)

coll = COLLECT(setup_exe, cli_exe,
               gui.binaries, gui.datas, cli.binaries, cli.datas,
               name="Omelet")

app = BUNDLE(
    coll,
    name="Omelet.app",
    bundle_identifier="dev.omelet.app",
    version=os.environ.get("OMELET_VERSION", "0.0.0"),
    info_plist={
        # Both of these correct what BUNDLE infers, and both were wrong in a
        # build that otherwise looked clean:
        #
        # CFBundleExecutable is taken from the first executable in COLLECT's
        # own (sorted) table, which is `omelet` however the spec orders them --
        # so a double-click ran the CLI. LSBackgroundOnly is set from the
        # collection's console flag, and an app marked background-only has no
        # Dock icon and cannot bring its window forward.
        "CFBundleExecutable": "omelet-setup",
        "LSBackgroundOnly": False,
        # vz — the VM type omelet.yaml asks Lima for — is macOS 13+.
        "LSMinimumSystemVersion": "13.0",
        "NSHighResolutionCapable": True,
        # Nothing here opens documents or takes a URL scheme; the window is the
        # whole interface.
        "CFBundleName": "Omelet",
        "CFBundleDisplayName": "Omelet",
        "CFBundleShortVersionString": os.environ.get("OMELET_VERSION", "0.0.0"),
    },
)
