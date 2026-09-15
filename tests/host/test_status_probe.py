"""Is this machine set up? Asked cheaply, and answered without raising.

The window calls this before it draws anything, so a provider that throws, a
VM that is gone and an agent that is silent all have to come back as facts.
"""
from host.core.provider import Completed
from host.core.status import Readiness, probe


class FakeProvider:
    def __init__(self, *, exists=True, reachable=True, engine="0.1.0"):
        self._exists, self._reachable, self._engine = exists, reachable, engine
        self.calls = []

    def exists(self):
        return self._exists

    def exec(self, argv, *, root=False):
        self.calls.append(argv)
        if not self._reachable:
            return Completed(1, "", "the VM is not running")
        if argv[0] == "cat":
            return (Completed(0, self._engine, "") if self._engine
                    else Completed(1, "", "No such file or directory"))
        return Completed(0, "", "")


def _client(health=None, error=None):
    class Client:
        def health(self):
            if error:
                raise error
            return health or {"api": 1}
    return lambda provider: Client()


def test_a_provisioned_machine_is_ready():
    result = probe(FakeProvider(), client_factory=_client())
    assert result == Readiness(vm_exists=True, vm_reachable=True,
                               engine_version="0.1.0", agent_api=1)
    assert result.ready


def test_a_missing_vm_stops_before_touching_the_guest():
    provider = FakeProvider(exists=False)
    result = probe(provider, client_factory=_client())
    assert not result.ready
    assert not result.vm_exists
    assert provider.calls == [], "nothing may be executed in a VM that is not there"


def test_a_vm_that_is_not_running_is_not_ready():
    result = probe(FakeProvider(reachable=False), client_factory=_client())
    assert result.vm_exists and not result.vm_reachable
    assert result.engine_version is None
    assert not result.ready


def test_a_vm_without_the_engine_is_not_ready():
    result = probe(FakeProvider(engine=""), client_factory=_client())
    assert result.vm_reachable and result.engine_version is None
    assert not result.ready


def test_a_silent_agent_is_not_ready_and_the_reason_is_kept():
    result = probe(FakeProvider(), client_factory=_client(error=OSError("refused")))
    assert result.engine_version == "0.1.0"
    assert result.agent_api is None
    assert "refused" in result.problem
    assert not result.ready


def test_probe_never_raises():
    class Exploding:
        def exists(self):
            raise RuntimeError("limactl is not installed")

    result = probe(Exploding(), client_factory=_client())
    assert not result.ready
    assert "limactl is not installed" in result.problem


def test_an_unsupported_agent_api_is_not_ready():
    from host.core import constants
    unsupported = max(constants.SUPPORTED_API) + 1
    result = probe(FakeProvider(), client_factory=_client(health={"api": unsupported}))
    assert result.agent_api == unsupported
    assert not result.ready
