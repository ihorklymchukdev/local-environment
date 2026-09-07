from __future__ import annotations

import logging
import os
import secrets
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import (FileResponse, JSONResponse, PlainTextResponse,
                               StreamingResponse)
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..core import files, lifecycle
from ..core.config import AgentConfig
from ..core.detect import AmbiguousError
from ..core.exec import LocalRunner
# Imported by name: the /health route below shadows a module named `health`.
from ..core.health import default_probe, diagnose
from ..core.overlay import host_for
from ..core.project import STARTED_OK, Project, _slug, load_project
from ..core.state import State
from .jobs import JobFailed, JobRegistry

TEXT = "text/plain; charset=utf-8"
log = logging.getLogger("omelet.agent")


class ApiError(Exception):
    """The only way this API reports a failure. One handler turns it into the
    single error body the host client parses."""

    def __init__(self, code: str, message: str, status: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class ThreadLocalState:
    """`State` opens one sqlite connection, and sqlite3 refuses a connection
    used from a thread other than the one that opened it. FastAPI runs sync
    routes in a threadpool and jobs run on their own threads, so each thread
    gets its own `State` over the same file."""

    def __init__(self, db_path):
        self._db_path = db_path
        self._local = threading.local()
        self._bound()  # fail here, at startup, if the file is unusable

    def _bound(self) -> State:
        state = getattr(self._local, "state", None)
        if state is None:
            state = State(self._db_path)
            self._local.state = state
        return state

    def __getattr__(self, name):
        return getattr(self._bound(), name)


def _busy(project_id: str) -> "ApiError":
    return ApiError("project_busy",
                    f"another operation on '{project_id}' is still running", 409)


class ProjectLocks:
    """One lifecycle operation per project at a time. Non-blocking on purpose:
    two `up` jobs would race on the same `.omelet/overlay.yml`, and a blocking
    lock would only move a multi-minute hold onto whoever waits."""

    def __init__(self):
        self._lock = threading.Lock()
        self._held: set[str] = set()

    def acquire(self, project_id: str) -> bool:
        with self._lock:
            if project_id in self._held:
                return False
            self._held.add(project_id)
            return True

    def release(self, project_id: str) -> None:
        with self._lock:
            self._held.discard(project_id)

    @contextmanager
    def held(self, project_id: str):
        if not self.acquire(project_id):
            raise _busy(project_id)
        try:
            yield
        finally:
            self.release(project_id)


class WebOverride(BaseModel):
    service: str
    port: int
    subdomain: str | None = None


class CreateProject(BaseModel):
    id: str
    web: list[WebOverride] | None = None
    domain: str | None = None


def _body(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}},
                        status_code=status)


def _validation_message(exc: RequestValidationError) -> str:
    first = (exc.errors() or [{}])[0]
    where = ".".join(str(p) for p in first.get("loc", ())[1:])
    return f"{where}: {first.get('msg', 'invalid request body')}".lstrip(": ")


def _read_token(path: Path) -> str:
    """Empty string for "missing", "unreadable", and "unparseable" alike --
    callers only need to know whether they have a credential to compare
    against, and this must fail closed on anything unexpected rather than
    crash-loop the agent."""
    try:
        return path.read_text().strip()
    except (OSError, UnicodeDecodeError):
        return ""


