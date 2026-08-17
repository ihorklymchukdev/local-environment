from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from ..core.images import WSL_IMAGES
from ..core.provider import Completed, Diagnosis
from .wsl_encoding import decode_wsl
from .wsl_checks import diagnose_wsl2, preflight_checks

RUNONCE_KEY = r"Software\Microsoft\Windows\CurrentVersion\RunOnce"
_RESUME_VALUE_NAME = "LocalRuntimeSetup"

# The user clicked No on the UAC prompt (ERROR_CANCELLED).
ELEVATION_DECLINED = 1223

# Absent off Windows, where this module is still imported by the test suite.
# 0 is "no extra creation flags", which is what every non-Windows Popen wants.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _default_runner(argv):
    return subprocess.run(argv, capture_output=True, creationflags=_NO_WINDOW)


def _default_facts() -> dict:
    from . import default_install_dir  # local import: providers/__init__ imports this module

    def wmi(query: str) -> str:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", query],
                             capture_output=True, creationflags=_NO_WINDOW)
        return out.stdout.decode("utf-8", "replace").strip()

    version = subprocess.run(["wsl.exe", "--version"], capture_output=True,
                             creationflags=_NO_WINDOW)
    # `wsl --status`'s exit code alone tells us the OS features are on,
    # without an elevated Get-WindowsOptionalFeature/DISM call: preflight
    # must stay unelevated so apply_remedy's UAC prompt is the only one.
    status = subprocess.run(["wsl.exe", "--status"], capture_output=True,
                            creationflags=_NO_WINDOW)
    return {
        "wsl_version_text": decode_wsl(version.stdout),
        "build": sys.getwindowsversion().build,
        "hypervisor_present":
            wmi("(Get-CimInstance Win32_ComputerSystem).HypervisorPresent") == "True",
        "firmware_virtualization":
            wmi("(Get-CimInstance Win32_Processor).VirtualizationFirmwareEnabled") == "True",
        # Measure the drive that will actually hold the VM, not Python's
        # drive. Anchor rather than the full path: on a first run the
        # install directory doesn't exist yet.
        "free_gb": shutil.disk_usage(
            Path(default_install_dir()).anchor or sys.prefix).free / 1024 ** 3,
        "wsl_features_enabled": status.returncode == 0,
    }


def _default_elevator(exe: str, args: list[str]) -> int:
    """Run `exe args` elevated, wait for it, and return its real exit code.

    ShellExecuteW cannot be used here: it reports success as soon as the
    process is *launched*, so a `wsl --install` that Windows Update or group
    policy rejected would be recorded as a success. ShellExecuteExW with
    SEE_MASK_NOCLOSEPROCESS hands back a process handle to wait on, which also
    makes back-to-back remedies serial instead of concurrent.
    """
    import ctypes
    from ctypes import wintypes

    SEE_MASK_NOCLOSEPROCESS = 0x00000040
    SEE_MASK_NOASYNC = 0x00000100      # keep the call valid past our own return
    INFINITE = 0xFFFFFFFF
    SW_SHOWNORMAL = 1

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("fMask", wintypes.ULONG),
            ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR),
            ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int),
            ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", ctypes.c_void_p),
            ("lpClass", wintypes.LPCWSTR),
            ("hkeyClass", wintypes.HKEY),
            ("dwHotKey", wintypes.DWORD),
            ("hIcon", wintypes.HANDLE),     # union with hMonitor
            ("hProcess", wintypes.HANDLE),
        ]

    # use_last_error keeps a private copy of the thread error taken right at the
    # call boundary. ctypes.GetLastError() reads the live value, which any
    # intervening Win32 call can clobber — and the value that matters here is
    # ERROR_CANCELLED, the most common failure the installer sees.
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]
    shell32.ShellExecuteExW.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE,
                                            ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(SHELLEXECUTEINFOW)
    info.fMask = SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NOASYNC
    info.lpVerb = "runas"
    info.lpFile = exe
    info.lpParameters = " ".join(args)
    info.nShow = SW_SHOWNORMAL

    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        # A declined UAC prompt lands here as ERROR_CANCELLED (1223).
        return ctypes.get_last_error() or 1
    if not info.hProcess:
        return 1
    try:
        kernel32.WaitForSingleObject(info.hProcess, INFINITE)
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(code)):
            return ctypes.get_last_error() or 1
        return int(code.value)
    finally:
        kernel32.CloseHandle(info.hProcess)


def _default_registry_writer(key: str, name: str, value: str) -> None:
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as handle:
        winreg.SetValueEx(handle, name, 0, winreg.REG_SZ, value)


