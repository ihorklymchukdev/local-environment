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
