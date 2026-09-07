import pytest

from host.client import AgentUnavailableError, read_token
from host.core.provider import Completed


class FakeProvider:
    def __init__(self, result: Completed):
        self._result = result
        self.execs = []

    def exec(self, argv, *, root=False):
        self.execs.append((argv, root))
        return self._result


def test_read_token_reads_as_root_from_the_token_path_and_strips_it():
    provider = FakeProvider(Completed(0, "sekret\n", ""))
    assert read_token(provider) == "sekret"
    (argv, root), = provider.execs
    assert argv == ["cat", "/opt/omelet/agent.token"]
    assert root is True


def test_read_token_raises_when_the_guest_command_fails():
    # A missing file, or the VM not existing at all, must not read as an
    # empty-but-valid token.
    provider = FakeProvider(Completed(1, "", "No such file or directory"))
    with pytest.raises(AgentUnavailableError):
        read_token(provider)


def test_read_token_raises_on_an_empty_token_even_when_the_command_succeeds():
    # A zero-length token file (the agent's own unconfigured state) must not
    # be treated as a usable credential either.
    provider = FakeProvider(Completed(0, "", ""))
    with pytest.raises(AgentUnavailableError):
        read_token(provider)


# ---------------------------------------------------------------------------
# The HTTP client, against a fake opener. Nothing here touches the network.
# ---------------------------------------------------------------------------

import email.message
import io
import json
import tarfile
import urllib.error

from host.client import (AgentClient, AgentError, JobFailedError,
                         JobTimeoutError, project_id_for)


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200):
        super().__init__(body)
        self.status = status


def http_error(status: int, code: str, message: str) -> urllib.error.HTTPError:
    body = json.dumps({"error": {"code": code, "message": message}}).encode()
    return urllib.error.HTTPError("http://agent/x", status, "reason",
                                  email.message.Message(), io.BytesIO(body))


class Call:
    def __init__(self, request, timeout):
        self.method = request.get_method()
        self.url = request.full_url
        self.path = request.full_url.split("39099", 1)[-1]
        self.headers = {k.lower(): v for k, v in request.header_items()}
        self.data = request.data
        # Read eagerly, the way urllib itself consumes a file-object body:
        # the client closes its temp file as soon as the call returns.
        self.body = (self.data.read() if hasattr(self.data, "read")
                     else self.data)
        self.timeout = timeout

    def json(self):
        return json.loads(self.body.decode())


class FakeOpener:
    """Stands in for urllib.request.OpenerDirector. `handler` maps a Call to
    the response body (a dict, str or bytes) or to an exception to raise."""

    def __init__(self, handler):
        self._handler = handler
        self.calls: list[Call] = []

    def open(self, request, timeout=None):
        call = Call(request, timeout)
        self.calls.append(call)
        result = self._handler(call)
        if isinstance(result, BaseException):
            raise result
        if isinstance(result, (dict, list)):
            return FakeResponse(json.dumps(result).encode())
        if isinstance(result, str):
            return FakeResponse(result.encode())
        return FakeResponse(result or b"")


class Clock:
    """Deterministic time for the poll loops; records every sleep so a test
    can prove the client is not spinning."""

    def __init__(self):
        self.now = 0.0
        self.slept: list[float] = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def client(handler, clock: Clock | None = None) -> tuple[AgentClient, FakeOpener]:
    opener = FakeOpener(handler)
    clock = clock or Clock()
    return (AgentClient("sekret", opener=opener, sleep=clock.sleep,
                        monotonic=clock.monotonic),
            opener)


def test_every_request_carries_the_bearer_token_and_a_timeout():
    # Without the header the agent answers 401; without a timeout the CLI
    # hangs forever on a wedged VM.
    c, opener = client(lambda call: {"projects": []})
    c.list_projects()
    call, = opener.calls
    assert call.headers["authorization"] == "Bearer sekret"
    assert call.timeout is not None and call.timeout > 0


def test_an_error_response_reports_the_agents_own_sentence():
    c, _ = client(lambda call: http_error(404, "project_not_found",
                                          "no project with id 'blog'"))
    try:
        c.get_project("blog")
        raise AssertionError("expected AgentError")
    except AgentError as e:
        assert e.code == "project_not_found"
        assert e.status == 404
        assert "no project with id 'blog'" in str(e)
        assert "HTTP Error" not in str(e)


