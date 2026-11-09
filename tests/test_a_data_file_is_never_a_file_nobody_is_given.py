"""A data file the product writes is never "a file nobody is given", on any stack (harness review HR2.P.6).

The data-file rule needed a pack's data-directory variable, so a stack with no pack was sent back for its
`notes.json` - ~35 resends since 11-01. A seed file the specification's file plan lists is still flagged.
"""
from __future__ import annotations

from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask
from app.analysis import work_orders

SPEC = """# Technical specification

## File Plan
- notes/notes_api/app.py: the service
- notes/seed/fixtures.json: the seed records the product ships with

## Configuration
- variable: DATA_DIR; default: data/
"""


def _plan() -> MilestonePlanOutput:
    return MilestonePlanOutput(selected_sprint_goal="Notes", delegated_tasks=[SpecialistTask(
        specialist_role="backend", title="Service", task_description="Build it.", files=["notes/notes_api/app.py"],
        test_cases=["given a note, when added, then it is listed"])])


def _workspace(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technical_specification.md").write_text(SPEC)
    return tmp_path


def test_a_pack_less_scope_naming_the_data_file_gets_no_problem(tmp_path) -> None:
    root = _workspace(tmp_path)
    missing = work_orders._files_the_sprint_names_and_nobody_is_given(
        "The service writes notes.json under DATA_DIR and serves `app.py`.", _plan().delegated_tasks, root, "notes")
    assert "notes.json" not in missing


def test_a_seed_file_the_file_plan_lists_is_still_flagged(tmp_path) -> None:
    root = _workspace(tmp_path)
    missing = work_orders._files_the_sprint_names_and_nobody_is_given(
        "Load the seed from fixtures.json at start.", _plan().delegated_tasks, root, "notes")
    assert "fixtures.json" in missing
