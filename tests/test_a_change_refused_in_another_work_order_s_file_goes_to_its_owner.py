"""A change refused in another work order's file is handed to that file's owner, so the stage stops sending it (LF.1548).

Measured on a medium run in parallel mode: the database work order tried eleven times to edit a routes file the plan
gave to the backend work order, running beside it. Every `edit_artifact` was refused with "say exactly what in
`blockers`", from the third with how many times, and the model reworded its edit each time: 97 calls, 31% failing.
The captured file holds those eleven calls as the model sent them.
"""
from __future__ import annotations

import json
import re
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel

from app.agents import stage_memory
from app.agents.settled_answer import build_settled_answer_middleware
from app.agents.specialists import SpecialistOutput
from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask
from app.graph import workflow
from app.tools.repository import (
    RepositoryToolError, edit_approved_artifact, record_work_order_files, why_the_stage_may_not_write,
    write_approved_artifact,
)

CAPTURED = json.loads((Path(__file__).parent / "captured" /
                       "edit-artifact-calls-refused-in-another-work-order-s-file.json").read_text(encoding="utf-8"))
REFUSED_TO, OWNER = CAPTURED["stage"], CAPTURED["owner"]
ROUTES = CAPTURED["calls"][0]["args"]["relative_path"]
MODELS = "task-management-dashboard/task_management_dashboard/models.py"
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


class Answer(BaseModel):
    changed_files: list[str]


def a_workspace(root: Path) -> Path:
    (root / ROUTES).parent.mkdir(parents=True)
    (root / ROUTES).write_text("from .models import User\n")
    (root / MODELS).write_text("class User:\n    pass\n")
    return root


def as_stage(monkeypatch, stage: dict) -> None:
    monkeypatch.setattr("app.observability.transcript._stage_from_config", lambda fallback: stage["now"])


def the_edit(root: Path, number: int) -> None:
    args = CAPTURED["calls"][number]["args"]
    edit_approved_artifact(root, args["relative_path"], args["find"], args["replace"])


@pytest.fixture()
def refused_stage(tmp_path, monkeypatch):
    """The database work order, refused the backend's routes file, its tool calls through the stage's guard."""
    root = a_workspace(tmp_path)
    record_work_order_files(root, {ROUTES: OWNER, MODELS: REFUSED_TO})
    stage = {"now": REFUSED_TO}
    as_stage(monkeypatch, stage)
    stage_memory.forget_everything()
    with stage_memory.remembering("the-database-thread"):
        yield SimpleNamespace(root=root, stage=stage, guard=build_settled_answer_middleware(Answer, REFUSED_TO, 120))
    stage_memory.forget_everything()


def through_the_guard(refused_stage, number: int, ran: list[int]) -> str:
    """One captured call as the agent makes it: the stage's guard first, then the tool, which answers an error."""
    call = CAPTURED["calls"][number]
    request = SimpleNamespace(tool_call={"name": call["tool"], "id": f"c{number}", "args": call["args"]})

    def the_tool(_request):
        ran.append(number)
        try:
            the_edit(refused_stage.root, number)
        except RepositoryToolError as error:
            return ToolMessage(content=json.dumps({"error": str(error)}), tool_call_id=f"c{number}", status="error")
        return ToolMessage(content="{}", tool_call_id=f"c{number}")

    return str(refused_stage.guard.wrap_tool_call(request, the_tool).content)


# -- the refusals the stage is given -------------------------------------------------------------------------------


def test_the_captured_eleven_edits_reach_the_file_tool_twice_and_are_withheld_after(refused_stage):
    ran: list[int] = []

    said = [through_the_guard(refused_stage, number, ran) for number in range(len(CAPTURED["calls"]))]

    assert ran == [0, 1]
    assert all("withheld for the rest of this stage" in reply and OWNER in reply for reply in said[2:])
    assert (refused_stage.root / ROUTES).read_text() == "from .models import User\n"


def test_the_first_refusal_says_the_change_is_recorded_and_goes_to_the_owner(refused_stage):
    with pytest.raises(RepositoryToolError) as refused:
        the_edit(refused_stage.root, 0)

    said = str(refused.value)
    assert f"the plan gave it to {OWNER}" in said and "recorded as this stage's blocker" in said
    assert "Do not send it again" in said and "Nothing was written." in said


