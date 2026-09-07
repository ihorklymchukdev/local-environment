from fastapi.testclient import TestClient

from agent.api.app import create_app
from agent.core.config import AgentConfig


def _client(tmp_path, token: str | None) -> TestClient:
    """`token=None` means no file at all; `""` means an empty file -- both
    must be treated as unconfigured, never as "allow"."""
    token_path = tmp_path / "agent.token"
    if token is not None:
        token_path.write_text(token)
    config = AgentConfig(projects_root=tmp_path / "projects",
                         state_db=tmp_path / "state.db", token_path=token_path)
    return TestClient(create_app(config=config), raise_server_exceptions=False)


def test_health_answers_with_no_authorization_header(tmp_path):
    client = _client(tmp_path, "secret")
    assert client.get("/health").status_code == 200


def test_health_answers_even_when_the_agent_has_no_token_configured(tmp_path):
    client = _client(tmp_path, None)
    assert client.get("/health").status_code == 200


def test_version_is_not_exempt_from_auth(tmp_path):
    # /health is the only exemption -- an unauthenticated /version is a free
    # fingerprint of the VM's contents.
    client = _client(tmp_path, "secret")
    resp = client.get("/version")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


def test_a_request_without_a_token_is_rejected(tmp_path):
    client = _client(tmp_path, "secret")
    resp = client.get("/projects")
    assert resp.status_code == 401
    assert resp.json()["error"] == {"code": "unauthorized",
                                    "message": resp.json()["error"]["message"]}


def test_a_request_with_the_wrong_token_is_rejected(tmp_path):
    client = _client(tmp_path, "secret")
    resp = client.get("/projects", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


def test_a_request_with_the_right_token_is_accepted(tmp_path):
    client = _client(tmp_path, "secret")
    resp = client.get("/projects", headers={"Authorization": "Bearer secret"})
    assert resp.status_code == 200


def test_a_non_bearer_scheme_is_rejected(tmp_path):
    client = _client(tmp_path, "secret")
    resp = client.get("/projects", headers={"Authorization": "secret"})
    assert resp.status_code == 401


def test_missing_token_file_never_falls_back_to_allowing_requests(tmp_path):
    # R-20: a missing token must never mean "allow", even when the caller
    # supplies something that looks like a credential.
    client = _client(tmp_path, None)
    resp = client.get("/projects", headers={"Authorization": "Bearer anything"})
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "agent_unconfigured"


def test_empty_token_file_is_also_treated_as_unconfigured(tmp_path):
    client = _client(tmp_path, "")
    resp = client.get("/projects")
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "agent_unconfigured"


def test_a_token_file_with_only_whitespace_is_treated_as_unconfigured(tmp_path):
    client = _client(tmp_path, "\n")
    resp = client.get("/projects")
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "agent_unconfigured"
