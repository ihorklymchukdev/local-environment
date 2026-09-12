import io
import os
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.api.app import create_app
from agent.core.config import AgentConfig
from tests.agent.test_api_routes import FakeProbe, FakeRunner
from tests.guest.loader import load
from tests.host.test_client_seam import TOKEN, AppOpener

cli = load()


class Guest:
    """The guest CLI wired to the real agent app, in-process, over the fake
    Docker runner -- the same seam tests/host/test_client_seam.py uses."""

    def __init__(self, root: Path, client: TestClient, runner: FakeRunner):
        self.root = root
        self.runner = runner
        self._client = client
        self.git_calls: list = []
        self.git_result: tuple[int, str] = (0, "")
        self.clone_files: dict[str, str] = {}

    def _git(self, argv, env):
        self.git_calls.append((argv, env))
        code, stderr = self.git_result
        if code == 0:
            target = Path(argv[-1])
            target.mkdir()
            for name, text in self.clone_files.items():
                (target / name).write_text(text)
        return subprocess.CompletedProcess(argv, code, "", stderr)

    def _agent(self):
        return cli.Agent(TOKEN, opener=AppOpener(self._client),
                         sleep=lambda _s: time.sleep(0.01))

    def run(self, *argv, cwd: Path) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        env = cli.Env(root=self.root, cwd=cwd, agent=self._agent,
                      gid=os.getgid, git=self._git, out=out, err=err)
        code = cli.main(list(argv), env)
        return code, out.getvalue(), err.getvalue()


@pytest.fixture
def guest(tmp_path):
    (tmp_path / "agent.token").write_text(TOKEN)
    root = tmp_path / "projects"
    root.mkdir()
    config = AgentConfig(domain="test.local", edge_port=41080,
                         projects_root=root, state_db=tmp_path / "state.db",
                         token_path=tmp_path / "agent.token", ready_timeout=0.0)
    runner = FakeRunner()
    app = create_app(config=config, runner=runner, http_probe=FakeProbe())
    with TestClient(app) as client:
        yield Guest(root, client, runner)
