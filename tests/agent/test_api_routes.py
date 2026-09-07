import threading
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.api.app import create_app
from agent.core.config import AgentConfig
from agent.core.exec import Completed
from agent.core.state import State

PS_RUNNING = '[{"Service":"web","State":"running","ExitCode":0}]'
# One LISTEN row (st 0A) on 127.0.0.1:80, the shape `cat /proc/net/tcp` prints.
PROC_NET_LOOPBACK = (
    "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when\n"
    "   0: 0100007F:0050 00000000:0000 0A 00000000:00000000 00:00000000\n")
# NDJSON: docker compose emits one object per line on some versions.
PS_RESTARTING = ('{"Service":"web","State":"restarting","ExitCode":1}\n'
                 '{"Service":"db","State":"running","ExitCode":0}')

COMPOSE_ONE_WEB = """
services:
  web:
    image: nginx
    ports: ["8080:80"]
"""
COMPOSE_MALFORMED = "services:\n  web:\n   image: nginx\n    ports: bad\n"
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
        self.container_id = Completed(0, "c0ffee1234\n", "")
        self.proc_net = Completed(0, PROC_NET_LOOPBACK, "")
        self.up_gate = None

    def exec(self, argv, *, root=False):
        self.calls.append(argv)
        if argv[1] == "version":
            return self._reply(self.docker_version)
        if argv[1] == "exec":
            return self.proc_net
        if "-q" in argv:
            return self.container_id
        if argv[-2:] == ["up", "-d"]:
            if self.up_gate is not None:
                assert self.up_gate.wait(5), "the up job was never released"
            return self.up
        if "ps" in argv:
            return self.ps
        if "down" in argv:
            return self.down
        if "logs" in argv:
            return self.logs
        return Completed(0, "", "")

    @staticmethod
    def _reply(scripted):
        if isinstance(scripted, Exception):
            raise scripted
        return scripted

    def stream(self, argv, *, root=False):
        self.calls.append(argv)
        return iter(list(self.stream_lines))

    def argv_containing(self, needle):
        return [a for a in self.calls if needle in " ".join(a)]


class FakeProbe:
    """Answers the health probe without a socket. 200 by default, so an
    ordinary `up` in these tests never enters the retry window."""

    def __init__(self):
        self.status = 200
        self.calls = []

    def __call__(self, url, host):
        self.calls.append((url, host))
        return self.status


AUTH = {"Authorization": "Bearer test-token"}


@pytest.fixture
def env(tmp_path):
    token_path = tmp_path / "agent.token"
    token_path.write_text("test-token")
    config = AgentConfig(
        domain="test.local",
        edge_port=41080,
        projects_root=tmp_path / "projects",
        state_db=tmp_path / "state.db",
        version="9.9.9",
        token_path=token_path,
        # No retry window: these tests assert on the verdict, and the window
        # itself is covered against a fake clock in test_health.py.
        ready_timeout=0.0,
    )
    runner = FakeRunner()
    probe = FakeProbe()
    app = create_app(config=config, runner=runner, http_probe=probe)
    with TestClient(app, headers=AUTH) as client:
        # raw_client returns the 500 a real caller would see instead of
        # re-raising the exception inside the test.
        yield SimpleNamespace(client=client, config=config, runner=runner,
                              probe=probe, state=app.state.state, jobs=app.state.jobs,
                              raw_client=TestClient(app, raise_server_exceptions=False,
                                                    headers=AUTH))


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
                if isinstance(value, (FastAPI, State))]


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


def test_an_unexpected_failure_still_answers_the_one_error_shape(env):
    env.runner.docker_version = RuntimeError("the runner exploded")
    resp = env.raw_client.get("/health")
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "internal_error"
    assert "exploded" not in resp.text, "an internal message must not leak out"


def test_a_malformed_compose_file_is_a_4xx_not_a_500(env):
    # Uploading a broken compose file is the most ordinary thing a user does.
    _create(env)
    _write_compose(env, "blog", COMPOSE_MALFORMED)

    up = env.raw_client.post("/projects/blog/up")
    assert up.status_code == 422
    assert up.json()["error"]["code"] == "invalid_compose"
    assert "line 4" in up.json()["error"]["message"], "the parser must locate it"

    one = env.raw_client.get("/projects/blog")
    assert one.status_code == 200
    assert one.json()["problem"]["code"] == "invalid_compose"


