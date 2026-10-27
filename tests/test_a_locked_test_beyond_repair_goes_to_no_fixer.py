"""A locked test that cannot pass, once the suite may not be repaired again, goes to no fixer.

Measured on one run: with its two suite repairs spent, the round's check named
the locked test that looked for a value it never entered, and the list went
nowhere. The test engineer found the same fault in the evidence, reported it
as a defect, and two fix stages in turn answered "a test bug; this stage
cannot change the locked suite".
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.acceptance import suite
from app.graph import acceptance_nodes as nodes
from app.graph.workflow import _a_suite_failure_the_round_did_not_report, _defects_only_about
from app.tools.sandbox import _ledger_path

BANNED = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")
BROKEN = [
    "`app/acceptance/a.spec.js` line 9: `[AC-13] renames and removes` looks for `second`, a value the "
    "test made itself and never gave the product",
]


def test_while_the_suite_may_be_repaired_nothing_is_beyond_repair() -> None:
    assert nodes.beyond_repair({"suite_repairs": nodes.MAX_SUITE_REPAIRS - 1}, BROKEN) == []


def test_once_its_repairs_are_spent_the_tests_criteria_are() -> None:
    assert nodes.beyond_repair({"suite_repairs": nodes.MAX_SUITE_REPAIRS_IN_ALL}, BROKEN) == ["AC-13"]
    assert nodes.beyond_repair({"suite_repairs": nodes.MAX_SUITE_REPAIRS_IN_ALL}, []) == []


def test_the_round_is_told_in_words_that_fit_any_product() -> None:
    note = nodes.beyond_repair_note(BROKEN, ["AC-13"])

    assert "(AC-13)" in note and BROKEN[0] in note
    rule = note.split("\n- ")[0].lower()
    for word in BANNED:
        assert not re.search(rf"\b{word}\b", rule), word


def _reported(description: str) -> SimpleNamespace:
    return SimpleNamespace(description=description, reproduction_steps="", expected_behavior="", actual_behavior="")


def test_only_a_defect_naming_nothing_but_those_criteria_is_set_aside() -> None:
    only = _reported("AC-13 locked test never enters the value it looks for")
    with_another = _reported("AC-13 and AC-2 both fail after saving")
    naming_none = _reported("Saving loses the value")

    kept, set_aside = _defects_only_about([only, with_another, naming_none], ["AC-13"])

    assert set_aside == [only]
    assert kept == [with_another, naming_none]
    assert _defects_only_about([only], []) == ([only], [])


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    root = tmp_path / "the-app-run-abc"
    root.mkdir()
    monkeypatch.setattr(suite, "_command", lambda repo_root: (["npx", "playwright", "test"], "report.xml", "app"))
    return root


def _ran(root: Path, command: list[str]) -> None:
    path = _ledger_path(str(root))
    assert path is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"stage": "test_round_3", "command": command, "category": "test", "returncode": 1}) + "\n")


def test_a_failed_acceptance_run_is_not_raised_again_for_the_defects_set_aside(workspace) -> None:
    _ran(workspace, ["npx", "playwright", "test", "acceptance/a.spec.js"])

    assert _a_suite_failure_the_round_did_not_report(str(workspace), "test_round_3", but_the_acceptance_suite=True) is None
    assert _a_suite_failure_the_round_did_not_report(str(workspace), "test_round_3") is not None


def test_any_other_failing_command_still_is(workspace) -> None:
    _ran(workspace, ["npm", "test"])

    defect = _a_suite_failure_the_round_did_not_report(str(workspace), "test_round_3", but_the_acceptance_suite=True)

    assert defect is not None and "`npm test` exited 1" in defect.description


def test_a_testing_finding_about_only_the_locked_suite_s_files_is_set_aside(tmp_path: Path) -> None:
    """Measured on one run: with the suite's repairs spent, the round reported "Acceptance test
    all_ops.spec.js uses fetch and expects listRes.status()", owned by testing and naming no criterion;
    two fix stages each answered that the locked suite was wrong and changed nothing."""
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "acceptance.json").write_text(json.dumps({"project": "app", "acceptance_dir": "acceptance"}))
    (tmp_path / "app" / "acceptance").mkdir(parents=True)
    (tmp_path / "app" / "acceptance" / "all_ops.spec.js").write_text("test('[AC-2] x', async () => {});\n")
    about_the_suite = SimpleNamespace(
        description="Acceptance test all_ops.spec.js uses fetch and expects listRes.status()", owner="testing",
        reproduction_steps="", expected_behavior="", actual_behavior="", affected_files=["app/acceptance/all_ops.spec.js"])
    about_the_product = SimpleNamespace(
        description="all_ops.spec.js fails: the routes answer 500", owner="backend",
        reproduction_steps="", expected_behavior="", actual_behavior="", affected_files=["app/src/routes.ts"])

    kept, set_aside = _defects_only_about([about_the_suite, about_the_product], ["AC-13"], tmp_path)

    assert set_aside == [about_the_suite] and kept == [about_the_product]


def test_a_criterion_beyond_repair_is_deferred_with_why(tmp_path: Path) -> None:
    """Measured on one run: the persistence criteria's only test was beyond repair, and each round still raised
    "the acceptance suite says this does not work yet" for them; the sprint was planned again three times for
    criteria no fix could prove. Deferred, the next measurement reads them as deferred, not failing."""
    from app.acceptance.criteria import number

    (tmp_path / ".project-directory").write_text("app\n")
    suite.save_criteria(tmp_path, number("# Brief\n## Features\n- Add a note\n- Notes survive a restart\n"))
    state = {"repository": SimpleNamespace(root_path=str(tmp_path))}

    nodes.defer_what_is_beyond_repair(state, ["AC-2"], ["`[AC-2] restart` fails because of an error in the test's own code"])

    reason = suite.deferred(tmp_path)["AC-2"]
    assert "cannot pass" in reason and "AC-1" not in suite.deferred(tmp_path)
    for word in BANNED:
        assert not re.search(rf"\b{word}\b", reason.lower()), word
