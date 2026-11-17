"""Run one node of the compiled workflow graph on its own, every model call stubbed.

The nodes are closures inside `build_workflow_graph`, so a test reaches one through `graph.nodes[name].bound`.
These helpers let a test assert what a node *does* - the request its stage was handed, the model it was built on,
what it recorded - instead of pinning the text of `workflow.py`, which moves whenever the file is restructured.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langgraph.checkpoint.memory import MemorySaver

from app.agents.specialists import SpecialistOutput
from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask
from app.graph import workflow

CONFIG = {"configurable": {"thread_id": "t", "run_id": "r"}}
BUILD = FakeListChatModel(responses=["unused"], name="build")
JUDGE = FakeListChatModel(responses=["unused"], name="judge")


def two_work_orders() -> MilestonePlanOutput:
    """Two work orders that share a file, as plans often do."""
    return MilestonePlanOutput(
        selected_sprint_goal="Sprint 1: notes",
        delegated_tasks=[
            SpecialistTask(specialist_role="backend", task_description="write the notes API",
                           acceptance_criteria=["works"], files=["app/server.js", "app/shared.js"]),
            SpecialistTask(specialist_role="ui_ux", task_description="write the notes page",
                           acceptance_criteria=["works"], files=["app/page.js", "app/shared.js"]),
        ],
        review_task_assignments=["change -> task 1"],
    )


def compiled(monkeypatch, tmp_path, *, two_models: bool = False) -> Any:
    """The graph on the build model; with `two_models`, a distinct judgement model as the owner configures."""
    if two_models:
        monkeypatch.setattr("app.models.roles.build_judgement_model", lambda model, *a, **k: JUDGE)
    return workflow.build_workflow_graph(
        model=BUILD if two_models else "fake-model", checkpointer=MemorySaver(), repo_root=str(tmp_path),
    )


def run_a_builder(monkeypatch, tmp_path, *, parallel: bool, task_index: int = 1, two_models: bool = False,
                  **state: Any) -> SimpleNamespace:
    """Run the linear builder (`specialist_dispatch`) or one parallel worker (`specialist_worker`) on work order
    `task_index` of `two_work_orders()`; return what its stage was handed and what the node returned.

    `.kwargs` are the keyword arguments of `build_specialist_task_request`, `.request` the request handed to the
    stage, `.model` the model its agent was built on, `.update` the node's return.
    """
    seen = SimpleNamespace(kwargs=None, request=None, model=None, update=None)

    def build_request(*args, **kwargs):
        seen.kwargs = kwargs
        return {"messages": [{"role": "user", "content": "the work order"}]}

    def agent(role, *args, **kwargs):
        seen.model = kwargs.get("model")
        return SimpleNamespace(role=role)

    def gated(state, config, *, initial_request, output_key, **kwargs):
        seen.request = initial_request
        return {output_key: SpecialistOutput(changed_files=["app/shared.js"]), "stage": kwargs.get("next_stage")}

    monkeypatch.setattr(workflow, "build_specialist_task_request", build_request)
    monkeypatch.setattr(workflow, "create_specialist_agent", agent)
    monkeypatch.setattr(workflow, "_run_gated_agent", gated)
    monkeypatch.setattr("app.server.runtime_settings.effective_settings",
                        lambda: SimpleNamespace(execution_mode="parallel" if parallel else "linear"))
    graph = compiled(monkeypatch, tmp_path, two_models=two_models)
    plan = two_work_orders()
    base: dict[str, Any] = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "milestone_plan": plan,
        "drafted_for_plan": True,
        "specialist_outputs": {},
        **state,
    }
    if parallel:
        base.update({"__worker_task": plan.delegated_tasks[task_index], "__worker_index": task_index})
        seen.update = graph.nodes["specialist_worker"].bound.invoke(base, CONFIG)
    else:
        base.setdefault("specialist_task_index", task_index)
        seen.update = graph.nodes["specialist_dispatch"].bound.invoke(base, CONFIG)
    return seen


def marking(monkeypatch, target: str, marker: str) -> list[tuple[tuple, dict]]:
    """Replace the request transform `target` with one that appends `[marker]` to the request's last message.

    Returns the list its calls are recorded in, so a test can see both that the node applied it and in what order.
    """
    calls: list[tuple[tuple, dict]] = []

    def mark(request, *args, **kwargs):
        calls.append((args, kwargs))
        request["messages"][-1]["content"] += f"\n[{marker}]"
        return request

    monkeypatch.setattr(target, mark)
    return calls


def one_defect(**extra: Any) -> Any:
    from app.sprint import Defect, RemediationCycle

    defect = Defect(description="[AC-2] Saving a note fails", severity="major", reproduction_steps="r",
                    expected_behavior="e", actual_behavior="a", owner="backend",
                    affected_files=["app/store.js"], **extra)
    return RemediationCycle(sprint_goal="g", defects=[defect])


def run_a_fixer(monkeypatch, tmp_path, *, answer: Any = None, cycle: Any = None, **state: Any) -> SimpleNamespace:
    """Run the linear fix stage (`defect_remediation`) on `one_defect()`; `answer` None pauses it for approval.

    `.request` is what the fixer was handed, `.watching` the arguments the stage's write check was armed with,
    `.update` the node's return.
    """
    import contextlib

    seen = SimpleNamespace(request=None, watching=None, update=None)

    def gated(state, config, *, initial_request, output_key, **kwargs):
        seen.request = initial_request
        if answer is None:
            return {"stage": "awaiting_approval:defect_fix", "pending_inner_thread_id": "inner"}
        return {output_key: answer}

    @contextlib.contextmanager
    def watching(*args, **kwargs):
        seen.watching = (args, kwargs)
        yield

    monkeypatch.setattr(workflow, "create_specialist_agent", lambda *a, **k: SimpleNamespace())
    monkeypatch.setattr(workflow, "build_defect_fix_request",
                        lambda *a, **k: {"messages": [{"role": "user", "content": "fix it"}]})
    monkeypatch.setattr(workflow, "_what_the_last_failure_printed", lambda *a, **k: "")
    monkeypatch.setattr(workflow, "_closed_if_an_earlier_fix_resolved_it", lambda *a, **k: None)
    monkeypatch.setattr(workflow, "_what_the_ledger_confirms", lambda *a, **k: "npm test")
    monkeypatch.setattr(workflow, "_fixes_run_side_by_side", lambda: False)
    # The agent loop's fix, not fast delivery's one-call rewrite of the files.
    monkeypatch.setattr("app.delivery.fast", lambda: False)
    monkeypatch.setattr("app.graph.kept_fix_candidates.replayed", lambda *a, **k: None)
    monkeypatch.setattr("app.graph.acceptance_nodes.done_by_the_definition", lambda *a, **k: [])
    monkeypatch.setattr("app.graph.engineering.before_a_fix", lambda *a, **k: "base")
    monkeypatch.setattr("app.graph.engineering.after_a_fix", lambda *a, **k: [])
    monkeypatch.setattr("app.graph.verify_after_write.watching", watching)
    monkeypatch.setattr(workflow, "_run_gated_agent", gated)
    graph = compiled(monkeypatch, tmp_path)
    base = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "remediation": cycle if cycle is not None else one_defect(),
        "defect_cursor": 0,
        "test_round": 1,
        "current_sprint_index": 0,
        "specialist_outputs": {},
        **state,
    }
    seen.update = graph.nodes["defect_remediation"].bound.invoke(base, CONFIG)
    return seen
