"""The host's compatibility check against the agent running in the VM.

A host binary talking to an agent older than the image it ships with fails
somewhere obscure -- a route that does not exist yet, a job result missing a
field. This check turns that into one sentence, before the slow steps.
"""
from __future__ import annotations

import pytest

from host.core.install import AgentTooOld, agent_version_step


class FakeClient:
    """Answers /version. `versions` is consumed one call at a time, so a test
    can say what the agent reports before and after a repair; an entry that is
    an exception is raised instead."""

    def __init__(self, *versions):
        self._versions = list(versions)

    def version(self) -> str:
        answer = (self._versions.pop(0) if len(self._versions) > 1
                  else self._versions[0])
        if isinstance(answer, BaseException):
            raise answer
        return answer


def test_an_older_agent_is_reported_in_words_a_user_can_act_on():
    with pytest.raises(AgentTooOld) as excinfo:
        agent_version_step(None, client=FakeClient("0.0.9"), expected="0.1.0")

    message = str(excinfo.value)
    assert "0.0.9" in message and "0.1.0" in message, \
        "support needs both versions"
    assert "older" in message.lower()
    assert "(0," not in message, \
        "a non-technical user must not be shown a version tuple"


def test_a_newer_agent_is_not_an_error():
    # Routes are added, not removed, so an agent ahead of the host serves
    # everything the host asks for. Refusing one would make a host downgrade,
    # or a pre-release image, unusable for no benefit.
    agent_version_step(None, client=FakeClient("0.2.0"), expected="0.1.0")
    agent_version_step(None, client=FakeClient("0.1.0"), expected="0.1.0")


def test_a_version_that_cannot_be_ordered_does_not_block_setup():
    # A locally built image ("dev", a git sha) says nothing about
    # compatibility. Failing setup over a string we cannot read would be worse
    # than continuing.
    agent_version_step(None, client=FakeClient("dev"), expected="0.1.0")
    agent_version_step(None, client=FakeClient(""), expected="0.1.0")


def test_an_older_agent_is_updated_in_place_rather_than_left_stuck():
    # The scenario this check exists for is an upgraded host against a VM
    # provisioned by the previous one. Reporting it and stopping leaves a
    # non-technical user with no move but destroying the VM and every project
    # in it -- bootstrap.sh's `compose pull && up -d` is the update mechanism,
    # and the marker that normally skips it is what left this VM behind.
    repairs = []
    message = agent_version_step(
        None, client=FakeClient("0.0.9", "0.1.0"), expected="0.1.0",
        repair=lambda: repairs.append("bootstrap"))

    assert repairs == ["bootstrap"]
    assert "0.1.0" in message


def test_an_agent_still_too_old_after_the_update_is_reported_once():
    repairs = []
    with pytest.raises(AgentTooOld):
        agent_version_step(None, client=FakeClient("0.0.9"), expected="0.1.0",
                           repair=lambda: repairs.append("bootstrap"))
    assert repairs == ["bootstrap"], "a failing update must not be retried"


def test_a_current_agent_is_never_re_provisioned():
    # The repair is minutes of pulling; an up-to-date VM must not pay it.
    repairs = []
    agent_version_step(None, client=FakeClient("0.1.0"), expected="0.1.0",
                       repair=lambda: repairs.append("bootstrap"))
    assert repairs == []


def test_the_agent_restarting_after_the_update_is_waited_out():
    # `compose up -d` returns before the new container is serving, so the
    # first version read after a repair legitimately answers "connection
    # refused". Failing there would report an unreachable VM seconds after
    # updating it.
    from host.client import AgentUnavailableError

    slept = []
    client = FakeClient("0.0.9", AgentUnavailableError("connection refused"),
                        "0.1.0")
    message = agent_version_step(None, client=client, expected="0.1.0",
                                 repair=lambda: None, sleep=slept.append)
    assert slept, "the agent's restart must be waited out, not spun on"
    assert "0.1.0" in message
