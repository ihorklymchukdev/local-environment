import os
import sys
from pathlib import Path

from .wsl2 import Wsl2Provider
from .lima import LimaProvider, find_limactl


def default_install_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", str(Path.home()))
        return Path(base) / "Omelet" / "vm"
    return Path.home() / ".local" / "share" / "omelet" / "vm"


def get_provider():
    if sys.platform == "win32":
        rootfs = Path(os.environ["OMELET_ROOTFS"]) if os.environ.get("OMELET_ROOTFS") else None
        return Wsl2Provider(install_dir=default_install_dir(), rootfs=rootfs)
    if sys.platform == "darwin":
        # Resolved here rather than left to PATH: the provider is handed a path
        # the same way the WSL2 one is handed a rootfs, and the setup window
        # runs without a shell's PATH. See find_limactl.
        return LimaProvider(config=Path(__file__).parent / "omelet.yaml",
                            limactl=find_limactl())
    raise RuntimeError(f"unsupported host platform: {sys.platform} "
                       "(only Windows/WSL2 and macOS/Lima are supported)")
