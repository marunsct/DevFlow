"""A test round's proven problems quote the operator's brief, as the review's do.

The list handed to each round was built without the brief. One run's intake put
"Advanced editing (rich text), task due dates, ..." under deferred scope, and
with no brief to quote, the round was told "This project's own documents
require that a user can `edit` - "- Advanced editing (rich text) ..."".
Recorded as a defect nine times, it reached nine fix stages, and none of them
built the plain edit "Users can add, edit, delete tasks" asked for.
"""

from __future__ import annotations

from pathlib import Path

from app.agents.specialists import what_the_files_already_prove

INTAKE = """# Product Intake

## Success measures
- Users can add, delete and toggle tasks

## Deferred scope
- Advanced editing (rich text), task due dates, notifications
"""
BRIEF = "## Acceptance Criteria\n- Users can add, edit, delete tasks\n"


def _workspace(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "product_intake.md").write_text(INTAKE, encoding="utf-8")
    (tmp_path / "index.html").write_text('<html><body><script src="app.js"></script></body></html>', encoding="utf-8")
    (tmp_path / "app.js").write_text(
        "export function addTask(t) { return t; }\nexport function deleteTask(id) { return id; }\n"
        "export function toggleTask(id) { return id; }\n",
        encoding="utf-8",
    )
    return tmp_path


def test_the_round_is_told_what_the_brief_asked_for(tmp_path: Path) -> None:
    proven = what_the_files_already_prove(str(_workspace(tmp_path)), brief=BRIEF)

    (edit,) = [p for p in proven if "`edit`" in p]
    assert 'brief requires that a user can `edit` - "- Users can add, edit, delete tasks"' in edit
