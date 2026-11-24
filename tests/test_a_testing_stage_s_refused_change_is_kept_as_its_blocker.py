"""A testing work order's refused product change is kept as its blocker, so it stops trying it (LF.1310).

Measured over nine runs: "'X' is product code, and this is the testing work order ..." was returned 54 times, up to
15 in one run and 8 in another. The testing builder found a real fault in the product while writing its tests, tried
to fix it, was refused, and tried again; the refusal asked it to name the fault in `blockers`, the local model kept
trying the change, and every refusal cost a model call.
"""
from __future__ import annotations

import json
import re
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.agents.specialists import SpecialistOutput
from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask
from app.graph import workflow
from app.tools.repository import (
    RepositoryToolError, delete_approved_artifact, edit_approved_artifact, just_asking, write_approved_artifact,
)

BACKEND = "specialist_backend_0"
TESTING = "specialist_testing_1"
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

ROUTER = "def list_notes():\n    return []\n"


def a_workspace(root: Path) -> Path:
    (root / "api").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "api" / "routes.py").write_text(ROUTER)
    (root / "api" / "settings.py").write_text("DEBUG = False\n")
    (root / "tests" / "test_notes.py").write_text("def test_notes_are_listed():\n    assert True\n")
    return root


def a_plan() -> MilestonePlanOutput:
    return MilestonePlanOutput(
        selected_sprint_goal="Sprint 1: notes",
        delegated_tasks=[
            SpecialistTask(specialist_role="backend", task_description="Serve the saved notes",
                           files=["api/routes.py"]),
            SpecialistTask(specialist_role="testing", task_description="Unit tests of the notes",
                           files=["tests/test_notes.py"]),
        ],
    )


def a_sprint(root: Path, **more) -> dict:
    return {
        "repository": SimpleNamespace(root_path=str(root)),
        "milestone_plan": a_plan(),
        "drafted_for_plan": True,
        "specialist_outputs": {BACKEND: SpecialistOutput(changed_files=["api/routes.py"])},
        "specialist_task_index": 1,
        **more,
    }


def in_stage(monkeypatch, stage: dict) -> None:
    monkeypatch.setattr("app.observability.transcript._stage_from_config", lambda fallback: stage["now"])


@pytest.fixture()
def builders(monkeypatch):
    """The builder stages, their model stubbed: the testing stage tries what its model tried, each builder's request
    is kept by stage."""
    handed: dict[str, str] = {}
    stage = {"now": ""}
    tries: dict[str, list] = {}

    def gated(state, config, *, stage_name, initial_request, output_key, **kwargs):
        handed[stage_name] = initial_request["messages"][-1]["content"]
        stage["now"] = stage_name
        for attempt in tries.get(stage_name, []):
            try:
                attempt(Path(state["repository"].root_path))
            except RepositoryToolError:
                pass
        stage["now"] = ""
        return {output_key: SpecialistOutput(changed_files=["tests/test_notes.py"]), "stage": kwargs.get("next_stage")}

    monkeypatch.setenv("DELIVERY_MODE", "fast")
    in_stage(monkeypatch, stage)
    monkeypatch.setattr(workflow, "build_specialist_task_request",
                        lambda *a, **k: {"messages": [{"role": "user", "content": "the work order"}]})
    monkeypatch.setattr(workflow, "create_specialist_agent", lambda role, *a, **k: SimpleNamespace(role=role))
    monkeypatch.setattr(workflow, "_run_gated_agent", gated)
    monkeypatch.setattr("app.server.runtime_settings.effective_settings",
                        lambda: SimpleNamespace(execution_mode="linear"))
    return SimpleNamespace(handed=handed, tries=tries)


def dispatch(root: Path, state: dict) -> dict:
    graph = workflow.build_workflow_graph(checkpointer=MemorySaver(), repo_root=str(root))
    return graph.nodes["specialist_dispatch"].bound.invoke(state, {"configurable": {"thread_id": "t"}})


def merged(state: dict, update: dict) -> dict:
    after = {**state, **update}
    for key in ("specialist_outputs", "unfinished_orders"):
        if key in update:
            after[key] = {**(state.get(key) or {}), **update[key]}
    return after


def fixing_the_router(root: Path) -> None:
    edit_approved_artifact(root, "api/routes.py", "return []", "return saved_notes()")


