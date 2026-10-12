"""One fixer is shown every open defect of its role a measurement can close; only measurement closes them.

Batching cut a round of four defects owned by one role from four fix stages to
one. But the batch then marked every bundled defect fixed on the strength of
the first one's answer - whether the stage had touched it or not - and wrote
"verified by <command>" where a regression test was required.

Now a bundled defect stays open. The fix is measured, as every fix is; when
the cursor reaches a bundled defect, a measurement showing it resolved closes
it with no fixer, and one still failing goes to its own fixer. Only defects a
measurement can show resolved are bundled at all.
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from langgraph.checkpoint.memory import MemorySaver

from app.agents.specialists import SpecialistOutput
from app.graph.workflow import _bundle_co_defects, build_workflow_graph
from app.sprint import Defect, RemediationCycle


def _d(description, owner="ui_ux", **extra) -> Defect:
    return Defect(
        description=description, severity="major", reproduction_steps="r",
        expected_behavior="e", actual_behavior="a", owner=owner, **extra,
    )


ROUND = [
    _d("[AC-3] The view does not update", failing_criteria=["AC-3"]),
    _d("[AC-4] The count is wrong", failing_criteria=["AC-4"]),
    _d("Regression: `unit: tests/view.test.js › renders` passed before and fails now."),
    _d("An accessibility check of the page finds 1 serious rule broken: color-contrast.", source="page check"),
    _d("The layout feels cramped", source="test round"),
    _d("[AC-5] The service refuses a valid record", owner="backend", failing_criteria=["AC-5"]),
]


class TestWhatIsBundled:
    def test_the_role_s_defects_a_measurement_can_close(self):
        bundled = [position for position, _ in _bundle_co_defects(RemediationCycle(sprint_goal="g", defects=ROUND), 0)]

        assert bundled == [1, 2, 3]

    def test_not_one_no_measurement_can_show_resolved(self):
        bundled = [d.description for _, d in _bundle_co_defects(RemediationCycle(sprint_goal="g", defects=ROUND), 0)]

        assert "The layout feels cramped" not in bundled

    def test_not_another_role_s(self):
        bundled = [d.owner for _, d in _bundle_co_defects(RemediationCycle(sprint_goal="g", defects=ROUND), 0)]

        assert "backend" not in bundled


def _the_fix_stage_runs(tmp_path, answer: SpecialistOutput) -> tuple[dict, list[str]]:
    cycle = RemediationCycle(sprint_goal="g", defects=ROUND[:2])
    state = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "remediation": cycle,
        "defect_cursor": 0,
        "test_round": 2,
        "current_sprint_index": 0,
        "specialist_outputs": {},
    }
    asked: list[str] = []

    def gated(state, config, *, initial_request, **kwargs):
        asked.append(initial_request["messages"][-1]["content"])
        return {"__fix_result__": answer}

    with patch("app.graph.workflow.create_specialist_agent", return_value=MagicMock()), \
         patch("app.graph.workflow.build_defect_fix_request", return_value={"messages": [{"role": "user", "content": ""}]}), \
         patch("app.graph.workflow._what_the_last_failure_printed", return_value=""), \
         patch("app.graph.workflow._closed_if_an_earlier_fix_resolved_it", return_value=None), \
         patch("app.graph.workflow._what_the_ledger_confirms", return_value="npm test"), \
         patch("app.graph.acceptance_nodes.done_by_the_definition", return_value=[]), \
         patch("app.graph.engineering.before_a_fix", return_value=""), \
         patch("app.graph.engineering.after_a_fix", return_value=[]), \
         patch("app.graph.workflow._run_gated_agent", side_effect=gated):
        graph = build_workflow_graph(checkpointer=MemorySaver(), repo_root=str(tmp_path))
        update = graph.nodes["defect_remediation"].bound.invoke(
            state, {"configurable": {"thread_id": "t", "run_id": "r"}}
        )
    return update, asked


class TestOneFixStage:
    ANSWER = SpecialistOutput(
        changed_files=["app/src/view.js"], tests=["tests/view.test.js"],
        decisions=["Re-rendered the list after each change"],
    )

    def test_is_shown_the_bundled_defect(self, tmp_path):
        _, asked = _the_fix_stage_runs(tmp_path, self.ANSWER)

        assert "[AC-4] The count is wrong" in asked[0]
        assert "measures each one after your fix" in asked[0]

    def test_closes_only_the_defect_it_was_sent(self, tmp_path):
        update, _ = _the_fix_stage_runs(tmp_path, self.ANSWER)

        statuses = [d.status for d in update["remediation"].defects]
        assert statuses == ["fixed", "open"]

    def test_moves_on_to_the_bundled_defect_for_the_measurement_to_judge(self, tmp_path):
        update, _ = _the_fix_stage_runs(tmp_path, self.ANSWER)

        assert update["defect_cursor"] == 1


def test_the_new_words_name_no_product():
    from pathlib import Path

    source = Path("src/app/graph/workflow.py").read_text()
    start = source.index("Related failures owned by your role")
    text = source[start:source.index("\n", source.index("one still failing goes to its own fix"))].lower()
    for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox"):
        assert not re.search(rf"\b{re.escape(word)}\b", text), word
