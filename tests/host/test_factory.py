import host.providers as providers
from host.providers.wsl2 import Wsl2Provider
from host.providers.lima import LimaProvider


def test_factory_returns_wsl2_on_windows(monkeypatch):
    monkeypatch.setattr(providers.sys, "platform", "win32")
    assert isinstance(providers.get_provider(), Wsl2Provider)


def test_factory_returns_lima_on_macos(monkeypatch):
    monkeypatch.setattr(providers.sys, "platform", "darwin")
    assert isinstance(providers.get_provider(), LimaProvider)


def test_factory_rejects_unsupported(monkeypatch):
    monkeypatch.setattr(providers.sys, "platform", "linux")
    try:
        providers.get_provider()
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "linux" in str(e).lower()


def test_both_providers_satisfy_the_vm_provider_protocol():
    # Catches a Protocol member added without updating the implementations.
    from host.core.provider import VmProvider
    assert isinstance(Wsl2Provider(), VmProvider)
    assert isinstance(LimaProvider(), VmProvider)
