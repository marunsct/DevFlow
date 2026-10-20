"""A command the plan tells a specialist to run is checked against the sandbox.

One run's technical lead ended three tasks with "MANDATORY VERIFICATION: run
`node -e ...`". The sandbox refuses inline code, so four specialist stages sent
the command the plan named and were refused.
"""
from __future__ import annotations

import json

import pytest

from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask
from app.analysis.planned_commands import (
    commands_the_sandbox_would_refuse,
    with_refused_commands_noted,
)


@pytest.fixture
def project(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "package.json").write_text(json.dumps({"name": "x"}), encoding="utf-8")
    return tmp_path


def _plan(*descriptions: str) -> MilestonePlanOutput:
    return MilestonePlanOutput(
        selected_sprint_goal="goal",
        delegated_tasks=[
            SpecialistTask(specialist_role="ui_ux", task_description=d) for d in descriptions
        ],
    )


def test_a_refused_command_is_noted_on_its_task(project):
    """Inline code (`node -e`) is no longer one: the command tool runs it from a file (LF.60, LF.104)."""
    plan = with_refused_commands_noted(_plan(
        "Write index.html. Then run `npx playwright install --with-deps`.",
    ), project)

    text = plan.delegated_tasks[0].task_description
    assert "Checked against this sandbox before you started" in text
    assert "will not run as written" in text
    assert "installs system packages as root" in text


def test_a_command_the_role_may_run_is_left_alone(project):
    original = _plan("Run `npm test` in `app` and `grep -n render app/app.js`.")
    assert with_refused_commands_noted(original, project) == original


def test_names_that_are_not_programs_are_not_commands(project):
    notes = commands_the_sandbox_would_refuse(
        "Edit `app/app.js`, export `addTask(title)`, style `.task-card`.", "ui_ux_specialist", project
    )
    assert notes == []


def test_a_shell_chain_is_named_as_needing_a_shell(project):
    notes = commands_the_sandbox_would_refuse(
        "run `npm test 2>/dev/null || echo skipped`", "testing_specialist", project
    )
    assert len(notes) == 1
    assert "There is no shell here" in notes[0]


def test_a_fenced_command_is_checked_too(project):
    notes = commands_the_sandbox_would_refuse(
        "Verify with:\n```sh\nnpx playwright install --with-deps\n```\n", "backend_specialist", project
    )
    assert notes and "playwright install" in notes[0]


def test_it_never_raises_on_a_malformed_plan(project):
    assert with_refused_commands_noted(object(), project) is not None
    assert commands_the_sandbox_would_refuse("`unterminated \"quote`", "x", project) == []


class TestQuotedTextIsNotAShellOperator:
    """One run's plan said `grep -q '<form' simple-to-do-list-app/index.html`,
    which runs as written, and was sent back as "will not run as written"."""

    def test_a_quoted_angle_bracket_is_an_argument(self):
        from app.analysis.planned_commands import _commands_in

        assert _commands_in("grep -q '<form' app/index.html") == ([["grep", "-q", "<form", "app/index.html"]], False)
        assert _commands_in("echo 'a|b' x") == ([["echo", "a|b", "x"]], False)

    def test_an_operator_outside_quotes_still_is(self):
        from app.analysis.planned_commands import _commands_in

        assert _commands_in("node app.js > out.txt") == ([["node", "app.js"]], True)
        assert _commands_in("npm test 2>&1") == ([["npm", "test"]], True)
        assert _commands_in("npm test && npm run e2e") == ([["npm", "test"], ["npm", "run", "e2e"]], True)

    def test_the_run_s_command_is_not_reported(self):
        from app.analysis.planned_commands import commands_the_sandbox_would_refuse

        notes = commands_the_sandbox_would_refuse("`grep -q '<form' simple-to-do-list-app/index.html`", "ui_ux_specialist")
        assert not any("no shell" in note for note in notes)