def test_an_error_body_that_is_not_the_agents_shape_still_reads_as_a_sentence():
    # A proxy or a crashed server can answer HTML; the client must not raise
    # a JSONDecodeError over the failure it was reporting.
    bad = urllib.error.HTTPError("http://agent/x", 502, "Bad Gateway",
                                 email.message.Message(),
                                 io.BytesIO(b"<html>nope</html>"))
    c, _ = client(lambda call: bad)
    try:
        c.list_projects()
        raise AssertionError("expected AgentError")
    except AgentError as e:
        assert e.status == 502
        assert str(e).strip()


def test_a_refused_connection_says_the_vm_is_not_running():
    c, _ = client(lambda call: urllib.error.URLError(
        ConnectionRefusedError(111, "Connection refused")))
    try:
        c.list_projects()
        raise AssertionError("expected AgentUnavailableError")
    except AgentUnavailableError as e:
        assert "VM" in str(e)


def test_wait_for_job_polls_until_it_finishes_and_returns_the_result():
    states = [
        {"job_id": "j1", "state": "running", "detail": "", "result": None},
        {"job_id": "j1", "state": "running", "detail": "", "result": None},
        {"job_id": "j1", "state": "done", "detail": "",
         "result": {"status": "started_ok", "urls": ["http://blog.x:39080"]}},
    ]
    clock = Clock()
    c, opener = client(lambda call: states.pop(0), clock)
    job = c.wait_for_job("j1")
    assert job["result"]["urls"] == ["http://blog.x:39080"]
    assert len(opener.calls) == 3
    # Two waits between three polls: a poll loop with no sleep is a spin.
    assert len(clock.slept) == 2 and all(s > 0 for s in clock.slept)


def test_a_failed_job_carries_the_guests_own_stderr_and_the_status_it_reached():
    failed = {"job_id": "j1", "state": "failed",
              "detail": "web exited with code 1: cannot bind port",
              "result": {"status": "crash_looping", "urls": []}}
    c, _ = client(lambda call: failed)
    try:
        c.wait_for_job("j1")
        raise AssertionError("expected JobFailedError")
    except JobFailedError as e:
        assert "cannot bind port" in str(e)
        assert e.result["status"] == "crash_looping"


def test_wait_for_job_gives_up_at_its_deadline():
    running = {"job_id": "j1", "state": "running", "detail": "", "result": None}
    clock = Clock()
    c, _ = client(lambda call: running, clock)
    try:
        c.wait_for_job("j1", timeout=2.0)
        raise AssertionError("expected JobTimeoutError")
    except JobTimeoutError as e:
        assert "j1" in str(e)


def test_a_busy_project_is_retried_rather_than_reported_as_a_failure():
    answers = [http_error(409, "project_busy", "another operation is running"),
               http_error(409, "project_busy", "another operation is running"),
               {"job_id": "j7"}]
    clock = Clock()
    c, _ = client(lambda call: answers.pop(0), clock)
    assert c.project_up("blog") == "j7"
    assert clock.slept, "a busy project must be retried after a wait"


def test_a_project_that_stays_busy_is_finally_reported():
    clock = Clock()
    c, _ = client(lambda call: http_error(409, "project_busy", "still running"),
                  clock)
    try:
        c.project_up("blog")
        raise AssertionError("expected AgentError")
    except AgentError as e:
        assert e.code == "project_busy"


def test_upload_directory_sends_a_tar_gz_of_the_directory_contents(tmp_path):
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "index.html").write_text("hi")

    c, opener = client(lambda call: {"id": "blog", "files": []})
    c.upload_directory("blog", tmp_path)
    call, = opener.calls
    assert call.method == "POST" and call.path == "/projects/blog/files"
    assert call.headers["content-type"] == "application/gzip"
    assert int(call.headers["content-length"]) > 0

    with tarfile.open(fileobj=io.BytesIO(call.body), mode="r:gz") as tar:
        names = sorted(tar.getnames())
    # Contents at the archive root, not nested under the local folder name:
    # the agent extracts straight into the project directory.
    assert "docker-compose.yml" in names and "app/index.html" in names


def test_ensure_project_tolerates_one_that_already_exists():
    seen = []

    def handler(call):
        seen.append((call.method, call.path))
        if call.method == "POST":
            return http_error(409, "project_exists", "project 'blog' already exists")
        return {"id": "blog", "status": "stopped", "urls": [], "problem": None}

    c, _ = client(handler)
    assert c.ensure_project("blog")["id"] == "blog"
    assert seen == [("POST", "/projects"), ("GET", "/projects/blog")]


def test_project_id_matches_the_rule_the_agent_slugs_with():
    from agent.core.project import _slug
    for name in ("My Blog", "blog", "  Spaced Out  ", "a_b.c", "UPPER"):
        assert project_id_for(name) == _slug(name)
