from typer.testing import CliRunner

import host.cli as cli

runner = CliRunner()


class FakeProvider:
    def __init__(self, forwards=(), error=None):
        self.calls = []
        self._forwards = list(forwards)
        self._error = error

    def forward(self, guest_port, host_port):
        self.calls.append(("forward", guest_port, host_port))
        if self._error:
            raise self._error

    def unforward(self, guest_port, host_port):
        self.calls.append(("unforward", guest_port, host_port))

    def forwards(self):
        return self._forwards


def run(monkeypatch, fake, argv):
    monkeypatch.setattr(cli, "_provider_factory", lambda: fake)
    return runner.invoke(cli.app, argv)


def test_port_add_forwards_guest_to_host(monkeypatch):
    fake = FakeProvider()
    result = run(monkeypatch, fake, ["port", "add", "5432", "5433"])
    assert result.exit_code == 0
    assert fake.calls == [("forward", 5432, 5433)]
    # The confirmation has to name the address the user types into their tool;
    # "forwarded 5432" leaves them guessing which side is which.
    assert "localhost:5433" in result.output


def test_port_add_reports_the_providers_own_sentence(monkeypatch):
    fake = FakeProvider(error=RuntimeError("port 5433 could not be forwarded"))
    result = run(monkeypatch, fake, ["port", "add", "5432", "5433"])
    assert result.exit_code == 1
    assert "could not be forwarded" in result.output
    assert "Traceback" not in result.output


def test_port_list_reads_both_ends(monkeypatch):
    fake = FakeProvider(forwards=[(5432, 5433), (6379, 6380)])
    result = run(monkeypatch, fake, ["port", "list"])
    assert result.exit_code == 0
    assert "localhost:5433 -> 5432" in result.output
    assert "localhost:6380 -> 6379" in result.output


def test_port_list_says_so_when_there_are_none(monkeypatch):
    result = run(monkeypatch, FakeProvider(), ["port", "list"])
    assert "No port forwards." in result.output


def test_port_remove_releases_it(monkeypatch):
    fake = FakeProvider()
    result = run(monkeypatch, fake, ["port", "remove", "5432", "5433"])
    assert result.exit_code == 0
    assert fake.calls == [("unforward", 5432, 5433)]
