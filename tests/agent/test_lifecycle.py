from agent.core.lifecycle import compose_up, _compose_argv
from agent.core.project import Project, STARTED_OK
from agent.core.detect import WebSpec
from host.core.provider import Completed
from agent.core import constants


class FakeProvider:
    def __init__(self):
        self.execs = []

    def exec(self, argv, *, root=False):
        self.execs.append(argv)
        joined = " ".join(argv)
        if "ps" in argv and "--format" in joined:
            return Completed(0, '[{"Service":"web","State":"running","ExitCode":0}]', "")
        return Completed(0, "", "")


def test_compose_argv_uses_both_files_in_order():
    argv = _compose_argv("myproj")
    d = f"{constants.GUEST_PROJECTS}/myproj"
    assert argv[:2] == ["/usr/bin/docker", "compose"]
    assert argv.count("-f") == 2
    assert f"{d}/docker-compose.yml" in argv
    assert f"{d}/.omelet/overlay.yml" in argv
    assert argv[-2:] == ["up", "-d"]


def test_compose_up_returns_url_and_status(tmp_path):
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    proj = Project(id="myproj", webs=[WebSpec("web", 80)])
    p = FakeProvider()
    status, urls, detail = compose_up(p, proj, tmp_path, "d.io")
    assert status == STARTED_OK
    assert detail == "", "a healthy stack reports no failure detail"
    assert f"http://myproj.d.io:{constants.EDGE_PORT}" in urls
    # overlay was written into the guest, compose up ran with both -f files
    assert any("overlay.yml" in " ".join(a) for a in p.execs)
    assert any(a[-2:] == ["up", "-d"] for a in p.execs)


def test_compose_up_carries_the_guest_error_when_the_stack_fails():
    # A bare status like "failed_to_start" is unactionable: the reason lives in
    # compose's own stderr, which used to be discarded.
    from host.core.provider import Completed
    from agent.core.project import FAILED_TO_START

    class FailingProvider(FakeProvider):
        def exec(self, argv, *, root=False):
            self.execs.append(argv)
            if argv[-2:] == ["up", "-d"]:
                return Completed(1, "", "network edge declared as external, but could not be found")
            return Completed(0, "[]", "")

    proj = Project(id="myproj", webs=[WebSpec("web", 80)])
    status, _urls, detail = compose_up(FailingProvider(), proj, "/tmp", "d.io")
    assert status == FAILED_TO_START
    assert "network edge" in detail
