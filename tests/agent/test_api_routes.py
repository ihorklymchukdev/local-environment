from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.api.app import create_app
from agent.core.config import AgentConfig
from agent.core.exec import Completed

PS_RUNNING = '[{"Service":"web","State":"running","ExitCode":0}]'
# NDJSON: docker compose emits one object per line on some versions.
PS_RESTARTING = ('{"Service":"web","State":"restarting","ExitCode":1}\n'
                 '{"Service":"db","State":"running","ExitCode":0}')

COMPOSE_ONE_WEB = """
services:
  web:
    image: nginx
    ports: ["8080:80"]
"""
COMPOSE_AMBIGUOUS = """
services:
  api:
    image: api
  worker:
    image: worker
"""


class FakeRunner:
    """Records argv and replays scripted results; never spawns a process."""

    def __init__(self):
        self.calls = []
        self.docker_version = Completed(0, "27.1.1", "")
        self.up = Completed(0, "", "")
        self.ps = Completed(0, PS_RUNNING, "")
        self.down = Completed(0, "", "")
        self.logs = Completed(0, "web-1 | listening on 80\n", "")
        self.stream_lines = ["web-1 | one\n", "web-1 | two\n"]

    def exec(self, argv, *, root=False):
        self.calls.append(argv)
        if argv[1] == "version":
            return self.docker_version
        if argv[-2:] == ["up", "-d"]:
            return self.up
        if "ps" in argv:
            return self.ps
        if "down" in argv:
            return self.down
        if "logs" in argv:
            return self.logs
        return Completed(0, "", "")

    def stream(self, argv, *, root=False):
        self.calls.append(argv)
        return iter(list(self.stream_lines))

    def argv_containing(self, needle):
        return [a for a in self.calls if needle in " ".join(a)]


@pytest.fixture
def env(tmp_path):
    config = AgentConfig(
        domain="test.local",
        edge_port=41080,
        projects_root=tmp_path / "projects",
        state_db=tmp_path / "state.db",
        version="9.9.9",
    )
    runner = FakeRunner()
    app = create_app(config=config, runner=runner)
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, config=config, runner=runner,
                              state=app.state.state, jobs=app.state.jobs)


def _create(env, pid="blog", **body):
    return env.client.post("/projects", json={"id": pid, **body})


def _write_compose(env, pid, text=COMPOSE_ONE_WEB):
    (env.config.projects_root / pid).mkdir(parents=True, exist_ok=True)
    (env.config.projects_root / pid / "docker-compose.yml").write_text(text)


def _run_to_completion(env, resp):
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]
    env.jobs.wait(job_id, timeout=5)
    return env.client.get(f"/jobs/{job_id}").json()


def test_importing_the_app_module_builds_nothing(env):
    # A module-level app would open sqlite under /opt/omelet at import time and
    # drag the whole suite onto the real filesystem.
    import agent.api.app as module
    assert not [name for name, value in vars(module).items()
                if isinstance(value, FastAPI)]


def test_missing_project_returns_a_structured_404(env):
    resp = env.client.get("/projects/nope")
    assert resp.status_code == 404
    assert resp.json() == {"error": {"code": "project_not_found",
                                     "message": "no project with id 'nope'"}}


def test_unknown_job_returns_a_structured_404(env):
    resp = env.client.get("/jobs/deadbeef")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "job_not_found"


def test_framework_errors_use_the_same_error_body(env):
    # The host client parses one shape; a route or the framework inventing a
    # second one breaks it.
    unknown = env.client.get("/no-such-route")
    assert unknown.status_code == 404
    assert set(unknown.json()["error"]) == {"code", "message"}

    invalid = env.client.post("/projects", json={})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "invalid_request"


def test_creating_the_same_project_twice_conflicts(env):
    assert _create(env).status_code == 201
    resp = _create(env)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "project_exists"


def test_up_returns_a_job_id_and_runs_compose_with_both_files(env):
    _create(env)
    _write_compose(env, "blog")
    job = _run_to_completion(env, env.client.post("/projects/blog/up"))

    assert job["state"] == "done"
    assert job["result"]["status"] == "started_ok"
    assert env.client.get("/projects/blog").json()["status"] == "started_ok"

    up = env.runner.argv_containing("up")[-1]
    assert up.count("-f") == 2 and up[-2:] == ["up", "-d"]
    ps = env.runner.argv_containing("ps")[-1]
    assert ps.count("-f") == 1, "compose ps runs against the base file only"


