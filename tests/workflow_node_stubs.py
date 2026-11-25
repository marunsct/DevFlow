"""Run one node of the compiled workflow graph on its own, every model call stubbed.

Wherever a node is defined (a closure inside `build_workflow_graph` or a function of `app.graph.nodes`), a test
reaches it the same way: through `graph.nodes[name].bound`.
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


def a_reported_defect(description: str = "[AC-2] Saving a note fails", **extra: Any) -> Any:
    from app.agents.specialists import ReportedDefect

    return ReportedDefect(description=description, severity="major", reproduction_steps="r",
                          expected_behavior="e", actual_behavior="a", affected_files=["app/store.js"],
                          owner="backend", **extra)


def run_a_test_round(monkeypatch, tmp_path, *, found: list[Any] | None = None, failing_due: list[str] | None = None,
                     saved_run: dict[str, Any] | None = None, overrides: dict[str, Any] | None = None,
                     **state: Any) -> SimpleNamespace:
    """Run `test_and_triage` once: the testing stage reports `found`, the locked suite fails `failing_due`.

    Every measurement the round would take of a real product is stubbed to say nothing, so what is left is the
    round's own handling of what it was told. `overrides` maps a dotted name to what replaces it instead of the
    stub. `.update` is the node's return, `.request` what the stage was handed.
    """
    seen = SimpleNamespace(update=None, request=None)

    def gated(state, config, *, initial_request, output_key, **kwargs):
        seen.request = initial_request
        return {output_key: SpecialistOutput(changed_files=[], defects=list(found or []))}

    due = list(failing_due or [])
    monkeypatch.setattr("app.graph.acceptance_nodes.acceptance_for_round", lambda state: ("", []))
    monkeypatch.setattr("app.graph.acceptance_nodes.reopen_the_suite_for", lambda *a, **k: None)
    monkeypatch.setattr("app.graph.acceptance_nodes.beyond_repair", lambda *a, **k: [])
    monkeypatch.setattr("app.graph.acceptance_nodes._failing_due", lambda state: (due, "npm test"))
    monkeypatch.setattr("app.graph.acceptance_nodes.suite.is_locked", lambda root: True)
    monkeypatch.setattr("app.graph.acceptance_nodes.suite.last_result",
                        lambda root: saved_run if saved_run is not None else {"ran": True, "failed": len(due)})
    monkeypatch.setattr("app.graph.acceptance_nodes.interface_defects", lambda state: [])
    monkeypatch.setattr("app.graph.acceptance_nodes.pack_contract_defects", lambda state: [])
    monkeypatch.setattr("app.graph.acceptance_nodes.failing_due_defects", lambda state, reported: [])
    monkeypatch.setattr("app.agents.specialists.what_the_files_already_prove", lambda *a, **k: [])
    monkeypatch.setattr(workflow, "_run_unit_tests_procedurally", lambda root: (None, "no unit test command is recorded for this project"))
    monkeypatch.setattr(workflow, "_with_the_contract_s_server_errors", lambda state, result, milestone: result)
    monkeypatch.setattr(workflow, "_with_the_lock_s_server_errors", lambda state, result, milestone: result)
    monkeypatch.setattr(workflow, "_a_suite_failure_the_round_did_not_report", lambda *a, **k: None)
    monkeypatch.setattr(workflow, "create_specialist_agent", lambda *a, **k: SimpleNamespace())
    monkeypatch.setattr(workflow, "_run_gated_agent", gated)
    monkeypatch.setattr("app.delivery.fast", lambda: False)
    for target, replacement in (overrides or {}).items():
        monkeypatch.setattr(target, replacement)
    graph = compiled(monkeypatch, tmp_path)
    base = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "milestone_plan": two_work_orders(),
        "test_round": 1,
        "specialist_outputs": {},
        "review_defects": [],
        "current_sprint_index": 0,
        **state,
    }
    seen.update = graph.nodes["test_and_triage"].bound.invoke(base, CONFIG)
    return seen


def end_an_attempt(monkeypatch, tmp_path, outcome: str, **state: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """A test round whose fix round closed nothing, so the attempt ends; `end_of_attempt.decide` answers `outcome`.

    Returns the round's update and the keyword arguments `decide` was asked with.
    """
    from app.graph import end_of_attempt, unchanged_fix_round

    asked: list[dict[str, Any]] = []

    def decide(root, defects, **kwargs):
        asked.append({"root": root, **kwargs})
        return SimpleNamespace(outcome=getattr(end_of_attempt, outcome), why="the decision's reason",
                               best_history=[*(kwargs["best_history"] or []), 15], put_back="")

    monkeypatch.setattr(unchanged_fix_round, "ends_the_attempt", lambda *a, **k: True)
    monkeypatch.setattr(end_of_attempt, "decide", decide)
    seen = run_a_test_round(monkeypatch, tmp_path, found=[a_reported_defect()], failing_due=["AC-2"], **state)
    return seen.update, asked


def an_accepting_review() -> Any:
    from app.agents.milestone_reviewer import MilestoneReviewOutput

    return MilestoneReviewOutput(status="accepted", findings=[], acceptance_evidence="All good",
                                 documentation_reviewed=True, tests_reviewed=True)


def run_a_milestone_review(monkeypatch, tmp_path, *, review: Any = None, overrides: dict[str, Any] | None = None,
                           **state: Any) -> SimpleNamespace:
    """Run `milestone_review` once on a reviewer that answers `review` (an accepting one by default).

    `.kwargs` are the keyword arguments of `build_milestone_review_request`, `.update` the node's return.
    """
    seen = SimpleNamespace(kwargs=None, update=None)

    def build_request(*args, **kwargs):
        seen.kwargs = kwargs
        return {"messages": [{"role": "user", "content": "review the sprint"}]}

    def gated(state, config, *, output_key, **kwargs):
        return {output_key: review if review is not None else an_accepting_review()}

    monkeypatch.setattr(workflow, "create_milestone_reviewer_agent", lambda *a, **k: SimpleNamespace())
    monkeypatch.setattr(workflow, "build_milestone_review_request", build_request)
    monkeypatch.setattr(workflow, "_run_gated_agent", gated)
    monkeypatch.setattr("app.graph.acceptance_nodes.acceptance_text_for", lambda state: "")
    for target, replacement in (overrides or {}).items():
        monkeypatch.setattr(target, replacement)
    graph = compiled(monkeypatch, tmp_path)
    base = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "milestone_plan": two_work_orders(),
        "specialist_outputs": {},
        "current_sprint_index": 0,
        **state,
    }
    seen.update = graph.nodes["milestone_review"].bound.invoke(base, CONFIG)
    return seen


def run_node(monkeypatch, tmp_path, node: str, *, answer: Any = None, overrides: dict[str, Any] | None = None,
             two_models: bool = False, **state: Any) -> SimpleNamespace:
    """Run graph node `node` once; every role agent it builds is a stub and every stage it runs answers `answer`.

    `answer` may be a callable of the stage name. `.requests` holds (stage name, request) for each stage the node
    ran, `.agents` (factory name, model) for each agent it built, `.update` the node's return.
    """
    seen = SimpleNamespace(update=None, requests=[], agents=[])

    def gated(state, config, *, stage_name, initial_request, output_key, **kwargs):
        seen.requests.append((stage_name, initial_request))
        return {output_key: answer(stage_name) if callable(answer) else answer, "stage": kwargs.get("next_stage")}

    def factory(name):
        def build(*args, **kwargs):
            seen.agents.append((name, kwargs.get("model")))
            return SimpleNamespace()
        return build

    for name in dir(workflow):
        if name.startswith("create_") and name.endswith("_agent"):
            monkeypatch.setattr(workflow, name, factory(name))
    monkeypatch.setattr(workflow, "_run_gated_agent", gated)
    for target, replacement in (overrides or {}).items():
        monkeypatch.setattr(target, replacement)
    graph = compiled(monkeypatch, tmp_path, two_models=two_models)
    from app.state import RepositoryContext

    repository = RepositoryContext(root_path=str(tmp_path), branch="main", commit="0000000", status="clean")
    seen.update = graph.nodes[node].bound.invoke({"repository": repository, **state}, CONFIG)
    return seen


def one_sprint(goal: str = "Notes can be saved") -> Any:
    from app.agents.scrum_master import SprintDefinition, SprintPlanOutput

    return SprintPlanOutput(sprints=[SprintDefinition(goal=goal, user_value="v")])


FAILING_LOCKED_TESTS = [
    ("test_ac2_saves", "AC-2: A note is saved", "assert 201 == 500"),
    ("test_ac3_lists", "AC-3: Notes are listed", "assert [] == [note]"),
    ("test_ac6_counts", "AC-6: The count is shown", "assert 'characters: 18' in out"),
]


def run_a_dispute(monkeypatch, tmp_path, *, called_wrong: list[str], pass_alone: tuple[str, ...] = (),
                  past_the_cap: tuple[str, ...] = (), **state: Any) -> SimpleNamespace:
    """Run `acceptance_dispute` on `FAILING_LOCKED_TESTS`; the QA lead calls `called_wrong` wrong.

    Of those, `pass_alone` pass when run alone and `past_the_cap` are past the run's reclassification cap. Records
    what each leg was asked: `.alone`, `.capped`, `.deferred`, `.reopened`, `.request_kwargs`; `.update` the return.
    """
    seen = SimpleNamespace(alone=[], capped=[], deferred=[], reopened=[], request_kwargs=None, update=None)

    def build_dispute_request(*args, **kwargs):
        seen.request_kwargs = kwargs
        return {"messages": [{"role": "user", "content": "judge these"}]}

    def fail_alone(root, named):
        seen.alone.append(list(named))
        return [n for n in named if n not in pass_alone], [n for n in named if n in pass_alone]

    def within_the_cap(state, named):
        seen.capped.append(list(named))
        return [n for n in named if n not in past_the_cap], [n for n in named if n in past_the_cap], 1

    def reopen(state, to_repair, **kwargs):
        seen.reopened.append((list(to_repair), kwargs))
        return {"stage": "acceptance_author"}

    seen.update = run_node(monkeypatch, tmp_path, "acceptance_dispute", answer="the QA lead's ruling", overrides={
        "app.graph.workflow._the_locked_tests_still_failing": lambda state: list(FAILING_LOCKED_TESTS),
        "app.acceptance.suite.suite_files": lambda root: [],
        "app.acceptance.requests.shares_one_service": lambda root: "ONE SHARED SERVICE",
        "app.agents.suite_dispute.build_dispute_request": build_dispute_request,
        "app.agents.suite_dispute.tests_it_names": lambda answer, names, **k: list(called_wrong),
        "app.graph.acceptance_nodes.tests_that_fail_alone": fail_alone,
        "app.graph.acceptance_nodes.tests_whose_service_stayed_up": lambda root, named: (list(named), []),
        "app.graph.acceptance_nodes.by_shared_cause": lambda named, code: list(named),
        "app.graph.acceptance_nodes.within_the_cap_by_cause": within_the_cap,
        "app.graph.acceptance_nodes.defer_what_is_beyond_repair":
            lambda state, beyond, why: seen.deferred.append((list(beyond), list(why))),
        "app.graph.acceptance_nodes.reopen_the_suite_for": reopen,
    }, **state).update
    return seen


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
