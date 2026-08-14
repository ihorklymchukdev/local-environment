import os
import sys
from pathlib import Path

from .wsl2 import Wsl2Provider
from .lima import LimaProvider


def default_install_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", str(Path.home()))
        return Path(base) / "Runtime" / "vm"
    return Path.home() / ".local" / "share" / "runtime" / "vm"


def get_provider():
    if sys.platform == "win32":
        rootfs = Path(os.environ["RUNTIME_ROOTFS"]) if os.environ.get("RUNTIME_ROOTFS") else None
        return Wsl2Provider(install_dir=default_install_dir(), rootfs=rootfs)
    if sys.platform == "darwin":
        return LimaProvider(config=Path(__file__).parent / "runtime.yaml")
    raise RuntimeError(f"unsupported host platform: {sys.platform} "
                       "(only Windows/WSL2 and macOS/Lima are supported)")
