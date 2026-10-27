"""In parallel mode, defects whose files do not meet are fixed side by side.

Sprint 1 of one run spent three hours on eleven fix stages one after another,
against a model API that served several requests at once. Defects are now
batched as work orders are staggered (`_that_do_not_share_a_file`), at most
`max_parallel()` together; the workspace is committed once before a batch and
measured once after it, and a batch that broke what passed before is reverted
whole and its defects fixed one at a time. Linear mode is unchanged.
"""

from __future__ import annotations

import dataclasses
import logging
from types import SimpleNamespace
from typing import Any

import pytest

from app.graph import workflow
from app.graph.workflow import _defects_to_fix_together, start_workflow
from test_graph_routing import (  # noqa: F401 - `agents` is a fixture
    ScriptedAgents,
    _approved_review,
    _defect,
    _document,
    _graph,
    _milestone,
    _milestone_review,
    _repository,
    _script_through_architecture,
    _security_review,
    _specialist,
    _sprint_plan,
    agents,
    responds_with,
)


@pytest.fixture(autouse=True)
def nothing_is_proven(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.agents.specialists.what_the_files_already_prove", lambda *a, **k: [])


@pytest.fixture
def parallel(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import config

    real = config.load_settings()
    monkeypatch.setattr(
        config, "load_settings", lambda *args, **kwargs: dataclasses.replace(real, execution_mode="parallel"),
    )


def _at(defect: Any, *files: str) -> Any:
    return defect.model_copy(update={"affected_files": list(files)})


THREE = [
    _at(_defect(owner="backend", description="API 500"), "src/api.py"),
    _at(_defect(owner="database", description="Missing index"), "src/db.py").model_copy(update={"actual_behavior": "Query took 1200ms without index"}),
    _at(_defect(owner="ui_ux", description="Broken layout"), "src/page.tsx").model_copy(update={"actual_behavior": "Text clipped at small viewport"}),
]


def _script(agents: ScriptedAgents, defects: list[Any], *, fixes: int = 1) -> None:
    _script_through_architecture(agents, _approved_review())
    agents.script("scrum_master", [responds_with(_sprint_plan())])
    agents.script("technical_lead", [responds_with(_milestone("backend"))])
    agents.script("specialist_backend", [responds_with(_specialist())] + [responds_with(_specialist(tests=["t-api"]))] * fixes)
    agents.script("specialist_database", [responds_with(_specialist(tests=["t-db"]))] * fixes)
    agents.script("specialist_ui_ux", [responds_with(_specialist(tests=["t-ui"]))] * fixes)
    agents.script("specialist_testing", [responds_with(_specialist(defects=defects)), responds_with(_specialist())])
    agents.script("milestone_reviewer", [responds_with(_milestone_review())])
    agents.script("security_reviewer", [responds_with(_security_review())])


def test_defects_in_different_files_are_fixed_in_one_batch(agents, parallel, tmp_path, caplog):
    _script(agents, THREE)
    caplog.set_level(logging.INFO, logger="app.graph.workflow")

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-batch")

    assert state["stage"] == "complete", state.get("error")
    assert [d.status for d in state["remediation"].defects] == ["fixed", "fixed", "fixed"]
    assert [d.regression_test for d in state["remediation"].defects] == ["t-api", "t-db", "t-ui"]
    assert any("Fixing 3 defects side by side" in r.getMessage() for r in caplog.records)
    assert not state.get("fix_batch")


def test_a_batch_that_broke_what_passed_is_reverted_and_its_defects_fixed_alone(agents, parallel, tmp_path, monkeypatch):
    from app.graph import engineering

    measured: list[str] = []

    def after(root, base, stage_name, description, contested=""):
        measured.append(stage_name)
        return ["[AC-1] lists notes"] if stage_name.endswith("_batch") else []

    monkeypatch.setattr(engineering, "before_a_fix", lambda root, stage_name: "base")
    monkeypatch.setattr(engineering, "after_a_fix", after)
    _script(agents, THREE, fixes=2)

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-batch-reverted")

    assert state["stage"] == "complete", state.get("error")
    assert measured[0].endswith("_batch")
    assert sorted(measured[1:4]) == ["defect_fix_1_0", "defect_fix_1_1", "defect_fix_1_2"], measured
    assert all(d.status == "fixed" for d in state["remediation"].defects)
    assert "A batch of fixes including this one was reverted" in state["remediation"].defects[0].actual_behavior


def test_linear_mode_still_fixes_one_at_a_time(agents, tmp_path, caplog):
    _script(agents, THREE)
    caplog.set_level(logging.INFO, logger="app.graph.workflow")

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-linear-fixes")

    assert state["stage"] == "complete", state.get("error")
    assert all(d.status == "fixed" for d in state["remediation"].defects)
    assert not any("side by side" in r.getMessage() for r in caplog.records)


def _cycle(*files_per_defect: tuple[str, ...], owner: str = "backend") -> Any:
    defects = [
        SimpleNamespace(
            affected_files=list(files), description=f"defect {i}", status="open", owner=owner,
            expected_behavior="", actual_behavior="", failing_criteria=[],
        )
        for i, files in enumerate(files_per_defect)
    ]
    return SimpleNamespace(defects=defects)


@pytest.fixture
def no_bundles(monkeypatch):
    monkeypatch.setattr(workflow, "_bundle_co_defects", lambda cycle, index: [])


def test_two_defects_naming_one_file_are_never_fixed_together(no_bundles):
    cycle = _cycle(("src/a.py",), ("src/b.py",), ("src/a.py",))

    assert _defects_to_fix_together(cycle, [0, 1, 2]) == [0, 1]


def test_at_most_the_configured_number_go_at_once(no_bundles, monkeypatch):
    cycle = _cycle(*[(f"src/f{i}.py",) for i in range(9)])

    assert len(_defects_to_fix_together(cycle, list(range(9)))) == 6
    monkeypatch.setenv("HARNESS_MAX_PARALLEL", "2")
    assert _defects_to_fix_together(cycle, list(range(9))) == [0, 1]


def test_a_defect_bundled_into_another_s_fix_is_not_fixed_beside_it(monkeypatch):
    cycle = _cycle(("src/a.py",), ("src/b.py",), ("src/c.py",))
    monkeypatch.setattr(
        workflow, "_bundle_co_defects",
        lambda c, index: [(2, c.defects[2])] if index == 0 else [],
    )

    chosen = _defects_to_fix_together(cycle, [0, 1, 2])

    assert 0 in chosen and 2 not in chosen


def test_the_ceiling_is_read_from_the_environment(monkeypatch):
    monkeypatch.delenv("HARNESS_MAX_PARALLEL", raising=False)
    assert workflow.max_parallel() == 6
    monkeypatch.setenv("HARNESS_MAX_PARALLEL", "1")
    assert workflow.max_parallel() == 1 and not workflow._fixes_run_side_by_side()
    monkeypatch.setenv("HARNESS_MAX_PARALLEL", "many")
    assert workflow.max_parallel() == 6


def test_a_fixer_in_a_batch_that_pauses_resumes_its_own_defect(agents, parallel, tmp_path):
    from test_graph_routing import approve_write_decision, pause_for_approval

    from app.graph.workflow import resume_pending_approval

    _script(agents, THREE)
    agents.script("specialist_database", [pause_for_approval(), responds_with(_specialist(tests=["t-db"]))])
    graph = _graph()

    state = start_workflow(graph, _document(), _repository(tmp_path), "run-batch-pause")
    for _ in range(6):
        if not str(state.get("stage", "")).startswith("awaiting_approval:"):
            break
        assert state["stage"] == "awaiting_approval:defect_fix_1_1"
        state = resume_pending_approval(graph, "run-batch-pause", approve_write_decision())

    assert state["stage"] == "complete", state.get("error")
    assert [d.regression_test for d in state["remediation"].defects] == ["t-api", "t-db", "t-ui"]
    assert len(agents.requests["specialist_backend"]) == 2, "the backend fixer ran once, beside the paused one"


def test_a_batch_keeps_the_fix_cycle_s_bounds_and_records():
    """Batched fixes skipped the call cap, the check after a write and the attempt record: a defect that
    had spent its calls was still sent, and a batched attempt left nothing for the cap or the next fixer."""
    import inspect as _inspect

    from app.graph import workflow as _workflow

    source = _inspect.getsource(_workflow)
    batch = source[source.index("    def _the_next_fix_batch("):source.index("    def defect_fix_worker_node(")]
    worker = source[source.index("    def defect_fix_worker_node("):source.index("    def defect_fix_gather_node(")]
    gather = source[source.index("    def defect_fix_gather_node("):source.index("    def _the_security_review(")]
    assert "defect_budget.spent_out(cycle, index)" in batch and '"fix_batch_started": defect_budget.now()' in batch
    assert "verify_after_write.watching(" in worker
    assert "_with_the_attempt(" in gather and 'state.get("fix_batch_started")' in gather