# -- the refusal ----------------------------------------------------------------------------------------------------


def test_the_first_refusal_says_the_change_is_recorded_and_will_reach_the_builder(tmp_path, monkeypatch):
    root = a_workspace(tmp_path)
    in_stage(monkeypatch, {"now": TESTING})

    with pytest.raises(RepositoryToolError) as refused:
        fixing_the_router(root)

    said = str(refused.value)
    assert "recorded as this stage's blocker" in said and "builder whose work order owns 'api/routes.py'" in said
    assert "write the test against the interface" in said and "Nothing was written." in said
    assert (root / "api" / "routes.py").read_text() == ROUTER


def test_a_second_refusal_of_the_same_file_in_the_stage_is_one_short_line(tmp_path, monkeypatch):
    root = a_workspace(tmp_path)
    in_stage(monkeypatch, {"now": TESTING})
    with pytest.raises(RepositoryToolError) as first:
        fixing_the_router(root)

    with pytest.raises(RepositoryToolError) as second:
        write_approved_artifact(root, "api/routes.py", "def list_notes():\n    return saved_notes()\n")

    said = str(second.value)
    assert "already recorded as this stage's blocker" in said and "Nothing was written." in said
    assert len(said) < len(str(first.value)) / 2


def test_another_file_or_another_testing_stage_is_told_in_full(tmp_path, monkeypatch):
    root = a_workspace(tmp_path)
    stage = {"now": TESTING}
    in_stage(monkeypatch, stage)
    with pytest.raises(RepositoryToolError):
        fixing_the_router(root)

    with pytest.raises(RepositoryToolError) as other_file:
        edit_approved_artifact(root, "api/settings.py", "DEBUG = False", "DEBUG = True")
    stage["now"] = "specialist_testing_2"
    with pytest.raises(RepositoryToolError) as other_stage:
        fixing_the_router(root)

    assert "recorded as this stage's blocker, with" in str(other_file.value)
    assert "recorded as this stage's blocker, with" in str(other_stage.value)


def test_asking_whether_a_write_would_be_refused_records_nothing(tmp_path, monkeypatch):
    root = a_workspace(tmp_path)
    in_stage(monkeypatch, {"now": TESTING})
    with just_asking(), pytest.raises(RepositoryToolError):
        fixing_the_router(root)

    with pytest.raises(RepositoryToolError) as refused:
        fixing_the_router(root)

    assert "already recorded" not in str(refused.value)


def test_a_test_round_s_refusal_is_as_before(tmp_path, monkeypatch):
    root = a_workspace(tmp_path)
    in_stage(monkeypatch, {"now": "test_round_0"})
    with pytest.raises(RepositoryToolError):
        fixing_the_router(root)

    with pytest.raises(RepositoryToolError) as again:
        fixing_the_router(root)

    assert "this is a test round" in str(again.value) and "blocker" not in str(again.value)
    assert not (root / ".harness" / "testing-blockers.json").exists()


def test_the_new_words_avoid_the_banned_words(tmp_path, monkeypatch, builders):
    from app.tools import testing_blockers

    root = a_workspace(tmp_path)
    builders.tries[TESTING] = [fixing_the_router]
    state = merged(a_sprint(root), dispatch(root, a_sprint(root)))
    note = dispatch(root, state)["unfinished_orders"][BACKEND]
    in_stage(monkeypatch, {"now": "specialist_testing_3"})
    told = []
    for _ in range(2):
        with pytest.raises(RepositoryToolError) as refused:
            edit_approved_artifact(root, "api/settings.py", "DEBUG = False", "DEBUG = True")
        told.append(str(refused.value))

    assert not BANNED.findall(" ".join([*told, note, testing_blockers.as_blocker("api/routes.py", "")]))


# -- the blocker, and the builder that owns the file ------------------------------------------------------------------


def test_the_refused_change_is_among_the_testing_stage_s_blockers(tmp_path, builders):
    root = a_workspace(tmp_path)
    builders.tries[TESTING] = [fixing_the_router, fixing_the_router]

    update = dispatch(root, a_sprint(root))

    blockers = update["specialist_outputs"][TESTING].blockers
    assert len(blockers) == 1
    assert "`api/routes.py`" in blockers[0] and "return saved_notes()" in blockers[0]