def test_the_second_refusal_of_the_file_is_one_short_line_naming_the_owner_and_the_change(refused_stage):
    with pytest.raises(RepositoryToolError) as first:
        the_edit(refused_stage.root, 0)

    with pytest.raises(RepositoryToolError) as second:
        the_edit(refused_stage.root, 3)

    said = str(second.value)
    assert said.startswith(f"Recorded for {OWNER}: ")
    assert "class User(Base)" in said and "finish your own files" in said
    assert "\n" not in said and len(said) < len(str(first.value))


def test_asking_whether_a_write_would_be_refused_records_nothing(refused_stage):
    why_the_stage_may_not_write(refused_stage.root, REFUSED_TO, ROUTES)
    with pytest.raises(RepositoryToolError) as refused:
        the_edit(refused_stage.root, 0)

    assert "recorded as this stage's blocker" in str(refused.value)


# -- the owner, running or on its next visit ----------------------------------------------------------------------


def test_the_running_owner_s_next_model_call_carries_the_change_once(refused_stage):
    from app.tools.foreign_file_handoffs import build_middleware

    with pytest.raises(RepositoryToolError):
        the_edit(refused_stage.root, 3)
    owner_s = build_middleware(str(refused_stage.root))
    refused_stage.stage["now"] = OWNER

    first, then = owner_s.before_model({"messages": []}, None), owner_s.before_model({"messages": []}, None)

    note = str(first["messages"][0].content)
    assert f"`{ROUTES}`, for {REFUSED_TO}" in note and "from .models import User, RefreshToken" in note
    assert then is None


def the_owner_s_next_note(refused_stage) -> str:
    from app.tools.foreign_file_handoffs import build_middleware

    refused_stage.stage["now"] = OWNER
    handed = build_middleware(str(refused_stage.root)).before_model({"messages": []}, None)
    refused_stage.stage["now"] = REFUSED_TO
    return str(handed["messages"][0].content) if handed else ""


BROKEN = "from .models import User//// the routes, cut short mid-line by the reply's cap"
WHOLE = "from .models import User, RefreshToken\n\n\ndef routes():\n    return []\n"


def test_a_later_whole_version_of_the_file_replaces_the_one_recorded_before(refused_stage):
    """Measured on one builder: its first write was a truncated file, its second the whole one, and the owner was
    handed the truncated one while the whole one was answered "already recorded, do not send it again"."""
    for content in (BROKEN, WHOLE):
        with pytest.raises(RepositoryToolError):
            write_approved_artifact(refused_stage.root, ROUTES, content)

    note = the_owner_s_next_note(refused_stage)

    assert "RefreshToken" in note and "cut short mid-line" not in note


def test_a_later_whole_version_reaches_an_owner_that_was_handed_the_earlier_one(refused_stage):
    with pytest.raises(RepositoryToolError):
        write_approved_artifact(refused_stage.root, ROUTES, BROKEN)
    the_owner_s_next_note(refused_stage)
    with pytest.raises(RepositoryToolError):
        write_approved_artifact(refused_stage.root, ROUTES, WHOLE)

    note = the_owner_s_next_note(refused_stage)

    assert "RefreshToken" in note


def test_another_stage_s_model_call_is_handed_nothing(refused_stage):
    from app.tools.foreign_file_handoffs import build_middleware

    with pytest.raises(RepositoryToolError):
        the_edit(refused_stage.root, 3)
    refused_stage.stage["now"] = "specialist_frontend_2"

    assert build_middleware(str(refused_stage.root)).before_model({"messages": []}, None) is None


def a_plan() -> MilestonePlanOutput:
    return MilestonePlanOutput(
        selected_sprint_goal="Sprint 2: the dashboard",
        delegated_tasks=[
            SpecialistTask(specialist_role="database", task_description="The models", files=[MODELS]),
            SpecialistTask(specialist_role="backend", task_description="The routes", files=[ROUTES]),
        ],
    )


def a_sprint(root: Path) -> dict:
    return {"repository": SimpleNamespace(root_path=str(root)), "milestone_plan": a_plan(), "drafted_for_plan": True,
            "specialist_outputs": {}, "specialist_task_index": 0}