def test_up_without_a_compose_file_is_compose_missing(env):
    _create(env)
    resp = env.client.post("/projects/blog/up")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "compose_missing"


def test_up_on_an_ambiguous_compose_carries_the_detector_message(env):
    _create(env)
    _write_compose(env, "blog", COMPOSE_AMBIGUOUS)
    resp = env.client.post("/projects/blog/up")
    assert resp.status_code == 422
    body = resp.json()["error"]
    assert body["code"] == "invalid_project"
    assert "declare `web:`" in body["message"]


def test_a_failed_compose_up_fails_the_job_with_the_guests_own_stderr(env):
    _create(env)
    _write_compose(env, "blog")
    env.runner.up = Completed(1, "", "network edge declared as external, but could not be found")

    job = _run_to_completion(env, env.client.post("/projects/blog/up"))
    assert job["state"] == "failed"
    assert "network edge" in job["detail"]
    assert env.client.get("/projects/blog").json()["status"] == "failed_to_start"


def test_ndjson_ps_output_still_classifies_a_crash_loop(env):
    _create(env)
    _write_compose(env, "blog")
    env.runner.ps = Completed(0, PS_RESTARTING, "")

    job = _run_to_completion(env, env.client.post("/projects/blog/up"))
    assert job["result"]["status"] == "crash_looping"
    assert job["state"] == "failed"
    assert job["detail"], "a crash loop must say something actionable"
    assert env.client.get("/projects/blog").json()["status"] == "crash_looping"


def test_urls_come_from_the_configured_domain_and_edge_port(env):
    _create(env)
    _write_compose(env, "blog")
    listed = env.client.get("/projects").json()["projects"]
    assert listed[0]["urls"] == ["http://blog.test.local:41080"]


def test_explicit_web_override_beats_detection(env):
    _create(env, web=[{"service": "api", "port": 8000}])
    _write_compose(env, "blog", COMPOSE_AMBIGUOUS)
    proj = env.client.get("/projects/blog").json()
    assert proj["urls"] == ["http://blog.test.local:41080"]

    job = _run_to_completion(env, env.client.post("/projects/blog/up"))
    assert job["state"] == "done"


def test_listing_tolerates_a_project_whose_compose_cannot_be_read(env):
    # Status must stay readable even when the project's files are broken.
    _create(env)
    _write_compose(env, "blog", COMPOSE_AMBIGUOUS)
    proj = env.client.get("/projects/blog").json()
    assert proj["urls"] == []
    assert proj["status"] == "stopped"


def test_down_stops_the_stack_and_records_stopped(env):
    _create(env)
    _write_compose(env, "blog")
    _run_to_completion(env, env.client.post("/projects/blog/up"))

    job = _run_to_completion(env, env.client.post("/projects/blog/down"))
    assert job["state"] == "done"
    assert env.client.get("/projects/blog").json()["status"] == "stopped"


def test_delete_stops_the_containers_and_forgets_the_project(env):
    _create(env)
    _write_compose(env, "blog")
    assert env.client.delete("/projects/blog").status_code == 200
    assert env.runner.argv_containing("down"), "delete must stop the containers"
    assert env.client.get("/projects/blog").status_code == 404


def test_project_logs_return_compose_output_and_follow_streams(env):
    _create(env)
    _write_compose(env, "blog")

    plain = env.client.get("/projects/blog/logs")
    assert plain.text == "web-1 | listening on 80\n"

    followed = env.client.get("/projects/blog/logs", params={"follow": True})
    assert followed.text == "web-1 | one\nweb-1 | two\n"
    assert any("--follow" in a for a in env.runner.argv_containing("logs"))


def test_job_logs_are_readable_over_http(env):
    _create(env)
    _write_compose(env, "blog")
    resp = env.client.post("/projects/blog/up")
    job_id = resp.json()["job_id"]
    env.jobs.wait(job_id, timeout=5)
    assert "compose up" in env.client.get(f"/jobs/{job_id}/logs").text


def test_health_answers_even_when_docker_is_unreachable(env):
    env.runner.docker_version = Completed(1, "", "Cannot connect to the Docker daemon")
    body = env.client.get("/health").json()
    assert body["status"] == "ok"
    assert body["version"] == "9.9.9"
    assert body["docker"]["reachable"] is False
    assert "Cannot connect" in body["docker"]["detail"]


def test_version_reports_the_configured_version(env):
    assert env.client.get("/version").json() == {"version": "9.9.9"}
