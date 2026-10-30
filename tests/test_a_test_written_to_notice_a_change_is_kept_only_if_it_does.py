"""A test added to notice a deliberate change is kept only if it fails with the change and passes without it (plan item 13c, behind `MUTATION_TEST_RETENTION`).

Measured: a mutation finding's fix stage left whatever the fixer wrote in the
product - the harness checked that some unit test failed with the change, and
nothing about the tests the fix added. A test that fails on the unchanged
product ships failing; one that passes both ways asserts nothing about the
change. With the switch on, test files the fix added that fail on the product
as it is are put back before the change is measured, and test files it created
that notice nothing are put back after; a file it only edited is never taken
apart. Off, nothing is put back.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app import ci
from app.acceptance import mutation_guided, mutation_retention
from app.agents.specialists import SpecialistOutput
from app.sprint import RemediationCycle

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
RUN, STAGE = "run-1", "defect_fix_2_0"


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("MUTATION_TEST_RETENTION", "on")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / ".gitignore").write_text(".harness/\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "calc.py").write_text("def over(a, b):\n    return a > b\n", encoding="utf-8")
    (tmp_path / "tests" / "test_old.py").write_text("def test_old():\n    assert True\n", encoding="utf-8")
    ci.commit(tmp_path, "base")
    ci.save(tmp_path, ci.Snapshot(label="before", unit={"test_old": "passed", "test_broken_before": "failed"}, unit_ran=True))
    mutation_retention.remember(RUN, STAGE, tmp_path)
    return tmp_path


def _the_fix_wrote(root: Path, files: dict[str, str], unit: dict[str, str]) -> None:
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8")
    ci.save(root, ci.Snapshot(label="after", commit=ci.commit(root, "Fix: x"), unit=unit, unit_ran=True))


def test_a_test_that_fails_on_the_unchanged_product_is_put_back_and_the_change_is_not_measured(workspace):
    _the_fix_wrote(workspace, {"tests/test_new.py": "def test_new():\n    assert over(1, 2)\n"},
                   {"test_old": "passed", "test_broken_before": "failed", "test_new": "failed"})
    asked: list[int] = []

    settled, note = mutation_retention.judged(workspace, RUN, STAGE, lambda: asked.append(1) or True)

    assert settled is False and asked == []
    assert not (workspace / "tests" / "test_new.py").exists()
    assert (workspace / "tests" / "test_old.py").exists()
    assert "failed on the product as it is" in note and "test_new" in note and "tests/test_new.py" in note
    assert not BANNED.search(note), note


def test_a_failure_there_before_the_fix_is_not_the_fix_s(workspace):
    _the_fix_wrote(workspace, {"tests/test_new.py": "def test_new():\n    assert True\n"},
                   {"test_old": "passed", "test_broken_before": "failed", "test_new": "passed"})

    settled, note = mutation_retention.judged(workspace, RUN, STAGE, lambda: True)

    assert settled is True and note == ""
    assert (workspace / "tests" / "test_new.py").exists()


def test_a_test_file_that_notices_nothing_is_put_back_when_the_fix_created_it(workspace):
    _the_fix_wrote(workspace, {"tests/test_new.py": "def test_new():\n    assert True\n"},
                   {"test_old": "passed", "test_broken_before": "failed", "test_new": "passed"})

    settled, note = mutation_retention.judged(workspace, RUN, STAGE, lambda: False)

    assert settled is False and not (workspace / "tests" / "test_new.py").exists()
    assert "noticed nothing" in note and "tests/test_new.py" in note
    assert not BANNED.search(note), note


def test_a_file_the_fix_only_edited_is_never_taken_apart(workspace):
    _the_fix_wrote(workspace, {"tests/test_old.py": "def test_old():\n    assert True\n\n\ndef test_more():\n    assert True\n"},
                   {"test_old": "passed", "test_more": "passed", "test_broken_before": "failed"})

    settled, note = mutation_retention.judged(workspace, RUN, STAGE, lambda: False)

    assert settled is False and note == ""
    assert "test_more" in (workspace / "tests" / "test_old.py").read_text(encoding="utf-8")


def test_the_product_is_never_put_back(workspace):
    _the_fix_wrote(workspace, {"src/calc.py": "def over(a, b):\n    return a >= b\n",
                               "tests/test_new.py": "def test_new():\n    assert False\n"},
                   {"test_old": "passed", "test_broken_before": "failed", "test_new": "failed"})

    mutation_retention.judged(workspace, RUN, STAGE, lambda: True)

    assert "a >= b" in (workspace / "src" / "calc.py").read_text(encoding="utf-8")
    assert not (workspace / "tests" / "test_new.py").exists()


def test_off_nothing_is_put_back_and_the_check_is_the_only_answer(workspace, monkeypatch):
    monkeypatch.setenv("MUTATION_TEST_RETENTION", "off")
    _the_fix_wrote(workspace, {"tests/test_new.py": "def test_new():\n    assert False\n"},
                   {"test_old": "passed", "test_broken_before": "failed", "test_new": "failed"})

    assert mutation_retention.judged(workspace, RUN, STAGE, lambda: False) == (False, "")
    assert (workspace / "tests" / "test_new.py").exists()


def test_a_stage_the_harness_did_not_note_is_settled_as_before(workspace):
    assert mutation_retention.judged(workspace, RUN, "defect_fix_9_9", lambda: True) == (True, "")


def test_a_finding_s_settlement_puts_back_what_fails_and_records_why(workspace):
    from app.graph.workflow import _settle_the_fix

    finding = mutation_guided.defect({"file": "src/calc.py", "line": 2, "column": 13, "original": ">",
                                      "replacement": "<=", "text": "    return a > b"})
    cycle = RemediationCycle(sprint_goal="g", defects=[finding])
    state = {"repository": SimpleNamespace(root_path=str(workspace)), "specialist_outputs": {}, "test_round": 2}
    _the_fix_wrote(workspace, {"tests/test_new.py": "def test_new():\n    assert False\n"},
                   {"test_old": "passed", "test_broken_before": "failed", "test_new": "failed"})

    with patch("app.observability.transcript._run_id_from_config", return_value=RUN), \
         patch.object(mutation_guided, "settled", return_value=True) as measured:
        update, _ = _settle_the_fix(state, cycle, 0, STAGE, SpecialistOutput(changed_files=["tests/test_new.py"]),
                                    measured="after " + STAGE)

    left = update["remediation"].defects[0]
    assert left.status == "open" and not measured.called
    assert not (workspace / "tests" / "test_new.py").exists()


def test_the_fix_stage_notes_what_a_finding_s_fix_starts_from_and_no_other_does(workspace):
    from app.graph import defect_fix_modes

    other = mutation_guided.defect({"file": "src/calc.py", "line": 2, "column": 13, "original": ">",
                                    "replacement": "<=", "text": "    return a > b"}).model_copy(update={"source": "test round"})
    state = {"repository": SimpleNamespace(root_path=str(workspace)), "test_round": 2, "current_sprint_index": 0}
    config = {"configurable": {"app_run_id": RUN}}
    mutation_retention._forget(RUN, STAGE)

    defect_fix_modes.begin(state, config, RemediationCycle(sprint_goal="g", defects=[other]), 0, STAGE)
    assert mutation_retention._forget(RUN, STAGE) is None

    finding = other.model_copy(update={"source": "mutation"})
    defect_fix_modes.begin(state, config, RemediationCycle(sprint_goal="g", defects=[finding]), 0, STAGE)
    noted = mutation_retention._forget(RUN, STAGE)
    assert noted and noted["base"] == ci.head(workspace) and noted["failing"] == {"test_broken_before"}


def test_the_finding_s_settlement_asks_the_retention_rule_first():
    import inspect

    from app.graph import workflow

    assert "mutation_retention.judged(" in inspect.getsource(workflow._a_mutation_finding_settled)


def test_the_switch_is_an_experiment_that_ships_off():
    from app import switches

    assert "MUTATION_TEST_RETENTION" in switches.EXPERIMENTS and "MUTATION_TEST_RETENTION" not in switches.EXPERIMENTS_ON
    assert mutation_retention.ON_BY_DEFAULT is False
