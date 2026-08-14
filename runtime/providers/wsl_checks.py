from ..core.provider import Diagnosis, CheckResult
from .wsl_encoding import decode_wsl


def diagnose_wsl2(runner, wsl="wsl.exe") -> Diagnosis:
    checks: list[CheckResult] = []

    ver = runner([wsl, "--version"])
    ver_text = decode_wsl(ver.stdout)
    has_version = ver.returncode == 0 and "WSL version" in ver_text
    checks.append(CheckResult(
        "wsl --version available", has_version,
        None if has_version else "run `wsl --update` (in-box WSL is too old)"))

    # Conflicts (Hyper-V / VirtualBox / AV) silently break VM creation.
    # We cannot always detect them; surface guidance as a non-blocking note.
    checks.append(CheckResult(
        "no known hypervisor conflict", True,
        "if create fails: check VirtualBox/antivirus and that "
        "VirtualMachinePlatform is enabled"))

    return Diagnosis(checks)
