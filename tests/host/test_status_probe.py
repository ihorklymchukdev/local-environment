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


class RaisingExecProvider:
    """A provider that exists, but blows up on one particular `exec` call --
    for the escape paths past `exists()` returning True, which the fixed
    `_reachable`/`_engine` knobs on `FakeProvider` can't reach."""

    def __init__(self, *, fail_on: str):
        self._fail_on = fail_on

    def exists(self):
        return True

    def exec(self, argv, *, root=False):
        if argv[0] == self._fail_on:
            raise RuntimeError(f"{argv[0]} failed")
        return Completed(0, "", "")


def _client(health=None, error=None):
    class Client:
        def health(self):
            if error:
                raise error
            return health or {"api": 1}
    return lambda provider: Client()


def _client_factory_raising(error):
    """A factory that fails during construction itself, before any `Client`
    exists to call `.health()` on -- a distinct escape path from `.health()`
    raising once the client is already built."""
    def factory(provider):
        raise error
    return factory


def _client_returning(health):
    """A client whose `.health()` hands back something with no usable
    `.get("api", ...)` -- `None`, a list, anything that isn't a dict."""
    class Client:
        def health(self):
            return health
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


def test_probe_never_raises_when_exists_itself_throws():
    class Exploding:
        def exists(self):
            raise RuntimeError("limactl is not installed")

    result = probe(Exploding(), client_factory=_client())
    assert not result.ready
    assert "limactl is not installed" in result.problem
    # Nothing was established yet -- exists() is the very first question.
    assert result == Readiness(problem="limactl is not installed")


def test_probe_never_raises_when_the_reachability_check_throws():
    # exists() already succeeded; exec(["true"]) throws instead of returning
    # a Completed. vm_exists is a fact this run did establish and must survive.
    result = probe(RaisingExecProvider(fail_on="true"), client_factory=_client())
    assert not result.ready
    assert result.vm_exists and not result.vm_reachable
    assert result.engine_version is None
    assert "true failed" in result.problem


def test_probe_never_raises_when_the_marker_read_throws():
    # exec(["true"]) already succeeded; exec(["cat", ...]) throws. Both
    # vm_exists and vm_reachable are established facts and must survive.
    result = probe(RaisingExecProvider(fail_on="cat"), client_factory=_client())
    assert not result.ready
    assert result.vm_exists and result.vm_reachable
    assert result.engine_version is None
    assert "cat failed" in result.problem


def test_probe_never_raises_when_the_client_factory_itself_throws():
    # Distinct from .health() raising: nothing was even built to call it on.
    result = probe(FakeProvider(),
                   client_factory=_client_factory_raising(OSError("no route to host")))
    assert not result.ready
    assert result.vm_exists and result.vm_reachable
    assert result.engine_version == "0.1.0"
    assert result.agent_api is None
    assert "no route to host" in result.problem


def test_probe_never_raises_when_health_answers_with_no_usable_api_field():
    for shapeless in (None, ["not", "a", "dict"], "nope"):
        result = probe(FakeProvider(), client_factory=_client_returning(shapeless))
        assert not result.ready
        assert result.vm_exists and result.vm_reachable
        assert result.engine_version == "0.1.0"
        assert result.agent_api is None
        assert result.problem, f"expected a problem recorded for {shapeless!r}"


def test_an_unsupported_agent_api_is_not_ready():
    from host.core import constants
    unsupported = max(constants.SUPPORTED_API) + 1
    result = probe(FakeProvider(), client_factory=_client(health={"api": unsupported}))
    assert result.agent_api == unsupported
    assert not result.ready
