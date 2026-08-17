import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    # runtime.providers.default_install_dir() resolves under the real home
    # directory (or LOCALAPPDATA on Windows). Without this, CLI tests that
    # exercise `setup`/`uninstall` would read and write real state files
    # under the developer's actual home directory instead of a throwaway one.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
