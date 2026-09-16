"""A claimed fix, checked against what actually ran.

`VerificationRun`'s docstring has always said "a claim here is checked against
`read_execution_ledger`, which is what makes it evidence rather than
assertion". No such check existed until this module. run-d3965815's final
message to the human reported two of three defects fixed while `app.test.mjs`
failed continuously from the first test round to the last - because "fixed"
meant "the specialist named a test" and nothing more.
"""

from __future__ import annotations

import json

import pytest

from app.agents.specialists import VerificationRun
from app.analysis.verification_claims import proven_commands, why_this_fix_is_not_proven


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    """A workspace whose execution ledger we control."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    root = tmp_path / "product-run-abc123"
    root.mkdir(parents=True)
    return root


def _ledger(root, entries) -> None:
    from app.tools.sandbox import _ledger_path

    path = _ledger_path(str(root))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")


def test_a_command_that_really_passed_proves_the_fix(workspace) -> None:
    _ledger(workspace, [{"command": ["node", "--test", "."], "returncode": "0"}])

    claims = [VerificationRun(command=["node", "--test", "."], exit_code=0)]

    assert proven_commands(str(workspace), claims) == [["node", "--test", "."]]
    assert why_this_fix_is_not_proven(str(workspace), claims) == ""


def test_a_command_that_failed_proves_nothing(workspace) -> None:
    """The run-d3965815 shape: claimed fixed, suite still red."""
    _ledger(workspace, [{"command": ["node", "--test", "."], "returncode": "1"}])

    claims = [VerificationRun(command=["node", "--test", "."], exit_code=0)]

    why = why_this_fix_is_not_proven(str(workspace), claims)

    assert "exited 0" in why
    assert "node --test ." in why


def test_a_command_nobody_ran_proves_nothing(workspace) -> None:
    _ledger(workspace, [{"command": ["ls"], "returncode": "0"}])

    why = why_this_fix_is_not_proven(
        str(workspace), [VerificationRun(command=["npm", "test"], exit_code=0)]
    )

    assert "npm test" in why


def test_an_empty_verification_list_says_so_plainly(workspace) -> None:
    why = why_this_fix_is_not_proven(str(workspace), [])

    assert "nothing was run" in why


def test_one_passing_command_among_several_is_enough(workspace) -> None:
    """A specialist that ran the linter, failed it, then ran the suite and
    passed has proven the suite."""
    _ledger(
        workspace,
        [
            {"command": ["npx", "eslint", "."], "returncode": "2"},
            {"command": ["node", "--test", "."], "returncode": "0"},
        ],
    )

    claims = [
        VerificationRun(command=["npx", "eslint", "."], exit_code=2),
        VerificationRun(command=["node", "--test", "."], exit_code=0),
    ]

    assert why_this_fix_is_not_proven(str(workspace), claims) == ""


def test_a_command_given_as_a_string_is_still_matched(workspace) -> None:
    """`VerificationRun` accepts a string and splits it; so must this."""
    _ledger(workspace, [{"command": ["node", "--test", "."], "returncode": "0"}])

    claims = [VerificationRun(command="node --test .", exit_code=0)]

    assert why_this_fix_is_not_proven(str(workspace), claims) == ""


def test_an_unreadable_ledger_does_not_invent_proof(workspace) -> None:
    """No ledger means nothing is proven - not that everything is."""
    claims = [VerificationRun(command=["node", "--test", "."], exit_code=0)]

    assert proven_commands(str(workspace), claims) == []


def test_the_report_says_which_fixes_were_proven() -> None:
    """"fixed" on its own was a claim, not a finding."""
    from app.sprint import Defect, RemediationCycle, build_defect_report

    cycle = RemediationCycle(
        sprint_goal="build it",
        defects=[
            Defect(
                description="renderTasks creates 0 items",
                severity="major",
                reproduction_steps="node --test .",
                expected_behavior="two items",
                actual_behavior="none",
                owner="testing",
                status="fixed",
                regression_test="renders two items",
                verified_by="node --test .",
            ),
            Defect(
                description="syntax error in createElementFallback",
                severity="major",
                reproduction_steps="node --test .",
                expected_behavior="parses",
                actual_behavior="Unexpected token",
                owner="security_reliability",
                status="fixed",
                regression_test="parses cleanly",
            ),
        ],
    )

    report = build_defect_report(cycle)

    assert "fixed, verified by `node --test .`" in report
    assert "fixed, but nothing was recorded as running and passing" in report


def test_an_unproven_fix_that_came_back_says_so() -> None:
    """The most actionable thing to tell the next specialist."""
    from app.sprint import Defect, RemediationCycle, recurring_defect_note

    def _defect(description: str, **extra) -> Defect:
        return Defect(
            description=description,
            severity="major",
            reproduction_steps="node --test .",
            expected_behavior="passes",
            actual_behavior="fails",
            owner="testing",
            **extra,
        )

    cycle = RemediationCycle(
        sprint_goal="build it",
        defects=[
            _defect(
                "renderTasks creates zero items despite valid tasks",
                status="fixed",
                regression_test="t",
            ),
            _defect("renderTasks creates zero items from a valid tasks array"),
        ],
    )

    note = recurring_defect_note(cycle)

    assert "That fix did not work" in note
    assert "whether it was run at all" in note
