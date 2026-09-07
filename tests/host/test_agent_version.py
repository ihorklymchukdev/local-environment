"""The host's compatibility check against the agent running in the VM.

A host binary talking to an agent older than the image it ships with fails
somewhere obscure -- a route that does not exist yet, a job result missing a
field. This check turns that into one sentence, before the slow steps.
"""
from __future__ import annotations

import pytest

from host.core.constants import AGENT_IMAGE, EXPECTED_AGENT_VERSION
from host.core.install import AgentTooOld, agent_version_step


class FakeClient:
    def __init__(self, version: str):
        self._version = version

    def version(self) -> str:
        return self._version


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


def test_the_expected_version_is_the_tag_the_host_pulls():
    # Derived, not restated: a bumped image tag must not leave the check
    # behind, comparing against a version nothing deploys any more.
    assert AGENT_IMAGE.endswith(f":{EXPECTED_AGENT_VERSION}")
