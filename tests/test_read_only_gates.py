"""Looking around must not spend the budget meant for building.

Measured on one run: `specialist_testing_2` used all 120 of its approval
gates and was stopped before finishing. What it spent them on:

    5x  run_terminal_command ['ls', '-la', '/app/data/workspaces/t7-run-...']
    2x  run_terminal_command ['find', '/app/data/workspaces/t7-run-...']
    1x  run_terminal_command ['cat', '/app/data/workspaces/t7-run-...']

Every one is read-only, and the agent already holds ungated `ls`, `read_file`,
`glob` and `grep` that do the same thing. It explored through the expensive
door until there was no budget left for work.

The approval still happens and is still recorded - the audit trail and the
human-approval semantics are unchanged. Only the per-stage ceiling stops
counting it.
"""

from __future__ import annotations

import pytest

from app.agents.approval import is_read_only_command


@pytest.mark.parametrize(
    "command",
    [["ls", "-la"], ["cat", "a.txt"], ["find", ".", "-name", "*.js"],
     ["wc", "-l", "x"], ["grep", "-r", "todo", "."], ["pwd"], ["which", "node"]],
)
def test_a_look_is_read_only(command):
    assert is_read_only_command({"args": {"command": command}})


@pytest.mark.parametrize(
    "command",
    [["npm", "test"], ["node", "x.js"], ["npm", "install"], ["mkdir", "p"],
     ["git", "commit"], ["python3", "x.py"]],
)
def test_anything_that_acts_is_not(command):
    assert not is_read_only_command({"args": {"command": command}})


@pytest.mark.parametrize("operator", [">", ">>", "|", ";", "&&", "||", "<"])
def test_a_redirection_makes_it_an_action(operator):
    """`cat a > b` writes. The executable name alone is not enough."""
    assert not is_read_only_command({"args": {"command": ["cat", "a", operator, "b"]}})


def test_a_write_request_is_not_a_command_at_all():
    assert not is_read_only_command({"args": {"relative_path": "a.md", "content": "x"}})


def test_the_ceiling_skips_read_only_gates():
    import inspect

    from app.server import runner

    source = " ".join(inspect.getsource(runner).split())

    assert 'action_kind", "") != "read"' in source
    assert "does not spend the budget meant for writes" in source


def test_read_is_a_valid_action_kind():
    """The state schema has to carry it, or the request cannot be stored."""
    from app.state import HumanApprovalRequest

    field = HumanApprovalRequest.model_fields["action_kind"]
    assert "read" in str(field.annotation)
