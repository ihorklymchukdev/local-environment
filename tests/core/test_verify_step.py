import pytest
import yaml

from runtime.core.install import VerificationFailed, verify_step
from runtime.core.provider import Completed


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
    assert seen == ["http://nginx-hello.127-0-0-1.sslip.io:39080"]
    assert any("down" in argv for argv in provider.execs), \
        "the smoke-test project must not be left running"


def test_verify_fails_on_a_non_200_status(template):
    with pytest.raises(VerificationFailed, match="502"):
        verify_step(FakeProvider(), template, "127-0-0-1.sslip.io",
                    http_get=lambda url: 502)


def test_verify_tears_down_even_when_the_request_fails(template):
    provider = FakeProvider()

    def http_get(url):
        raise OSError("connection refused")

    with pytest.raises(VerificationFailed):
        verify_step(provider, template, "127-0-0-1.sslip.io", http_get=http_get)
    assert any("down" in argv for argv in provider.execs)