def test_one_broken_project_does_not_take_the_listing_down(env):
    _create(env, "blog")
    _write_compose(env, "blog")
    _create(env, "broken")
    _write_compose(env, "broken", COMPOSE_MALFORMED)

    listed = env.raw_client.get("/projects")
    assert listed.status_code == 200
    by_id = {p["id"]: p for p in listed.json()["projects"]}
    assert by_id["blog"]["urls"] == ["http://blog.test.local:41080"]
    assert by_id["blog"]["problem"] is None
    assert by_id["broken"]["problem"]["code"] == "invalid_compose"


def test_a_second_lifecycle_operation_on_a_busy_project_is_refused(env):
    _create(env)
    _write_compose(env, "blog")
    env.runner.up_gate = threading.Event()

    first = env.client.post("/projects/blog/up")
    assert first.status_code == 202

    for resp in (env.client.post("/projects/blog/up"),
                 env.client.post("/projects/blog/down"),
                 env.client.delete("/projects/blog")):
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "project_busy"

    env.runner.up_gate.set()
    env.jobs.wait(first.json()["job_id"], timeout=5)
    # The lock is released with the job, not leaked.
    assert env.client.post("/projects/blog/down").status_code == 202


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

    # Compose exits non-zero when the project was never created; an empty 200
    # would hide the reason.
    env.runner.logs = Completed(1, "", "no configuration file provided")
    failed = env.client.get("/projects/blog/logs")
    assert failed.status_code == 409
    assert failed.json()["error"]["code"] == "logs_unavailable"
    assert "no configuration file" in failed.json()["error"]["message"]

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


def test_a_started_project_traefik_cannot_reach_reports_a_problem(env):
    # The containers stayed up, so the job succeeds and the URL is printed --
    # without this the user gets a working-looking URL that answers a proxy
    # error, and nothing anywhere says why.
    _create(env)
    _write_compose(env, "blog")
    env.probe.status = 502

    job = _run_to_completion(env, env.client.post("/projects/blog/up"))
    assert job["state"] == "done"

    body = env.client.get("/projects/blog").json()
    assert body["status"] == "started_ok"
    assert body["problem"]["code"] == "bound_to_loopback"
    assert "0.0.0.0" in body["problem"]["message"]
    assert env.probe.calls[0] == ("http://traefik:41080/", "blog.test.local")


def test_a_fixed_project_clears_its_problem_on_the_next_up(env):
    _create(env)
    _write_compose(env, "blog")
    env.probe.status = 502
    _run_to_completion(env, env.client.post("/projects/blog/up"))
    assert env.client.get("/projects/blog").json()["problem"] is not None

    env.probe.status = 200
    _run_to_completion(env, env.client.post("/projects/blog/up"))
    assert env.client.get("/projects/blog").json()["problem"] is None


def test_a_broken_compose_file_outranks_a_routing_problem(env):
    # Both can be true at once; the one the user has to fix first wins.
    _create(env)
    _write_compose(env, "blog")
    env.probe.status = 502
    _run_to_completion(env, env.client.post("/projects/blog/up"))
    _write_compose(env, "blog", COMPOSE_MALFORMED)

    assert env.raw_client.get("/projects/blog").json()["problem"]["code"] == \
        "invalid_compose"


def test_a_stored_problem_clears_when_the_project_answers_on_a_re_read(env):
    # An entrypoint slower than the readiness window stores a diagnosis that is
    # true for a minute and false for as long as the project lives afterwards.
    _create(env)
    _write_compose(env, "blog")
    env.probe.status = 502
    _run_to_completion(env, env.client.post("/projects/blog/up"))
    assert env.state.get_project("blog")["problem_code"] == "bound_to_loopback"

    env.probe.status = 200
    assert env.client.get("/projects/blog").json()["problem"] is None
    assert env.state.get_project("blog")["problem_code"] is None, \
        "the stale row must be cleared, not just hidden from one response"


def test_a_stored_problem_survives_a_re_read_that_still_fails(env):
    _create(env)
    _write_compose(env, "blog")
    env.probe.status = 502
    _run_to_completion(env, env.client.post("/projects/blog/up"))

    body = env.client.get("/projects/blog").json()
    assert body["problem"]["code"] == "bound_to_loopback"


def test_the_project_listing_never_probes(env):
    # One round trip per project would make `omelet status` slow in proportion
    # to how much the tool is used.
    _create(env)
    _write_compose(env, "blog")
    env.probe.status = 502
    _run_to_completion(env, env.client.post("/projects/blog/up"))
    env.probe.calls.clear()

    listed = env.client.get("/projects").json()["projects"]
    assert listed[0]["problem"]["code"] == "bound_to_loopback"
    assert env.probe.calls == []
