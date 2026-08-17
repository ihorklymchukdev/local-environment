import pytest

from runtime.providers.wsl2 import RUNONCE_KEY, Wsl2Provider

HEALTHY_FACTS = dict(
    wsl_version_text="WSL version: 2.3.26.0", build=26100,
    hypervisor_present=True, firmware_virtualization=True, free_gb=120.0,
    wsl_features_enabled=True)


def make(**kwargs):
    defaults = dict(runner=lambda argv: type("R", (), {
        "returncode": 0, "stdout": b"", "stderr": b""})(),
        facts=lambda: dict(HEALTHY_FACTS))
    return Wsl2Provider(**{**defaults, **kwargs})


def test_preflight_uses_gathered_facts():
    assert make().preflight().ok is True
    degraded = make(facts=lambda: {**HEALTHY_FACTS, "free_gb": 1.0})
    assert degraded.preflight().ok is False


def test_enable_features_remedy_runs_elevated_not_in_process():
    calls = []
    provider = make(elevator=lambda exe, args: calls.append((exe, args)) or 0)
    provider.apply_remedy("enable_wsl_features")
    assert calls == [("wsl.exe", ["--install", "--no-distribution"])]


def test_a_declined_uac_prompt_raises():
    # ShellExecuteW returns a non-zero exit code when the user says No.
    provider = make(elevator=lambda exe, args: 1223)
    with pytest.raises(RuntimeError, match="administrator"):
        provider.apply_remedy("enable_wsl_features")


def test_unknown_remedy_is_a_programming_error():
    with pytest.raises(ValueError, match="unknown remedy"):
        make().apply_remedy("make_coffee")


def test_reboot_is_required_only_after_features_were_enabled():
    provider = make(elevator=lambda exe, args: 0)
    assert provider.reboot_required() is False
    provider.apply_remedy("enable_wsl_features")
    assert provider.reboot_required() is True


def test_register_resume_writes_a_self_deleting_runonce_value():
    written = []
    provider = make(registry_writer=lambda key, name, value:
                    written.append((key, name, value)))
    provider.register_resume(r"C:\Apps\LocalRuntime\runtime.exe")
    assert written == [(RUNONCE_KEY, "LocalRuntimeSetup",
                        r'"C:\Apps\LocalRuntime\runtime.exe" setup --resume')]


def test_image_selection_follows_architecture():
    assert "amd64" in make(arch="amd64").image().url
    assert "arm64" in make(arch="arm64").image().url


def test_default_install_dir_is_importable_without_circular_import():
    # _default_facts measures disk space under default_install_dir(), not
    # sys.prefix; this only guards against the circular import that local
    # importing avoids, since disk measurement itself can't run on Linux.
    from runtime.providers import default_install_dir
    from runtime.providers.wsl2 import _default_facts
    assert callable(default_install_dir) and callable(_default_facts)
