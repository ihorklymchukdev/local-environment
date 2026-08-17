from typer.testing import CliRunner

import runtime.cli as cli
from runtime.core.images import Image
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
    def destroy(self): pass
    def image(self): return Image("http://example.invalid/img.wsl", "0" * 64)


class FailingDestroyProvider(StubProvider):
    def destroy(self):
        raise RuntimeError("wsl.exe not found")


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


def test_uninstall_cleans_up_local_state_even_when_destroy_fails(monkeypatch):
    from runtime.core.install import InstallState
    from runtime.providers import default_install_dir

    monkeypatch.setattr(cli, "_provider_factory", lambda: FailingDestroyProvider())
    root = default_install_dir().parent
    state = InstallState(root / "install-state.json")
    state.mark("preflight")
    cache_dir = root / "cache"
    cache_dir.mkdir(parents=True)
    (cache_dir / "image.tar").write_text("x")

    result = runner.invoke(cli.app, ["uninstall", "--purge"])

    assert result.exit_code != 0, "a failed destroy must not be reported as success"
    assert "Traceback" not in result.stdout, "non-technical users must not see a stack trace"
    assert state.completed() == set(), "local state must be cleared even if destroy fails"
    assert not cache_dir.exists(), "the cache must be removed even if destroy fails"


def test_uninstall_purge_succeeds_and_clears_state(monkeypatch):
    from runtime.core.install import InstallState
    from runtime.providers import default_install_dir

    monkeypatch.setattr(cli, "_provider_factory", lambda: StubProvider())
    root = default_install_dir().parent
    state = InstallState(root / "install-state.json")
    state.mark("preflight")

    result = runner.invoke(cli.app, ["uninstall", "--purge"])

    assert result.exit_code == 0
    assert state.completed() == set()


def test_selfcheck_reports_ok_for_all_four_bundled_assets():
    result = runner.invoke(cli.app, ["selfcheck"])
    assert result.exit_code == 0
    for name in ("bootstrap.sh", "traefik.yml", "docker-compose.yml", "runtime.yaml"):
        assert name in result.stdout
    assert "MISSING" not in result.stdout


def test_selfcheck_reports_missing_and_exits_nonzero_when_an_asset_cannot_resolve(
        monkeypatch, tmp_path):
    import runtime.providers as providers

    # Simulate a frozen build whose datas entry for runtime.yaml went missing:
    # __file__ is what the real resolution (Path(__file__).parent) depends on.
    monkeypatch.setattr(providers, "__file__", str(tmp_path / "nonexistent" / "__init__.py"))

    result = runner.invoke(cli.app, ["selfcheck"])

    assert result.exit_code == 1
    assert "MISSING" in result.stdout
    assert "runtime.yaml" in result.stdout
