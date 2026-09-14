import io
import os
import urllib.error

import pytest

from tests.engine.cli.loader import load

cli = load()


class _Refused:
    def open(self, request, timeout=None):
        raise urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))


def test_a_stopped_service_is_named_with_the_command_that_starts_it(tmp_path):
    root = tmp_path / "projects"
    (root / "blog").mkdir(parents=True)
    out, err = io.StringIO(), io.StringIO()
    env = cli.Env(root=root, cwd=root / "blog",
                  agent=lambda: cli.Agent("t", opener=_Refused()),
                  out=out, err=err)
    assert cli.main(["status"], env) == 1
    assert "not answering" in err.getvalue()
    assert cli.START_STACK in err.getvalue()


def test_a_vm_without_a_token_says_omelet_is_not_set_up(tmp_path):
    with pytest.raises(cli.OmeletError, match="not set up"):
        cli.read_token(tmp_path / "agent.token")


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read any file")
def test_an_unreadable_token_points_at_the_docker_group(tmp_path):
    token = tmp_path / "agent.token"
    token.write_text("secret")
    token.chmod(0)
    with pytest.raises(cli.OmeletError, match="docker group"):
        cli.read_token(token)
