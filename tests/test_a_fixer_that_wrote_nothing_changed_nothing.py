"""A fixer whose writes were all refused changed nothing, whatever the harness wrote beside it (LF.1444).

Measured on a medium run (deep review 2026-11-25, decisions finding 5): a fixer made two edits, both refused ("it would
add errors the language service is sure of ... Nothing was written"), and ran one `python3 -c` command, which the
harness saved as `tmp-inline-99274923.py` in the product's directory. "Changed nothing" was read from `git status` of
the whole workspace, so the fix was settled "its own tests still fail", and the next fixer read under "Earlier attempts
at this defect, as the harness measured them" the model's own "Changed both to call alembic.command.upgrade(...)" with a
measured verdict against it. Seven such attempts in the 16 full transcripts.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import ci
from app.agents import ledger
from app.sprint import NOTHING_WAS_CHANGED, Defect

PRODUCT = "task-management-dashboard"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


def _workspace(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "workspace"
    (root / PRODUCT / "task_management_dashboard").mkdir(parents=True)
    (root / PRODUCT / "task_management_dashboard" / "database.py").write_text("engine = None\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "-c", "user.email=h@example.com", "-c", "user.name=h", "add", "-A")
    _git(root, "-c", "user.email=h@example.com", "-c", "user.name=h", "commit", "-q", "-m", "base")
    return root, _git(root, "rev-parse", "HEAD")


def _the_harness_s_writes_during_the_fix(root: Path) -> None:
    (root / PRODUCT / "tmp-inline-99274923.py").write_text("import alembic.command\nprint(1)\n", encoding="utf-8")
    (root / PRODUCT / "test-results").mkdir()
    (root / PRODUCT / "test-results" / "unit.xml").write_text("<testsuites/>\n", encoding="utf-8")
    (root / ".harness").mkdir()
    (root / ".harness" / "ci.json").write_text("{}\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "decision_log.md").write_text("# Decisions\n", encoding="utf-8")


def test_the_harness_s_own_files_are_not_a_fixer_s_change(tmp_path):
    root, base = _workspace(tmp_path)
    _the_harness_s_writes_during_the_fix(root)

    assert ci.unchanged_since(root, base) is True


def test_a_product_file_written_is_still_a_change(tmp_path):
    root, base = _workspace(tmp_path)
    _the_harness_s_writes_during_the_fix(root)
    (root / PRODUCT / "task_management_dashboard" / "database.py").write_text("engine = 1\n", encoding="utf-8")

    assert ci.unchanged_since(root, base) is False


@pytest.fixture
def _ledger_on(monkeypatch):
    monkeypatch.setenv("DECISION_LEDGER", "on")


def test_the_next_fixer_is_not_told_of_a_change_that_was_never_written(_ledger_on):
    said = SimpleNamespace(changed_files=["task-management-dashboard/task_management_dashboard/database.py"],
                           decisions=["Changed both to call alembic.command.upgrade(alembic_cfg, 'head')"])
    attempt = ledger.attempt_record("defect_fix_1_2", said, NOTHING_WAS_CHANGED)
    defect = Defect(description="[AC-1] User registration and authentication (JWT-based) - the acceptance suite says "
                                "this does not work yet.", severity="major", reproduction_steps="run the suite",
                    expected_behavior="registration answers 201", actual_behavior="it answers 500", owner="backend",
                    attempts=[attempt])

    block = ledger.earlier_attempts(defect)

    assert "defect_fix_1_2" in block
    assert "wrote nothing" in block
    assert "Changed both" not in block
    assert "database.py" not in block
