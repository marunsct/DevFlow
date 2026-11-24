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

    def after(root, base, stage_name, description, contested="", on_revert=None, **_):
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


def _two_apart(**first):
    import the_fix_stage

    return [the_fix_stage.a_defect("[AC-1] One is wrong", affected_files=["src/one.js"], **first),
            the_fix_stage.a_defect("[AC-2] Two is wrong", affected_files=["src/two.js"])]


class TestABatchKeepsTheFixCycleSBoundsAndRecords:
    """Batched fixes skipped the call cap, the check after a write and the attempt record: a defect that
    had spent its calls was still sent, and a batched attempt left nothing for the cap or the next fixer."""

    @pytest.fixture(autouse=True)
    def _on(self, monkeypatch):
        monkeypatch.setenv("DEFECT_CALL_CAP", "on")
        monkeypatch.setenv("VERIFY_AFTER_WRITE", "on")

    def test_a_defect_that_spent_its_calls_is_not_sent(self, tmp_path):
        import the_fix_stage

        spent = _two_apart(attempts=[{"stage": "defect_fix_1_0", "did": "x", "outcome": "left open", "calls": 60}])
        update, seen = the_fix_stage.run(tmp_path, the_fix_stage.a_state(tmp_path, *spent), side_by_side=True)

        assert update.get("fixes_tried") == ["defect_fix_2_0"] and "fix_batch" not in update
        assert seen.agent_models == []

    def test_a_batch_is_sent_with_its_start(self, tmp_path):
        import the_fix_stage

        update, _ = the_fix_stage.run(tmp_path, the_fix_stage.a_state(tmp_path, *_two_apart()), side_by_side=True)

        assert update["stage"] == "defect_fix_parallel" and update["fix_batch"] == [0, 1]
        assert update["fix_batch_started"], "the moment the batch's calls are counted from"

    def test_each_fixer_s_writes_are_checked_by_its_own_defect_s_tests(self, tmp_path):
        import the_fix_stage

        from app.graph import verify_after_write

        def the_check_after_a_write(stage_name):
            found = verify_after_write._the_check("r", stage_name)
            assert found is not None, "a check is watching this fixer's own stage"
            return found[0]()

        state = the_fix_stage.a_state(tmp_path, *_two_apart(), __fix_index=1)
        _, seen = the_fix_stage.run(tmp_path, state, node="defect_fix_worker", during=the_check_after_a_write)

        assert seen.tests_checked == [(str(tmp_path), state["remediation"].defects[1])]

    def test_each_batched_attempt_is_recorded_with_its_calls_since_the_batch_began(self, tmp_path, monkeypatch):
        import the_fix_stage

        from app.agents.specialists import SpecialistOutput

        counted = []
        monkeypatch.setattr("app.graph.defect_budget.calls_in",
                            lambda run_id, stage, since: counted.append((stage, since)) or 7)
        answer = SpecialistOutput(changed_files=["src/one.js"], tests=["t"])
        state = the_fix_stage.a_state(
            tmp_path, *_two_apart(), fix_batch=[0, 1], fix_base_commit="base", fix_batch_started="2026-01-01T00:00:00",
            specialist_outputs={"defect_fix_2_0": answer, "defect_fix_2_1": answer},
        )

        update, _ = the_fix_stage.run(tmp_path, state, node="defect_fix_gather")

        assert [[a.get("calls") for a in d.attempts] for d in update["remediation"].defects] == [[7], [7]]
        assert counted == [("defect_fix_2_0", "2026-01-01T00:00:00"), ("defect_fix_2_1", "2026-01-01T00:00:00")]