def create_app(*, config: AgentConfig | None = None, runner=None, state=None,
               jobs: JobRegistry | None = None, http_probe=None) -> FastAPI:
    config = config or AgentConfig.from_env()
    runner = runner or LocalRunner()
    http_probe = http_probe or default_probe
    state = state if state is not None else ThreadLocalState(config.state_db)
    jobs = jobs or JobRegistry()
    locks = ProjectLocks()

    app = FastAPI(title="omelet-agent", version=config.version)
    app.state.config = config
    app.state.runner = runner
    app.state.state = state
    app.state.jobs = jobs

    @app.exception_handler(ApiError)
    async def _api_error(_request, exc: ApiError):
        return _body(exc.code, exc.message, exc.status)

    @app.exception_handler(RequestValidationError)
    async def _invalid_request(_request, exc: RequestValidationError):
        return _body("invalid_request", _validation_message(exc), 422)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(
            exc.status_code, "http_error")
        return _body(code, str(exc.detail), exc.status_code)

    @app.exception_handler(Exception)
    async def _unexpected(_request, exc: Exception):
        # The traceback goes to the agent's log, never into the response: the
        # host client only needs a code it can act on.
        log.exception("unhandled error serving a request")
        return _body("internal_error",
                     f"the agent failed with an unexpected {type(exc).__name__}", 500)

    # Read once at startup, not per request. The agent binds 0.0.0.0 inside
    # the VM (WSL2's localhostForwarding needs that), so every container in
    # the VM can otherwise reach an agent holding the Docker socket. A missing
    # or empty token file must close every authenticated route, never open
    # one -- Phase 3 replaces this shared, VM-wide token with a service-issued
    # device token per host.
    token = _read_token(config.token_path)

    @app.middleware("http")
    async def _require_bearer_token(request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        if not token:
            return _body("agent_unconfigured",
                         "the agent has no token configured; run setup again", 503)
        scheme, _, supplied = request.headers.get("authorization", "").partition(" ")
        # Starlette decodes headers as latin-1, so a header value can carry
        # bytes that are not valid ASCII; compare_digest raises TypeError on
        # two `str` args if either has a non-ASCII character. Comparing the
        # encoded bytes instead means every wire-valid header reaches a
        # normal true/false answer, never an exception out of the one guard
        # that must never throw.
        match = (scheme.lower() == "bearer"
                and secrets.compare_digest(supplied.encode(), token.encode()))
        if not match:
            return _body("unauthorized", "missing or invalid bearer token", 401)
        return await call_next(request)

    def project_dir(project_id: str) -> Path:
        return Path(config.projects_root) / project_id

    def require_row(project_id: str) -> dict:
        row = state.get_project(project_id)
        if row is None:
            raise ApiError("project_not_found",
                           f"no project with id '{project_id}'", 404)
        return row

    def require_job(job_id: str):
        job = jobs.get(job_id)
        if job is None:
            raise ApiError("job_not_found", f"no job with id '{job_id}'", 404)
        return job

    def parse_yaml(path: Path) -> dict:
        try:
            data = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError as e:
            # The parser already says where the mistake is; keep it on one line.
            raise ApiError("invalid_compose",
                           f"{path.name} is not valid YAML: {' '.join(str(e).split())}",
                           422) from e
        if not isinstance(data, dict):
            raise ApiError("invalid_compose",
                           f"{path.name} must be a mapping, not a "
                           f"{type(data).__name__}", 422)
        return data

    def load(project_id: str) -> Project:
        d = project_dir(project_id)
        compose_path = d / "docker-compose.yml"
        if not compose_path.exists():
            raise ApiError("compose_missing",
                           f"project '{project_id}' has no docker-compose.yml", 400)
        project_yml = d / ".omelet" / "project.yml"
        overrides = parse_yaml(project_yml) if project_yml.exists() else None
        try:
            return load_project(parse_yaml(compose_path), overrides, project_id)
        except AmbiguousError as e:
            # The detector's message is already written for a human.
            raise ApiError("invalid_project", str(e), 422) from e
        except (AttributeError, KeyError, TypeError, ValueError) as e:
            raise ApiError("invalid_project",
                           f"the project definition cannot be read: {e}", 422) from e

    def urls_for(project: Project, domain: str) -> list[str]:
        return [f"http://{host_for(project.id, web, domain)}:{config.edge_port}"
                for web in project.webs]

    def payload(row: dict) -> dict:
        # A project with broken or missing files still has a status, and one
        # broken project must never take the whole listing down with it.
        problem = None
        urls: list[str] = []
        try:
            urls = urls_for(load(row["id"]), row["domain"])
        except ApiError as e:
            problem = {"code": e.code, "message": e.message}
        if problem is None and row.get("problem_code"):
            # A file that will not parse outranks a routing fault: it is why
            # the project has no URLs to be unreachable on.
            problem = {"code": row["problem_code"],
                       "message": row["problem_message"]}
        return {"id": row["id"], "status": row["status"], "domain": row["domain"],
                "path": row["guest_path"], "urls": urls, "problem": problem}

    def submit_locked(project_id: str, work) -> str:
        """The job releases the lock itself, in its own `finally`."""
        if not locks.acquire(project_id):
            raise _busy(project_id)
        try:
            return jobs.submit(work)
        except BaseException:
            locks.release(project_id)
            raise

    @app.get("/health")
    def health() -> dict:
        probe = runner.exec([lifecycle.DOCKER, "version", "--format",
                             "{{.Server.Version}}"])
        return {
            "status": "ok",
            "version": config.version,
            "docker": {
                "reachable": probe.ok,
                "version": probe.stdout.strip() if probe.ok else "",
                "detail": "" if probe.ok else (probe.stderr or probe.stdout).strip(),
            },
        }

    @app.get("/version")
    def version() -> dict:
        return {"version": config.version}

    @app.post("/projects", status_code=201)
    def create_project(body: CreateProject) -> dict:
        # Same slug rule load_project applies to a directory name, so an id
        # survives the round trip host -> agent -> compose project name.
        project_id = _slug(body.id)
        if not project_id:
            raise ApiError("invalid_project",
                           f"'{body.id}' is not a usable project id", 422)
        if state.get_project(project_id) is not None:
            raise ApiError("project_exists",
                           f"project '{project_id}' already exists", 409)

        d = project_dir(project_id)
        d.mkdir(parents=True, exist_ok=True)
        if body.web:
            (d / ".omelet").mkdir(exist_ok=True)
            (d / ".omelet" / "project.yml").write_text(yaml.safe_dump(
                {"id": project_id, "web": [w.model_dump() for w in body.web]},
                sort_keys=False))
        state.add_project(project_id, str(d), body.domain or config.domain)
        return payload(state.get_project(project_id))

    @app.get("/projects")
    def list_projects() -> dict:
        return {"projects": [payload(row) for row in state.list_projects()]}

    @app.get("/projects/{project_id}")
    def get_project(project_id: str) -> dict:
        return payload(require_row(project_id))

    def resolve_path(project_id: str, rel_path: str) -> Path:
        try:
            return files.resolve_within(project_dir(project_id), rel_path)
        except files.PathTraversalError as e:
            raise ApiError("path_traversal", str(e), 400) from e

    async def _stream_to_tempfile(request: Request, dir_: Path) -> Path:
        # Written next to its destination, never buffered whole in memory -
        # this route body is what removes the old ~24 KB command-line ceiling.
        dir_.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=dir_, suffix=".upload")
        path = Path(name)
        written = 0
        try:
            with os.fdopen(fd, "wb") as f:
                async for chunk in request.stream():
                    written += len(chunk)
                    # Checked before writing: the moment the limit is passed,
                    # not after the whole body has already landed on disk.
                    if written > config.max_upload_bytes:
                        raise ApiError(
                            "payload_too_large",
                            f"upload exceeds the {config.max_upload_bytes} "
                            "byte limit", 413)
                    f.write(chunk)
        except BaseException:
            # A client that disconnects mid-upload, or trips the size cap
            # above, must not leave a temp file behind.
            path.unlink(missing_ok=True)
            raise
        return path

    @app.post("/projects/{project_id}/files")
    async def upload_files(project_id: str, request: Request) -> dict:
        require_row(project_id)
        d = project_dir(project_id)
        tmp = await _stream_to_tempfile(request, d.parent)
        try:
            try:
                files.extract_archive(tmp, d)
            except files.PathTraversalError as e:
                raise ApiError("path_traversal", str(e), 400) from e
            except files.BadArchiveError as e:
                raise ApiError("bad_archive", str(e), 400) from e
        finally:
            tmp.unlink(missing_ok=True)
        return {"id": project_id, "files": files.list_tree(d)}

    @app.get("/projects/{project_id}/files")
    def list_files(project_id: str) -> dict:
        require_row(project_id)
        return {"files": files.list_tree(project_dir(project_id))}

    @app.put("/projects/{project_id}/files/{file_path:path}")
    async def write_file(project_id: str, file_path: str, request: Request) -> dict:
        require_row(project_id)
        target = resolve_path(project_id, file_path)
        d = project_dir(project_id)
        # Staged next to the project directory, not inside it, so a listing
        # never catches the upload half-written.
        tmp = await _stream_to_tempfile(request, d.parent)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(tmp, target)
        finally:
            tmp.unlink(missing_ok=True)
        return {"path": file_path, "size": target.stat().st_size}

    @app.get("/projects/{project_id}/files/{file_path:path}")
    def read_file(project_id: str, file_path: str):
        require_row(project_id)
        target = resolve_path(project_id, file_path)
        if not target.is_file():
            raise ApiError("file_not_found",
                           f"no file '{file_path}' in project '{project_id}'", 404)
        # Starlette streams this from disk; the file is never read whole.
        return FileResponse(target)

    @app.delete("/projects/{project_id}/files/{file_path:path}")
    def delete_file(project_id: str, file_path: str) -> dict:
        require_row(project_id)
        target = resolve_path(project_id, file_path)
        if not target.is_file():
            raise ApiError("file_not_found",
                           f"no file '{file_path}' in project '{project_id}'", 404)
        target.unlink()
        return {"path": file_path, "deleted": True}

    @app.delete("/projects/{project_id}")
    def delete_project(project_id: str) -> dict:
        require_row(project_id)
        # `compose down` is bounded by container stop timeouts, not by an image
        # build, so this is the one compose call that stays synchronous. The
        # lock stops it removing the state row under a running `up`.
        with locks.held(project_id):
            result = lifecycle.compose_down(runner, project_id)
            state.remove_project(project_id)
        return {"id": project_id, "stopped": result.ok,
                "detail": "" if result.ok else (result.stderr or result.stdout).strip()}

    @app.post("/projects/{project_id}/up", status_code=202)
    def project_up(project_id: str) -> dict:
        row = require_row(project_id)
        # Parsing happens here, not in the job, so a broken compose file comes
        # back as an error code the caller can read instead of a failed job.
        project = load(project_id)
        domain = row["domain"]
        directory = project_dir(project_id)

        def work(write):
            try:
                write(f"compose up {project_id}\n")
                status, _lifecycle_urls, detail = lifecycle.compose_up(
                    runner, project, directory, domain)
                diagnosis = None
                if status == STARTED_OK:
                    write("waiting for the project to answer through Traefik\n")
                    diagnosis = diagnose(
                        runner, project, domain, edge_port=config.edge_port,
                        traefik_host=config.traefik_host, http_probe=http_probe,
                        timeout=config.ready_timeout)
                state.set_status(project_id, status)
                if diagnosis is None:
                    state.set_problem(project_id)
                else:
                    state.set_problem(project_id, diagnosis.code,
                                      diagnosis.message)
                result = {"status": status, "urls": urls_for(project, domain),
                          "problem": diagnosis.as_dict() if diagnosis else None}
                write(f"status: {status}\n")
                if diagnosis:
                    # The containers did start, so the job succeeds; the reason
                    # the URL will not answer belongs in its log all the same.
                    write(f"{diagnosis.message}\n")
                if detail:
                    write(f"{detail}\n")
                if status != STARTED_OK:
                    raise JobFailed(
                        detail or f"containers did not stay up (status: {status})",
                        result=result)
                return result
            finally:
                locks.release(project_id)

        return {"job_id": submit_locked(project_id, work)}

    @app.post("/projects/{project_id}/down", status_code=202)
    def project_down(project_id: str) -> dict:
        require_row(project_id)

        def work(write):
            try:
                write(f"compose down {project_id}\n")
                result = lifecycle.compose_down(runner, project_id)
                if not result.ok:
                    raise JobFailed((result.stderr or result.stdout).strip()
                                    or "compose down failed")
                state.set_status(project_id, "stopped")
                return {"status": "stopped"}
            finally:
                locks.release(project_id)

        return {"job_id": submit_locked(project_id, work)}

    @app.get("/projects/{project_id}/logs")
    def project_logs(project_id: str, follow: bool = False,
                     service: str | None = None):
        require_row(project_id)
        if not follow:
            result = lifecycle.project_logs(runner, project_id, service)
            if not result.ok:
                raise ApiError("logs_unavailable",
                               (result.stderr or result.stdout).strip()
                               or "docker compose logs failed", 409)
            return PlainTextResponse(result.stdout, media_type=TEXT)
        argv = lifecycle.logs_argv(project_id, service, follow=True)
        return StreamingResponse(runner.stream(argv, root=True), media_type=TEXT)

    @app.get("/jobs/{job_id}")
    def job_status(job_id: str) -> dict:
        return require_job(job_id).as_dict()

    @app.get("/jobs/{job_id}/logs")
    def job_logs(job_id: str, follow: bool = False):
        job = require_job(job_id)
        if not follow:
            return PlainTextResponse(job.text(), media_type=TEXT)
        return StreamingResponse(jobs.follow(job_id), media_type=TEXT)

    return app