@pytest.fixture()
def builders(monkeypatch):
    """Linear dispatch with each builder's model stubbed: the database builder tries the captured edit, and each
    builder's request is kept by stage. A stubbed builder makes no model call, so no running owner is handed it."""
    handed: dict[str, str] = {}
    stage = {"now": ""}

    def gated(state, config, *, stage_name, initial_request, output_key, **kwargs):
        handed[stage_name] = initial_request["messages"][-1]["content"]
        stage["now"] = stage_name
        if stage_name == REFUSED_TO:
            for number in (0, 3):
                try:
                    the_edit(Path(state["repository"].root_path), number)
                except RepositoryToolError:
                    pass
        stage["now"] = ""
        return {output_key: SpecialistOutput(changed_files=[]), "stage": kwargs.get("next_stage")}

    monkeypatch.setenv("DELIVERY_MODE", "fast")
    as_stage(monkeypatch, stage)
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
    after = {**state, **update}
    for key in ("specialist_outputs", "unfinished_orders"):
        if key in update:
            after[key] = {**(state.get(key) or {}), **update[key]}
    return after


def test_the_refused_change_is_among_the_refused_stage_s_blockers(tmp_path, builders):
    root = a_workspace(tmp_path)

    update = dispatch(root, a_sprint(root))

    blockers = update["specialist_outputs"][REFUSED_TO].blockers
    assert len(blockers) == 1
    assert f"`{ROUTES}`" in blockers[0] and OWNER in blockers[0] and "class User(Base)" in blockers[0]


def test_a_change_no_running_owner_received_goes_to_the_owner_s_next_visit_once(tmp_path, builders):
    root = a_workspace(tmp_path)
    state = merged(a_sprint(root), dispatch(root, a_sprint(root)))
    state = merged(state, dispatch(root, state))  # every builder has finished
    sent = dispatch(root, state)
    state = merged(state, sent)
    state = merged(state, dispatch(root, state))  # the owner ran again

    after = dispatch(root, state)

    asked = builders[OWNER]
    assert "What another work order needs from your files" in asked and f"for {REFUSED_TO}" in asked
    assert (sent["stage"], after["stage"]) == ("specialist_dispatch", "ci_gate")


def without_the_project_s_name(text: str) -> str:
    """The captured project is named for its product; its path is not the harness's wording."""
    return text.replace("task-management-dashboard/task_management_dashboard", "the-project")


def test_the_refusals_avoid_the_banned_words(refused_stage):
    told = [through_the_guard(refused_stage, number, []) for number in range(3)]

    assert not BANNED.findall(without_the_project_s_name(" ".join(told)))


def test_what_the_owner_is_told_avoids_the_banned_words(refused_stage):
    from app.tools import foreign_file_handoffs

    with pytest.raises(RepositoryToolError):
        the_edit(refused_stage.root, 3)
    refused_stage.stage["now"] = OWNER
    note = foreign_file_handoffs.build_middleware(str(refused_stage.root)).before_model({"messages": []}, None)
    blocker = foreign_file_handoffs.as_blocker(ROUTES, OWNER, "")

    assert not BANNED.findall(without_the_project_s_name(f"{note['messages'][0].content} {blocker}"))


# -- the ledger and `loop.sh effects` -------------------------------------------------------------------------------


def test_the_refusals_and_hand_offs_are_in_the_effects_report(refused_stage, monkeypatch, tmp_path):
    from app.tools.foreign_file_handoffs import build_middleware

    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr("app.observability.transcript._run_id_from_config", lambda: "run-foreign-file")
    said = [through_the_guard(refused_stage, number, []) for number in range(3)]
    refused_stage.stage["now"] = OWNER
    build_middleware(str(refused_stage.root)).before_model({"messages": []}, None)
    records = [json.loads(line) for line in
               (tmp_path / "data" / "transcripts" / "run-foreign-file.jsonl").read_text().splitlines()]
    records += [{"kind": "tool_result", "stage": REFUSED_TO, "content": reply} for reply in said]

    effects = runpy.run_path(str(Path(__file__).resolve().parent.parent / "scripts" / "loop" / "effects.py"))["effects"]
    lines = "\n".join(effects(records, ""))

    assert "     3  LF.1548 writes refused in another work order's file" in lines
    assert "     1  LF.1548 hand-offs recorded for the file's owner" in lines
    assert "     1  LF.1548 hand-offs delivered to a running owner" in lines
