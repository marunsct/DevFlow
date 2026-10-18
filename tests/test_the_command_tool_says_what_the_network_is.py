"""The command tool's network sentence is true for the sandbox mode in use (Initiative X.3).

It told every stage that everything but 'install' runs with networking
disabled. In container mode - the deployment's own - the command runs in the
worker and nothing cuts the network.
"""

from __future__ import annotations

from unittest import mock

from app.tools import agent_toolkit, sandbox


def _description(mode: str) -> str:
    with mock.patch.object(sandbox, "execution_mode", lambda: mode):
        return agent_toolkit.build_terminal_command_tool("/tmp").description


def test_in_container_mode_it_does_not_claim_the_network_is_off() -> None:
    text = _description(sandbox.IN_CONTAINER_MODE)
    assert "runs with networking disabled" not in text
    assert "not cut off from the network" in text


def test_with_a_container_per_command_it_says_the_network_is_off() -> None:
    other = next(m for m in ("docker", "per-command", "container") if m != sandbox.IN_CONTAINER_MODE)
    assert "runs with networking disabled" in _description(other)


def test_the_sentence_replaced_is_the_one_the_docstring_has() -> None:
    assert agent_toolkit.NETWORK_OFF_SENTENCE in _description("docker")
