from host.providers.wsl_checks import diagnose_wsl2


class R:
    def __init__(self, out=b"", rc=0):
        self.returncode, self.stdout, self.stderr = rc, out, b""


def test_reports_wsl_version_present():
    def runner(argv):
        return R(out="WSL version: 2.6.1.0\r\n".encode("utf-16-le"))
    diag = diagnose_wsl2(runner)
    labels = {c.label: c.ok for c in diag.checks}
    assert labels["wsl --version available"] is True


def test_reports_wsl_version_missing_with_fix():
    def runner(argv):
        return R(out=b"", rc=1)
    diag = diagnose_wsl2(runner)
    missing = [c for c in diag.checks if c.label == "wsl --version available"][0]
    assert missing.ok is False
    assert "wsl --update" in (missing.fix or "")
    assert diag.ok is False
