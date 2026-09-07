from host.providers.wsl_checks import parse_wsl_version, preflight_checks

# Captured from a real `wsl --version` on Windows 11.
REAL_WSL_VERSION = """WSL version: 2.3.26.0
Kernel version: 5.15.167.4-1
WSLg version: 1.0.65
MSRDC version: 1.2.5620
Direct3D version: 1.611.1-81528511
DXCore version: 10.0.26100.1-240331-1435.ge-release
Windows version: 10.0.26100.2314"""

HEALTHY = dict(wsl_version_text=REAL_WSL_VERSION, build=26100,
               hypervisor_present=True, firmware_virtualization=True,
               free_gb=120.0, wsl_features_enabled=True)


def test_parses_a_real_wsl_version_banner():
    assert parse_wsl_version(REAL_WSL_VERSION) == (2, 3, 26, 0)


def test_returns_none_for_inbox_wsl_which_has_no_version_command():
    # Old in-box WSL prints usage text to stderr instead of a version.
    assert parse_wsl_version("Invalid command line option: --version") is None


def test_a_healthy_host_has_no_blocking_checks():
    assert preflight_checks(**HEALTHY).ok is True


def test_firmware_virtualization_off_is_a_dead_end():
    diag = preflight_checks(**{**HEALTHY, "hypervisor_present": False,
                               "firmware_virtualization": False})
    labels = [c.label for c in diag.dead_ends]
    assert any("virtualization" in l.lower() for l in labels)
    bios = next(c for c in diag.dead_ends if "virtualization" in c.label.lower())
    assert "BIOS" in bios.fix or "UEFI" in bios.fix


def test_hypervisor_running_counts_as_virtualization_available():
    # Once WSL2/Hyper-V is running, firmware flags can read False; the
    # hypervisor being present is proof enough.
    diag = preflight_checks(**{**HEALTHY, "firmware_virtualization": False,
                               "hypervisor_present": True})
    assert diag.ok is True


def test_missing_store_wsl_is_fixable_not_a_dead_end():
    diag = preflight_checks(**{**HEALTHY, "wsl_version_text": ""})
    assert [c.remedy for c in diag.fixable] == ["update_wsl"]
    assert diag.dead_ends == []


def test_old_windows_build_is_a_dead_end():
    diag = preflight_checks(**{**HEALTHY, "build": 18363})
    assert any("Windows" in c.label for c in diag.dead_ends)


def test_low_disk_space_is_a_dead_end():
    diag = preflight_checks(**{**HEALTHY, "free_gb": 3.2})
    assert any("disk" in c.label.lower() for c in diag.dead_ends)


def test_wsl_features_disabled_is_fixable_not_a_dead_end():
    # This is the case that proves the auto-fix/reboot path is reachable:
    # a missing Windows feature must route through apply_remedy, not a
    # BIOS-style dead end no code can act on.
    diag = preflight_checks(**{**HEALTHY, "wsl_features_enabled": False})
    assert [c.remedy for c in diag.fixable] == ["enable_wsl_features"]
    assert diag.dead_ends == []
