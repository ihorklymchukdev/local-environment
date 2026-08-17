from typer.testing import CliRunner

import runtime.cli as cli
from runtime.core.install import DeadEnd, RebootRequired
from runtime.core.provider import CheckResult, Completed, Diagnosis

runner = CliRunner()


class StubProvider:
    def __init__(self, diagnosis=None, reboot=False):
        self._diagnosis = diagnosis or Diagnosis([CheckResult("all good", True)])
        self._reboot = reboot
        self.resumed_with = None

    def preflight(self): return self._diagnosis
    def apply_remedy(self, remedy): pass
    def reboot_required(self): return self._reboot
    def register_resume(self, exe): self.resumed_with = exe
    def exists(self): return True
    def create(self): pass
    def exec(self, argv, *, root=False): return Completed(0, "", "")


def test_setup_reports_a_dead_end_in_plain_language(monkeypatch):
    blocked = Diagnosis([CheckResult(
        "CPU virtualization available", False,
        fix="Restart into BIOS/UEFI setup and enable Intel VT-x or AMD-V")])
    monkeypatch.setattr(cli, "_provider_factory", lambda: StubProvider(blocked))
    result = runner.invoke(cli.app, ["setup", "--headless"])
    assert result.exit_code == 1
    assert "BIOS" in result.stdout
    assert "Traceback" not in result.stdout, "non-technical users must not see a stack trace"


def test_setup_registers_resume_and_asks_for_a_restart(monkeypatch):
    provider = StubProvider(reboot=True)
    monkeypatch.setattr(cli, "_provider_factory", lambda: provider)
    result = runner.invoke(cli.app, ["setup", "--headless"])
    assert result.exit_code == 2, "a pending reboot is not a failure"
    assert "Restart your computer" in result.stdout
    assert provider.resumed_with is not None


def test_uninstall_requires_purge_to_destroy_the_vm(monkeypatch):
    monkeypatch.setattr(cli, "_provider_factory", lambda: StubProvider())
    result = runner.invoke(cli.app, ["uninstall"])
    assert result.exit_code == 1
    assert "--purge" in result.stdout
