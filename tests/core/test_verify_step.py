import pytest
import yaml

from omelet.core.install import VerificationFailed, verify_step
from omelet.core.provider import Completed


class FakeProvider:
    """Records guest commands; reports a healthy compose stack."""

    def __init__(self):
        self.execs = []

    def exec(self, argv, *, root=False):
        self.execs.append(argv)
        if "ps" in argv:
            return Completed(0, '[{"Service":"web","State":"running"}]', "")
        return Completed(0, "", "")


@pytest.fixture
def template(tmp_path):
    d = tmp_path / "nginx-hello"
    d.mkdir()
    (d / "docker-compose.yml").write_text(yaml.safe_dump(
        {"services": {"web": {"image": "nginx:alpine", "ports": ["8080:80"]}}}))
    return d


def test_verify_passes_on_200_and_tears_the_project_down(template):
    provider = FakeProvider()
    seen = []

    def http_get(url):
        seen.append(url)
        return 200

    verify_step(provider, template, "127-0-0-1.sslip.io", http_get=http_get)
    assert seen == ["http://omelet-selftest.127-0-0-1.sslip.io:39080"], \
        "the smoke test must use a reserved id, not the template's folder name"
    assert any("down" in argv for argv in provider.execs), \
        "the smoke-test project must not be left running"


def test_verify_fails_on_a_non_200_status(template):
    with pytest.raises(VerificationFailed, match="502"):
        verify_step(FakeProvider(), template, "127-0-0-1.sslip.io",
                    http_get=lambda url: 502, ready_timeout=0)


def test_verify_fails_without_requesting_when_the_stack_is_crash_looping(template):
    class CrashLooping(FakeProvider):
        def exec(self, argv, *, root=False):
            self.execs.append(argv)
            if "ps" in argv:
                return Completed(0, '[{"Service":"web","State":"restarting"}]', "")
            return Completed(0, "", "")

    provider = CrashLooping()
    requested = []

    with pytest.raises(VerificationFailed, match="crash_looping"):
        verify_step(provider, template, "127-0-0-1.sslip.io",
                    http_get=lambda url: requested.append(url) or 200)

    assert requested == [], \
        "a container that never came up must fail before anything is requested"
    assert any("down" in argv for argv in provider.execs)


def test_verify_tears_down_even_when_the_request_fails(template):
    provider = FakeProvider()

    def http_get(url):
        raise OSError("connection refused")

    with pytest.raises(VerificationFailed):
        verify_step(provider, template, "127-0-0-1.sslip.io", http_get=http_get,
                    ready_timeout=0)
    assert any("down" in argv for argv in provider.execs)


def test_verify_waits_out_the_404_before_traefik_publishes_the_router(template):
    # Traefik registers a new router a beat after the container starts. A
    # single-shot request fails a healthy stack with
    # "...did not respond: HTTP Error 404: Not Found".
    from urllib.error import HTTPError

    codes = iter([404, 404, 200])

    def http_get(url):
        code = next(codes)
        if code != 200:
            raise HTTPError(url, code, "Not Found", {}, None)
        return code

    slept = []
    verify_step(FakeProvider(), template, "127-0-0-1.sslip.io",
                http_get=http_get, sleep=slept.append)
    assert slept, "the smoke test must retry rather than fail on the first 404"