def _default_arch() -> str:
    import platform
    return "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "amd64"


class Wsl2Provider:
    def __init__(self, distro="runtime-vm", install_dir: Path | None = None,
                 rootfs: Path | None = None, wsl="wsl.exe", runner=_default_runner,
                 facts=_default_facts, elevator=_default_elevator,
                 registry_writer=_default_registry_writer, arch=None):
        self.distro = distro
        self.install_dir = Path(install_dir) if install_dir else None
        self.rootfs = Path(rootfs) if rootfs else None
        self.wsl = wsl
        self._run = runner
        self._facts = facts
        self._elevate = elevator
        self._write_registry = registry_writer
        self._arch = arch or _default_arch()
        self._features_enabled = False

    # --- wsl.exe's own output is UTF-16LE ---
    def _meta(self, args: list[str]) -> Completed:
        p = self._run([self.wsl, *args])
        return Completed(p.returncode, decode_wsl(p.stdout), decode_wsl(p.stderr))

    def is_supported(self) -> Diagnosis:
        return diagnose_wsl2(self._run, self.wsl)

    def exists(self) -> bool:
        out = self._meta(["-l", "-q"]).stdout
        return self.distro in [line.strip() for line in out.splitlines()]

    def create(self) -> None:
        if self.install_dir is None or self.rootfs is None:
            raise ValueError("install_dir and rootfs are required to create the VM")
        if not self.rootfs.exists():
            raise FileNotFoundError(f"rootfs not found: {self.rootfs}")
        self.install_dir.mkdir(parents=True, exist_ok=True)
        imported = self._meta(["--import", self.distro, str(self.install_dir),
                               str(self.rootfs), "--version", "2"])
        if not imported.ok:
            raise RuntimeError(
                f"wsl --import failed (exit {imported.returncode}): "
                f"{(imported.stderr or imported.stdout).strip()}")
        # systemd is off by default in WSL; docker.service needs it.
        self.exec(["bash", "-lc", "printf '[boot]\\nsystemd=true\\n' > /etc/wsl.conf"],
                  root=True)
        self.stop()  # --terminate so the wsl.conf change takes effect on next boot

    def start(self) -> None:
        # Running any command boots the distro.
        self.exec(["true"])

    def stop(self) -> None:
        self._meta(["--terminate", self.distro])

    def destroy(self) -> None:
        self._meta(["--unregister", self.distro])

    def exec(self, argv: list[str], *, root: bool = False) -> Completed:
        base = [self.wsl, "-d", self.distro]
        if root:
            base += ["-u", "root"]
        base += ["--", *argv]
        p = self._run(base)
        # command passthrough is UTF-8
        return Completed(p.returncode,
                         p.stdout.decode("utf-8", "replace").strip("\n"),
                         p.stderr.decode("utf-8", "replace").strip("\n"))

    def forward(self, guest_port: int, host_port: int) -> None:
        # WSL2 localhostForwarding surfaces guest 0.0.0.0:<port> on host
        # localhost:<same port>. The edge port is chosen equal on both sides,
        # so no action is required here. Distinct raw-TCP forwards
        # (guest_port != host_port) are added in a later milestone via netsh.
        if guest_port != host_port:
            raise NotImplementedError(
                "distinct-port forwarding on WSL2 is not part of the PoC slice")

    def preflight(self) -> Diagnosis:
        return preflight_checks(**self._facts())

    def apply_remedy(self, remedy: str) -> None:
        if remedy not in ("enable_wsl_features", "update_wsl"):
            raise ValueError(f"unknown remedy: {remedy}")
        args = (["--install", "--no-distribution"] if remedy == "enable_wsl_features"
                else ["--update"])
        code = self._elevate(self.wsl, args)
        if code == ELEVATION_DECLINED:
            raise RuntimeError(
                f"`wsl {' '.join(args)}` needs administrator approval "
                "(the permission prompt was dismissed). Re-run setup and "
                "choose Yes when Windows asks.")
        if code != 0:
            raise RuntimeError(
                f"`wsl {' '.join(args)}` could not be completed (code {code}). "
                "Windows Update may be busy, or company policy may block WSL. "
                "Restart the computer and run setup again.")
        if remedy == "enable_wsl_features":
            self._features_enabled = True

    def reboot_required(self) -> bool:
        return self._features_enabled

    def register_resume(self, exe_path: str) -> None:
        self._write_registry(RUNONCE_KEY, _RESUME_VALUE_NAME,
                             f'"{exe_path}" setup --resume')

    def image(self):
        return WSL_IMAGES[self._arch]
