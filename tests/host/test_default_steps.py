"""The wiring of the real step list — the seam where findings survived review.

Every other install test builds its own toy steps, so nothing exercised the
list `omelet setup` actually runs.
"""
import pytest

from host.core.images import Image
from host.core.install import InstallError, InstallState, default_steps, run_install
from host.core.provider import CheckResult, Diagnosis

IMAGE = Image("https://example.invalid/ubuntu-24.04.4-wsl-amd64.wsl", "0" * 64)


class FakeProvider:
    def __init__(self, *, exists=True, reboot=False):
        self.rootfs = None
        self._exists = exists
        self._reboot = reboot
        self.created = False
        self.resumed_with = None

    def preflight(self): return Diagnosis([CheckResult("fine", True)])
    def apply_remedy(self, remedy): pass
    def reboot_required(self): return self._reboot
    def register_resume(self, exe): self.resumed_with = exe
    def image(self): return IMAGE
    def exists(self): return self._exists

    def create(self):
        if self.rootfs is None:
            raise ValueError("install_dir and rootfs are required to create the VM")
        self.created = True


def build(provider, tmp_path, **overrides):
    kwargs = dict(
        cache_dir=tmp_path / "cache",
        template_dir=tmp_path / "template",
        domain="127-0-0-1.sslip.io",
        exe_path=r"C:\Apps\Omelet\setup.exe",
        install_dir=tmp_path / "vm",
    )
    return default_steps(provider, **{**kwargs, **overrides})


def run(steps, state, patch):
    """Run the real list, substituting the steps that would touch a real VM."""
    events = []
    stubbed = [s if s.name not in patch else type(s)(
        s.name, patch[s.name], always_run=s.always_run, action=s.action)
        for s in steps]
    run_install(stubbed, state, events.append)
    return events


def test_step_names_and_order_match_the_spec(tmp_path):
    names = [s.name for s in build(FakeProvider(), tmp_path)]
    assert names == ["preflight", "remediate", "reboot_gate", "fetch_image",
                     "create_vm", "bootstrap", "agent", "verify", "finish"]


def test_rootfs_is_set_even_when_fetch_image_is_skipped(tmp_path):
    # The bug: rootfs was only assigned as a side effect inside fetch_image, so
    # any re-run after a failure reached create_vm with rootfs=None forever.
    state = InstallState(tmp_path / "state.json")
    for name in ("preflight", "remediate", "reboot_gate", "fetch_image"):
        state.mark(name)

    provider = FakeProvider(exists=False)
    steps = build(provider, tmp_path)
    run(steps, state, {"bootstrap": lambda: None, "agent": lambda: None,
                       "verify": lambda: None})

    assert provider.rootfs == tmp_path / "cache" / "ubuntu-24.04.4-wsl-amd64.wsl"
    assert provider.created, "create_vm must succeed on a re-run, not raise on a None rootfs"


def test_the_proving_steps_run_again_on_a_re_run(tmp_path):
    # A user whose VM broke re-runs setup; skipping verify would report success
    # while proving nothing, and the VM's agent can have changed since the run
    # that recorded the compatibility check.
    state = InstallState(tmp_path / "state.json")
    provider = FakeProvider()
    ran = []
    patch = {"fetch_image": lambda: None,
             "bootstrap": lambda: None,
             "agent": lambda: ran.append("agent"),
             "verify": lambda: ran.append("verify"),
             "finish": lambda: ran.append("finish") or "done"}

    run(build(provider, tmp_path), state, patch)
    assert ran == ["agent", "verify", "finish"]
    assert "verify" not in state.completed(), \
        "a proof that only holds for one run must not be persisted"

    ran.clear()
    events = run(build(provider, tmp_path), state, patch)
    assert ran == ["agent", "verify", "finish"], "verify must never be skipped"
    assert [e.step for e in events if e.status == "skipped"] == \
        ["preflight", "remediate", "reboot_gate", "fetch_image", "create_vm",
         "bootstrap"]


def test_finish_names_the_install_location_and_the_next_command(tmp_path):
    state = InstallState(tmp_path / "state.json")
    events = run(build(FakeProvider(), tmp_path), state,
                 {"fetch_image": lambda: None, "bootstrap": lambda: None,
                  "agent": lambda: None, "verify": lambda: None})
    finish = next(e for e in events if e.step == "finish" and e.status == "done")
    assert str(tmp_path / "vm") in finish.message
    assert "omelet up" in finish.message
    assert "succe" in finish.message.lower()


def test_a_failure_carries_a_suggested_action_not_just_the_raw_error(tmp_path):
    state = InstallState(tmp_path / "state.json")

    def boom():
        raise OSError("<urlopen error [Errno 11001] getaddrinfo failed>")

    with pytest.raises(InstallError) as excinfo:
        run(build(FakeProvider(), tmp_path), state, {"fetch_image": boom})

    assert excinfo.value.step == "fetch_image"
    assert "getaddrinfo" in excinfo.value.message, "support still needs the raw detail"
    assert "internet" in excinfo.value.action.lower()
    assert "urlopen" not in excinfo.value.action, "the action must be jargon-free"


def test_the_gate_registers_resume_before_asking_for_a_restart(tmp_path):
    from host.core.install import RebootRequired

    provider = FakeProvider(reboot=True)
    state = InstallState(tmp_path / "state.json")
    with pytest.raises(RebootRequired):
        run(build(provider, tmp_path), state, {})
    assert provider.resumed_with == r"C:\Apps\Omelet\setup.exe"
