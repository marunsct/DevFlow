"""In thorough delivery a failing unit run reaches the defect with its exception lines, not as a count (LF.1457).

Measured on one medium run in thorough delivery: the harness's own unit run held 9 of 32 failing, grouped by cause
(`InvalidRequestError: One or more mappers failed to initialize`, `AmbiguousForeignKeysError`), earlier
`'SQLiteTypeCompiler' object has no attribute 'visit_ARRAY'`; the opening requests of all 19 stages of the sprint
held the exception 0 times and "Unit tests: 23 of 32 pass" 11 times. The tester's defect, the only one about those
tests, read "SQLAlchemy ARRAY type blocks SQLite table creation in test fixtures". Fast delivery raises the unit run's
own defect with its causes; a tester's round had nothing of it.

The unit run and the tester's defects below are the run's own.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from langgraph.checkpoint.memory import MemorySaver

RECORD = json.loads((Path(__file__).parent / "fixtures" / "evidence_records" / "thorough_unit_run.json")
                    .read_text(encoding="utf-8"))
OUTPUT = RECORD["unit_run"]["output"]
FAILING = [name for name, outcome in RECORD["unit_run"]["unit"].items() if outcome == "failed"]


def _the_tester_s(*which: int) -> list:
    from app.agents.specialists import ReportedDefect

    return [ReportedDefect(**RECORD["tester_defects"][index]) for index in which]


def _a_thorough_round(root: str, tester_raised: list):
    """A thorough round on a green locked suite whose tester raised `tester_raised`, the unit run failing as it did."""
    from app.agents.specialists import SpecialistOutput
    from app.graph.workflow import build_workflow_graph

    def the_tester(state, config, **kwargs):
        return {"__test_result__": SpecialistOutput(changed_files=[], defects=tester_raised)}

    state = {
        "repository": SimpleNamespace(root_path=root),
        "milestone_plan": SimpleNamespace(selected_sprint_goal="Sign-in", milestone_scope=[], delegated_tasks=[]),
        "test_round": 0, "specialist_outputs": {}, "review_defects": [], "current_sprint_index": 0,
    }
    with patch("app.graph.acceptance_nodes.acceptance_for_round", return_value=("The suite's result.\n\n", [])), \
         patch("app.graph.acceptance_nodes.reopen_the_suite_for", return_value=None), \
         patch("app.graph.acceptance_nodes.beyond_repair", return_value=[]), \
         patch("app.graph.acceptance_nodes._failing_due", return_value=([], "npm run test:acceptance")), \
         patch("app.graph.workflow._run_unit_tests_procedurally", return_value=(False, OUTPUT)), \
         patch("app.graph.workflow._the_failing_unit_tests", return_value=FAILING), \
         patch("app.graph.acceptance_nodes.suite.is_locked", return_value=True), \
         patch("app.graph.acceptance_nodes.suite.last_result", return_value={"ran": True, "passed": 8, "failed": 13}), \
         patch("app.agents.specialists.what_the_files_already_prove", return_value=[]), \
         patch("app.graph.acceptance_nodes.interface_defects", return_value=[]), \
         patch("app.graph.acceptance_nodes.pack_contract_defects", return_value=[]), \
         patch("app.graph.acceptance_nodes.failing_due_defects", return_value=[]), \
         patch("app.graph.workflow._run_gated_agent", side_effect=the_tester):
        graph = build_workflow_graph(checkpointer=MemorySaver(), repo_root=root)
        update = graph.nodes["test_and_triage"].bound.invoke(state, {"configurable": {"thread_id": "t", "run_id": "r"}})
    return list(update["remediation"].defects)


def test_the_tester_s_defect_about_the_failing_tests_carries_the_exception_lines(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DELIVERY_MODE", "thorough")
    monkeypatch.delenv("MEASURED_ROUND_WHEN_RED", raising=False)

    defects = _a_thorough_round(str(tmp_path), _the_tester_s(0, 1))

    about_them = next(d for d in defects if d.description.startswith("SQLAlchemy ARRAY type"))
    assert "AmbiguousForeignKeysError" in about_them.actual_behavior
    assert "One or more mappers failed to initialize" in about_them.actual_behavior
    the_key = next(d for d in defects if d.description.startswith("JWT HMAC key"))
    assert "AmbiguousForeignKeysError" not in the_key.actual_behavior
    # One defect for the one cause: the round's carries it, the harness raises none of its own beside it.
    assert sum("AmbiguousForeignKeysError" in f"{d.description} {d.actual_behavior}" for d in defects) == 1


def test_a_round_that_raised_nothing_about_them_gets_the_harness_s_own_defect(tmp_path, monkeypatch) -> None:
    from app.graph.workflow import UNIT_TESTS_FAIL

    monkeypatch.setenv("DELIVERY_MODE", "thorough")
    monkeypatch.delenv("MEASURED_ROUND_WHEN_RED", raising=False)

    defects = _a_thorough_round(str(tmp_path), _the_tester_s(1))

    (own,) = [d for d in defects if d.description.startswith(UNIT_TESTS_FAIL)]
    assert "AmbiguousForeignKeysError" in own.description
