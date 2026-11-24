"""An unfinished build goes back to its builders, not to fixers (LF.1299).

Measured on a medium run in thorough delivery: sprint 2's builders handed over unfinished work (one wrote a single
file, another made one edit), and the first test round raised eleven defects, most saying the feature was not built - a
service file that did not exist, a route answering 404, a router whose every endpoint returned an empty result. The
first fix stage, bounded for a fault, read seventy times and left its defect open; the run recovered only after three
exhausted rounds, by planning the whole sprint again.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.agents.specialists import SpecialistOutput
from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask
from app.graph import unfinished_build, workflow
from workflow_node_stubs import run_a_test_round
from workflow_nodes import reported

BACKEND = "specialist_backend_0"
PAGE = "specialist_ui_ux_1"
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

#: A router the builder left as it began: every route answers an empty value.
STUB_ROUTER = '''from fastapi import APIRouter

router = APIRouter()


@router.get("/notes")
def list_notes():
    return []


@router.get("/notes/{note_id}")
def read_note(note_id: int):
    return {}
'''

BUILT_ROUTER = '''from fastapi import APIRouter, HTTPException

from api.reminders import create_reminder, saved_notes

router = APIRouter()


@router.get("/notes")
def list_notes():
    return saved_notes()


@router.post("/notes/{note_id}/remind", status_code=201)
def remind(note_id: int, at: str):
    if note_id not in saved_notes():
        raise HTTPException(404)
    return create_reminder(note_id, at)
'''

BUILT_SERVICE = '''NOTES = {}


def saved_notes():
    return NOTES


def create_reminder(note_id, at):
    return {"note": note_id, "at": at}
'''


def a_plan() -> MilestonePlanOutput:
    return MilestonePlanOutput(
        selected_sprint_goal="Sprint 2: reminders",
        delegated_tasks=[
            SpecialistTask(specialist_role="backend", task_description="Build the reminders service and its routes",
                           acceptance_criteria=["AC-2: a note can be given a reminder"],
                           files=["api/routes.py", "api/reminders.py"],
                           interfaces=["def create_reminder(note_id, at)"]),
            SpecialistTask(specialist_role="ui_ux", task_description="Build the notes page",
                           acceptance_criteria=["AC-1: notes are listed"], files=["web/page.js"]),
        ],
    )


def a_workspace(root: Path, *, router: str = STUB_ROUTER, service: str | None = None) -> Path:
    (root / "api").mkdir(parents=True, exist_ok=True)
    (root / "web").mkdir(parents=True, exist_ok=True)
    (root / "api" / "routes.py").write_text(router)
    if service is not None:
        (root / "api" / "reminders.py").write_text(service)
    (root / "web" / "page.js").write_text("export function render(notes) {\n  return notes.map(n => n.title);\n}\n")
    # The contract the suite was locked with: the sprint's route, and its criterion.
    harness = root / ".harness"
    harness.mkdir(exist_ok=True)
    (harness / "acceptance.json").write_text(json.dumps({"interface_contract": [
        {"criterion": "AC-2", "kind": "http", "line": "AC-2 POST /notes/{note_id}/remind -> 201", "method": "POST",
         "path": "/notes/{note_id}/remind", "status": 201, "statuses": [201]},
    ]}))
    return root


def a_sprint(root: Path, **more) -> dict:
    return {
        "repository": SimpleNamespace(root_path=str(root)),
        "milestone_plan": a_plan(),
        "drafted_for_plan": True,
        "sprint_plan": SimpleNamespace(sprints=[SimpleNamespace(criteria=["AC-1"]), SimpleNamespace(criteria=["AC-2"])]),
        "current_sprint_index": 1,
        "specialist_outputs": {BACKEND: SpecialistOutput(changed_files=["api/routes.py"]),
                               PAGE: SpecialistOutput(changed_files=["web/page.js"])},
        "specialist_task_index": 2,
        **more,
    }


@pytest.fixture()
def builders(monkeypatch):
    """The builder stages, their model calls stubbed: each request handed to a builder is recorded by stage."""
    handed: dict[str, str] = {}

    def gated(state, config, *, stage_name, initial_request, output_key, **kwargs):
        handed[stage_name] = initial_request["messages"][-1]["content"]
        return {output_key: SpecialistOutput(changed_files=["api/reminders.py"]), "stage": kwargs.get("next_stage")}

    monkeypatch.setenv("DELIVERY_MODE", "thorough")
    monkeypatch.setattr(workflow, "build_specialist_task_request",
                        lambda *a, **k: {"messages": [{"role": "user", "content": "the work order"}]})
    monkeypatch.setattr(workflow, "create_specialist_agent", lambda role, *a, **k: SimpleNamespace(role=role))
    monkeypatch.setattr(workflow, "_run_gated_agent", gated)
    monkeypatch.setattr("app.server.runtime_settings.effective_settings",
                        lambda: SimpleNamespace(execution_mode="linear"))
    return handed


def dispatch(root: Path, state: dict) -> dict:
    graph = workflow.build_workflow_graph(checkpointer=MemorySaver(), repo_root=str(root))
    return graph.nodes["specialist_dispatch"].bound.invoke(state, {"configurable": {"thread_id": "t"}})


def merged(state: dict, update: dict) -> dict:
    """The state after `update`, the merged channels merged as the graph merges them."""
    after = {**state, **update}
    for key in ("specialist_outputs", "unfinished_orders"):
        if key in update:
            after[key] = {**(state.get(key) or {}), **update[key]}
    return after


# -- after the build -------------------------------------------------------------------------------------------------


def test_a_backend_order_that_left_its_router_a_stub_and_its_service_missing_goes_back_before_the_test_round(
        tmp_path, builders):
    root = a_workspace(tmp_path)

    update = dispatch(root, a_sprint(root))

    assert update["stage"] == "specialist_dispatch"
    assert set(update["unfinished_orders"]) == {BACKEND}
    note = update["unfinished_orders"][BACKEND]
    assert "`api/reminders.py` does not exist" in note
    assert "`api/routes.py`" in note and "`create_reminder`" in note
    assert "`POST /notes/{note_id}/remind` (AC-2)" in note


def test_the_builder_sent_back_is_told_what_is_missing_and_the_finished_builders_do_not_run_again(tmp_path, builders):
    root = a_workspace(tmp_path)
    state = a_sprint(root)
    state = merged(state, dispatch(root, state))

    update = dispatch(root, state)

    assert list(builders) == [BACKEND]
    assert "`api/reminders.py` does not exist" in builders[BACKEND]
    assert update["unfinished_orders"] == {BACKEND: ""}
    assert update["specialist_outputs"][BACKEND].changed_files == ["api/routes.py", "api/reminders.py"]


def test_a_work_order_goes_back_once_an_attempt(tmp_path, builders):
    root = a_workspace(tmp_path)
    state = a_sprint(root)
    state = merged(state, dispatch(root, state))
    state = merged(state, dispatch(root, state))  # the builder ran again and left it as it was

    assert dispatch(root, state)["stage"] == "ci_gate"


def test_a_finished_build_goes_on_to_ci_as_before(tmp_path, builders):
    root = a_workspace(tmp_path, router=BUILT_ROUTER, service=BUILT_SERVICE)

    update = dispatch(root, a_sprint(root))

    assert update["stage"] == "ci_gate" and not update.get("unfinished_orders")
    assert builders == {}


def test_fast_delivery_keeps_its_own_path(tmp_path, builders, monkeypatch):
    """Fast delivery holds its drafts to what they promised itself (`drafting._promised_but_not_written`)."""
    monkeypatch.setenv("DELIVERY_MODE", "fast")
    root = a_workspace(tmp_path)

    assert dispatch(root, a_sprint(root))["stage"] == "ci_gate"


def test_in_parallel_mode_the_builder_sent_back_is_dispatched_again(tmp_path, builders):
    root = a_workspace(tmp_path)
    state = a_sprint(root, unfinished_orders={BACKEND: "the note"})
    graph = workflow.build_workflow_graph(checkpointer=MemorySaver(), repo_root=str(root))

    update = graph.nodes["specialist_gather"].bound.invoke(state, {"configurable": {"thread_id": "t"}})

    assert update["stage"] == "specialist_dispatch_parallel"


def test_a_parallel_builder_sent_back_hands_over_marked_built_again(tmp_path, builders):
    root = a_workspace(tmp_path)
    plan = a_plan()
    state = {**a_sprint(root, unfinished_orders={BACKEND: "\n\n--- the note ---"}),
             "__worker_task": plan.delegated_tasks[0], "__worker_index": 0}
    graph = workflow.build_workflow_graph(checkpointer=MemorySaver(), repo_root=str(root))

    update = graph.nodes["specialist_worker"].bound.invoke(state, {"configurable": {"thread_id": "t"}})

    assert "--- the note ---" in builders[BACKEND]
    assert update["unfinished_orders"] == {BACKEND: ""}


def test_the_note_a_builder_reads_avoids_the_banned_words(tmp_path, builders):
    root = a_workspace(tmp_path)

    note = dispatch(root, a_sprint(root))["unfinished_orders"][BACKEND]

    assert not BANNED.findall(note)


@pytest.mark.parametrize("text", [
    STUB_ROUTER,
    "router.get('/notes', (req, res) => res.json([]));\nrouter.get('/notes/:id', (req, res) => res.json({}));\n",
    "def remind(note_id):\n    raise NotImplementedError\n",
])
def test_a_file_whose_every_answer_is_empty_is_a_stub(text):
    assert unfinished_build.answers_only_empty(text)


@pytest.mark.parametrize("text", [
    BUILT_ROUTER,
    "router.get('/notes', (req, res) => res.json(store.all()));\nrouter.get('/x', (req, res) => res.json([]));\n",
    "def first(items):\n    if not items:\n        return None\n    return items[0]\n",
])
def test_a_file_that_answers_with_values_is_not_a_stub(text):
    assert not unfinished_build.answers_only_empty(text)


# -- after a test round ----------------------------------------------------------------------------------------------


def a_round(monkeypatch, root: Path, found: list) -> dict:
    sprint = a_sprint(root)
    return run_a_test_round(monkeypatch, root, found=found, milestone_plan=sprint["milestone_plan"],
                            sprint_plan=sprint["sprint_plan"], current_sprint_index=1,
                            specialist_outputs=sprint["specialist_outputs"]).update


def a_404() -> object:
    return reported("[AC-2] POST /notes/7/remind answered 404, wanted 201", actual_behavior="404 Not Found")


def a_missing_service() -> object:
    return reported("No reminders service exists: api/reminders.py is missing")


def a_real_fault() -> object:
    return reported("[AC-1] GET /notes lists the notes oldest first", affected_files=["api/routes.py"])


def test_a_round_whose_defects_are_mostly_work_not_built_sends_them_to_the_builder(tmp_path, monkeypatch):
    root = a_workspace(tmp_path, router=BUILT_ROUTER.replace("remind", "alert"))

    update = a_round(monkeypatch, root, [a_404(), a_missing_service(), a_real_fault()])

    assert update["stage"] == "specialist_dispatch"
    assert set(update["unfinished_orders"]) == {BACKEND}
    assert "POST /notes/7/remind answered 404" in update["unfinished_orders"][BACKEND]
    status = {d.description[:12]: d.status for d in update["remediation"].defects}
    assert status == {"[AC-2] POST ": "superseded", "No reminders": "superseded", "[AC-1] GET /": "open"}
    assert update["remediation"].attempt == 0


def test_a_404_on_a_route_the_code_serves_stays_with_the_fixers(tmp_path, monkeypatch):
    """A route that is written and still answers 404 - a doubled prefix, say - is a fault, not work not built."""
    root = a_workspace(tmp_path, router=BUILT_ROUTER, service=BUILT_SERVICE)

    update = a_round(monkeypatch, root, [a_404(), a_real_fault()])

    assert update["stage"] == "defect_remediation"
    assert [d.status for d in update["remediation"].defects] == ["open", "open"]


def test_a_round_of_real_faults_goes_to_the_fixers_as_before(tmp_path, monkeypatch):
    root = a_workspace(tmp_path, router=BUILT_ROUTER, service=BUILT_SERVICE)

    update = a_round(monkeypatch, root, [a_real_fault()])

    assert update["stage"] == "defect_remediation" and not update.get("unfinished_orders")


def test_a_round_sends_work_to_the_builders_once_an_attempt(tmp_path, monkeypatch):
    root = a_workspace(tmp_path, router=BUILT_ROUTER.replace("remind", "alert"))
    sprint = a_sprint(root)

    update = run_a_test_round(monkeypatch, root, found=[a_404(), a_missing_service()],
                              milestone_plan=sprint["milestone_plan"], sprint_plan=sprint["sprint_plan"],
                              current_sprint_index=1, specialist_outputs=sprint["specialist_outputs"],
                              builders_sent_back=[unfinished_build.AFTER_A_ROUND]).update

    assert update["stage"] == "defect_remediation"


# -- the ledger and `loop.sh effects` --------------------------------------------------------------------------------


def test_both_send_backs_are_in_the_ledger_and_counted_by_the_effects_report(tmp_path, builders, monkeypatch):
    import runpy

    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr("app.observability.transcript._run_id_from_config", lambda: "run-unfinished")
    root = a_workspace(tmp_path / "workspace")
    dispatch(root, a_sprint(root))
    a_round(monkeypatch, a_workspace(tmp_path / "later", router=BUILT_ROUTER.replace("remind", "alert")), [a_404()])
    records = [json.loads(line) for line in
               (tmp_path / "data" / "transcripts" / "run-unfinished.jsonl").read_text().splitlines()]

    effects = runpy.run_path(str(Path(__file__).resolve().parent.parent / "scripts" / "loop" / "effects.py"))["effects"]
    lines = "\n".join(effects(records, ""))

    assert [r["stage"] for r in records if r.get("event") == unfinished_build.SENT_BACK_EVENT] == [BACKEND]
    assert [r["description"][:6] for r in records if r.get("event") == unfinished_build.ROUTED_EVENT] == ["[AC-2]"]
    assert "   1  LF.1299 a work order not finished sent back to its builder" in lines
    assert "   1  LF.1299 a round's not-built defect sent to its builder" in lines


def test_a_testing_order_whose_promised_tests_are_written_is_done(tmp_path):
    """The product's code leaves tests out; a testing order's promise is kept in its own test files."""
    root = a_workspace(tmp_path, router=BUILT_ROUTER, service=BUILT_SERVICE)
    (root / "tests").mkdir()
    (root / "tests" / "test_reminders.py").write_text("def test_a_reminder_is_kept():\n    assert True\n")
    order = SpecialistTask(specialist_role="testing", task_description="Unit tests of the reminders",
                           files=["tests/test_reminders.py"], interfaces=["def test_a_reminder_is_kept()"])

    missing = unfinished_build.what_is_missing(order, root, sources=unfinished_build.product_sources(root))

    assert missing == []