def test_the_refused_change_reaches_the_next_request_of_the_builder_that_owns_the_file(tmp_path, builders):
    root = a_workspace(tmp_path)
    builders.tries[TESTING] = [fixing_the_router]
    state = merged(a_sprint(root), dispatch(root, a_sprint(root)))
    state = merged(state, dispatch(root, state))  # every builder has finished

    dispatch(root, state)

    asked = builders.handed[BACKEND]
    assert "What the testing work order needs from your files" in asked
    assert "`api/routes.py`" in asked and "return saved_notes()" in asked


def test_the_owner_is_sent_it_once_an_attempt(tmp_path, builders):
    root = a_workspace(tmp_path)
    builders.tries[TESTING] = [fixing_the_router]
    state = merged(a_sprint(root), dispatch(root, a_sprint(root)))
    sent = dispatch(root, state)
    state = merged(state, sent)
    state = merged(state, dispatch(root, state))  # the owner ran again

    after = dispatch(root, state)

    assert (sent["stage"], after["stage"]) == ("specialist_dispatch", "ci_gate")


def test_a_file_no_work_order_owns_stays_a_blocker_and_the_build_goes_on(tmp_path, builders):
    root = a_workspace(tmp_path)
    builders.tries[TESTING] = [lambda r: edit_approved_artifact(r, "api/settings.py", "DEBUG = False", "DEBUG = True")]
    state = merged(a_sprint(root), dispatch(root, a_sprint(root)))

    update = dispatch(root, state)

    assert update["stage"] == "ci_gate" and not update.get("unfinished_orders")
    assert "`api/settings.py`" in state["specialist_outputs"][TESTING].blockers[0]


def test_a_testing_stage_writing_its_own_tests_is_as_before(tmp_path, builders):
    root = a_workspace(tmp_path)
    builders.tries[TESTING] = [lambda r: write_approved_artifact(
        r, "tests/test_notes.py", "def test_notes_are_listed():\n    assert list_notes() == []\n")]
    state = merged(a_sprint(root), dispatch(root, a_sprint(root)))

    update = dispatch(root, state)

    assert "list_notes()" in (root / "tests" / "test_notes.py").read_text()
    assert state["specialist_outputs"][TESTING].blockers == []
    assert update["stage"] == "ci_gate"


def test_a_delete_refused_is_recorded_as_the_file_deleted(tmp_path, builders):
    root = a_workspace(tmp_path)
    builders.tries[TESTING] = [lambda r: delete_approved_artifact(r, "api/routes.py")]

    update = dispatch(root, a_sprint(root))

    assert "the file deleted" in update["specialist_outputs"][TESTING].blockers[0]
    assert (root / "api" / "routes.py").is_file()


# -- the ledger and `loop.sh effects` -------------------------------------------------------------------------------


def test_the_recorded_and_sent_changes_are_in_the_ledger_and_the_effects_report(tmp_path, builders, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr("app.observability.transcript._run_id_from_config", lambda: "run-testing-blockers")
    root = a_workspace(tmp_path / "workspace")
    builders.tries[TESTING] = [fixing_the_router, fixing_the_router]
    state = merged(a_sprint(root), dispatch(root, a_sprint(root)))
    dispatch(root, state)
    records = [json.loads(line) for line in
               (tmp_path / "data" / "transcripts" / "run-testing-blockers.jsonl").read_text().splitlines()]
    # What the transcript keeps of the two refusals the model was given.
    records += [{"kind": "tool_result", "stage": TESTING, "raised": "RepositoryToolError: 'api/routes.py' is product "
                 "code, and this is the testing work order: ..."},
                {"kind": "tool_result", "stage": TESTING, "raised": "RepositoryToolError: 'api/routes.py' is product "
                 "code, refused to this testing work order before and already recorded as this stage's blocker"}]

    effects = runpy.run_path(str(Path(__file__).resolve().parent.parent / "scripts" / "loop" / "effects.py"))["effects"]
    lines = "\n".join(effects(records, ""))

    assert "   1  LF.1310 a testing stage's refused product change recorded as its blocker" in lines
    assert "   1  LF.1310 a recorded change sent to the builder that owns the file" in lines
    assert "product-code refusals per testing stage: specialist_testing_1 2" in lines
