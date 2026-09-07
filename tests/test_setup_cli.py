import pytest
from typer.testing import CliRunner

import host.cli as cli
from host.core.images import Image
from host.core.install import DeadEnd, RebootRequired
from host.core.provider import CheckResult, Completed, Diagnosis

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


@pytest.fixture
def provisionable(monkeypatch):
    """Everything that would touch the network or a real VM, stubbed."""
    import host.core.bootstrap as bootstrap_mod
    import host.core.download as download_mod
    import host.core.install as install_mod

    monkeypatch.setattr(cli, "_provider_factory", lambda: StubProvider())
    monkeypatch.setattr(download_mod, "fetch", lambda image, dest: dest)
    monkeypatch.setattr(bootstrap_mod, "bootstrap", lambda provider: None)
    monkeypatch.setattr(install_mod, "verify_step", lambda *a, **k: None)
    return monkeypatch


def test_headless_setup_ends_by_naming_the_next_command(provisionable):
    result = runner.invoke(cli.app, ["setup", "--headless"])
    assert result.exit_code == 0
    assert "omelet up" in result.stdout, \
        "a user who waited several minutes must be told what to type next"


def test_resume_explains_why_setup_started_by_itself(provisionable):
    result = runner.invoke(cli.app, ["setup", "--headless", "--resume"])
    assert "Continuing setup after the restart" in result.stdout


def test_a_failure_offers_a_suggested_action(provisionable):
    import host.core.bootstrap as bootstrap_mod

    def explode(provider):
        raise RuntimeError("apt-get: Temporary failure resolving 'archive.ubuntu.com'")

    provisionable.setattr(bootstrap_mod, "bootstrap", explode)

    result = runner.invoke(cli.app, ["setup", "--headless"])

    assert result.exit_code == 1
    assert "archive.ubuntu.com" in result.stdout, "support still needs the raw error"
    assert "What to do" in result.stdout
    assert "Traceback" not in result.stdout


def test_uninstall_requires_purge_to_destroy_the_vm(monkeypatch):
    monkeypatch.setattr(cli, "_provider_factory", lambda: StubProvider())
    result = runner.invoke(cli.app, ["uninstall"])
    assert result.exit_code == 1
    assert "--purge" in result.stdout


def test_uninstall_cleans_up_local_state_even_when_destroy_fails(monkeypatch):
    from host.core.install import InstallState
    from host.providers import default_install_dir

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


def test_uninstall_purge_removes_state_db_and_the_vm_directory(monkeypatch):
    # Spec §8 names both explicitly; state.db and the vhdx are the two things
    # that survive an uninstall and confuse the next install.
    from host.providers import default_install_dir

    monkeypatch.setattr(cli, "_provider_factory", lambda: FailingDestroyProvider())
    install_dir = default_install_dir()
    install_dir.mkdir(parents=True, exist_ok=True)
    (install_dir / "ext4.vhdx").write_text("x")
    state_db = install_dir.parent / "state.db"
    state_db.write_text("x")

    runner.invoke(cli.app, ["uninstall", "--purge"])

    assert not state_db.exists(), "state.db must not survive a purge"
    assert not install_dir.exists(), "the VM directory must not survive a purge"


def test_uninstall_purge_succeeds_and_clears_state(monkeypatch):
    from host.core.install import InstallState
    from host.providers import default_install_dir

    monkeypatch.setattr(cli, "_provider_factory", lambda: StubProvider())
    root = default_install_dir().parent
    state = InstallState(root / "install-state.json")
    state.mark("preflight")

    result = runner.invoke(cli.app, ["uninstall", "--purge"])

    assert result.exit_code == 0
    assert state.completed() == set()


def test_selfcheck_reports_ok_for_every_bundled_asset():
    result = runner.invoke(cli.app, ["selfcheck"])
    assert result.exit_code == 0
    for name in ("bootstrap.sh", "stack.yml", "docker-compose.yml", "omelet.yaml"):
        assert name in result.stdout
    assert "MISSING" not in result.stdout


def test_selfcheck_reports_missing_and_exits_nonzero_when_an_asset_cannot_resolve(
        monkeypatch, tmp_path):
    import host.providers as providers

    # Simulate a frozen build whose datas entry for omelet.yaml went missing:
    # __file__ is what the real resolution (Path(__file__).parent) depends on.
    monkeypatch.setattr(providers, "__file__", str(tmp_path / "nonexistent" / "__init__.py"))

    result = runner.invoke(cli.app, ["selfcheck"])

    assert result.exit_code == 1
    assert "MISSING" in result.stdout
    assert "omelet.yaml" in result.stdout


def test_verify_template_resolves_to_the_bundled_compose_file():
    from host.core.install import VERIFY_TEMPLATE
    assert (VERIFY_TEMPLATE / "docker-compose.yml").is_file()


def test_cli_never_resolves_bundled_assets_from_its_own_file():
    # cli.py is the frozen entry script, and PyInstaller gives it a __file__
    # under the bundle root rather than under host/. Resolving an asset
    # from it therefore succeeds from source and silently misses in a build --
    # which is exactly how the nginx-hello template shipped missing once.
    from pathlib import Path
    src = Path("host/cli.py").read_text()
    assert "Path(__file__)" not in src, \
        "resolve bundled assets from an imported module, not from cli.py"


def test_packaging_spec_bundles_exactly_the_assets_selfcheck_verifies():
    # selfcheck's whole job is catching a bad PyInstaller `datas` entry by
    # running the exe. That only works while the two lists agree: when
    # traefik.yml was deleted, the spec kept bundling a file that no longer
    # existed and selfcheck had quietly lost its entry, so nothing failed.
    import re
    from pathlib import Path

    spec = Path("packaging/windows/omelet.spec").read_text()
    datas = re.search(r"datas=\[(.*?)\n    \]", spec, re.DOTALL)
    assert datas, "could not find the datas block in the spec"
    bundled = set(re.findall(r'"\.\./\.\./([^"]+)"', datas[1]))

    result = runner.invoke(cli.app, ["selfcheck"])
    checked = set(re.findall(r"^\S+\s+(\S+) ->", result.stdout, re.MULTILINE))

    assert bundled == checked, \
        f"only bundled: {bundled - checked}; only selfchecked: {checked - bundled}"
