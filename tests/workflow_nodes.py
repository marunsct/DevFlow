"""Run one node of the compiled workflow graph on a made state, for behaviour tests.

Some nodes are closures inside `build_workflow_graph`, others module-level
functions of `app.graph.nodes`; the compiled graph is the one handle on them
that holds wherever they come to be defined. Tests here call a node through
`graph.nodes[name]` rather than read its source, so a node lifted out of
`workflow.py` keeps its tests.
"""
from __future__ import annotations

from contextlib import ExitStack
from types import SimpleNamespace
from typing import Any, Callable
from unittest.mock import patch

from langgraph.checkpoint.memory import MemorySaver

CONFIG = {"configurable": {"thread_id": "t", "run_id": "r"}}


def workflow_source_files() -> list[Any]:
    """The workflow's source files: `app.graph.workflow`, `app.graph.context` and every module of `app.graph.nodes`.

    For a test that parses the source (`ast`), which takes one module at a time."""
    from pathlib import Path

    import app.graph.context
    import app.graph.nodes
    import app.graph.workflow

    return [
        Path(app.graph.workflow.__file__), Path(app.graph.context.__file__),
        *sorted(Path(app.graph.nodes.__file__).parent.glob("*.py")),
    ]


def workflow_source() -> str:
    """The workflow's source: `app.graph.workflow`, `app.graph.context` and every module of `app.graph.nodes`, where
    its nodes live.

    For the few tests that pin wording rather than behaviour; one place to read
    it, so a node moving between these modules keeps its pins."""
    return "\n".join(path.read_text(encoding="utf-8") for path in workflow_source_files())


def run_node(name: str, state: dict[str, Any], root: str, patches: dict[str, Any] | None = None) -> dict[str, Any]:
    """The update one node returns for `state`, with `patches` (target -> replacement) applied."""
    from app.graph.workflow import build_workflow_graph

    with ExitStack() as stack:
        for target, replacement in (patches or {}).items():
            stack.enter_context(patch(target, replacement))
        graph = build_workflow_graph(checkpointer=MemorySaver(), repo_root=root)
        return graph.nodes[name].bound.invoke(state, CONFIG)


def reported(description: str, owner: str = "backend", **fields: Any) -> Any:
    """A defect as a test round reports it."""
    from app.agents.specialists import ReportedDefect

    return ReportedDefect(
        description=description, severity=fields.pop("severity", "major"), reproduction_steps="r",
        expected_behavior="e", actual_behavior=fields.pop("actual_behavior", "a"), owner=owner, **fields,
    )


def a_test_round(
    tmp_path,
    found: list[Any] | tuple[Any, ...] = (),
    *,
    state: dict[str, Any] | None = None,
    patches: dict[str, Any] | None = None,
    gated: Callable[..., dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """`test_and_triage` on a round whose testing specialist reports `found`.

    Nothing measured is known (no locked suite, no saved run, no unit command), so
    the round is the testing specialist's. Returns the node's update and the
    keyword arguments of each `_run_gated_agent` call.
    """
    from app.agents.specialists import SpecialistOutput

    calls: list[dict[str, Any]] = []

    def the_round(state, config, **kwargs):
        calls.append(kwargs)
        if gated is not None:
            return gated(state, config, **kwargs)
        return {"__test_result__": SpecialistOutput(changed_files=[], defects=list(found))}

    made = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "milestone_plan": SimpleNamespace(selected_sprint_goal="Build features", milestone_scope=[], delegated_tasks=[]),
        "test_round": 1,
        "specialist_outputs": {},
        "review_defects": [],
        "current_sprint_index": 0,
        **(state or {}),
    }
    every = {
        "app.graph.acceptance_nodes.acceptance_for_round": lambda state: ("", []),
        "app.graph.acceptance_nodes.reopen_the_suite_for": lambda *args, **kwargs: None,
        "app.graph.acceptance_nodes.beyond_repair": lambda *args: [],
        "app.graph.acceptance_nodes._failing_due": lambda state: ([], ""),
        "app.graph.workflow._run_unit_tests_procedurally": lambda root: (None, ""),
        "app.graph.acceptance_nodes.suite.is_locked": lambda root: False,
        "app.graph.acceptance_nodes.suite.last_result": lambda root: None,
        "app.agents.specialists.what_the_files_already_prove": lambda *args: [],
        "app.graph.acceptance_nodes.interface_defects": lambda state: [],
        "app.graph.acceptance_nodes.pack_contract_defects": lambda state: [],
        "app.graph.acceptance_nodes.failing_due_defects": lambda state, reported: [],
        "app.graph.workflow._run_gated_agent": the_round,
        **(patches or {}),
    }
    return run_node("test_and_triage", made, str(tmp_path), every), calls


def an_architect_state(tmp_path, **more: Any) -> dict[str, Any]:
    """What the principal architect's node reads, for a TypeScript service in `notes-api/`."""
    from app.agents.stack_selector import StackSelectorOutput, TechnologyStack
    from app.state import RepositoryContext

    (tmp_path / ".project-directory").write_text("notes-api\n")
    (tmp_path / "notes-api").mkdir(exist_ok=True)
    stack = TechnologyStack(language="TypeScript", framework="Hono", frontend_framework="", database="SQLite",
                            testing_framework="node:test, Playwright", product_kind="http_api", additional_tools=[])
    return {
        "stack_selection": StackSelectorOutput(technology_stack=stack, rationale="As the brief asks."),
        "document": SimpleNamespace(text="Notes over HTTP."),
        "repository": RepositoryContext(root_path=str(tmp_path), branch="main", commit="abc", status="clean"),
        "product_intake": {"product_name": "Notes"},
        "tools_models": {"plan": "local"},
        **more,
    }


def a_specification(**fields: Any) -> Any:
    """A complete technical specification, with `fields` in place of its defaults."""
    from app.agents.principal_architect import TechnicalSpecificationOutput

    every = {name: ["written"] for name, field in TechnicalSpecificationOutput.model_fields.items()
             if field.annotation == list[str]}
    return TechnicalSpecificationOutput(**{**every, "product_scope": "Notes over HTTP.",
                                           "file_plan": ["notes-api/src/app.ts: routes"], **fields})


def an_architect(
    state: dict[str, Any],
    answer: Any,
    *,
    fast: bool = False,
    patches: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """`principal_architect` answering `answer`: (its update, what the architect agent was asked, what any
    section-writing call was asked). Fast delivery writes the sections with the deployment's own model."""
    from unittest.mock import MagicMock

    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    import json
    import re

    written: list[str] = []
    agent_requests: list[str] = []

    class Writer(BaseChatModel):
        @property
        def _llm_type(self) -> str:
            return "stand-in"

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            text = str(messages[-1].content)
            written.append(text)
            if '{"sections"' in text:
                reply = {"sections": ["testing"]}
            else:
                names = re.search(r"Its keys are exactly: ([^.]+)\.", text).group(1).split(", ")
                reply = {name: ["written"] for name in names}
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=json.dumps(reply)))])

    def gated(state, config, *, initial_request, output_key, **kwargs):
        agent_requests.append(initial_request["messages"][-1]["content"])
        return {output_key: answer, "stage": "architecture_review"}

    every = {
        "app.models.build_default_chat_model": lambda *args, **kwargs: Writer(),
        "app.graph.workflow.create_principal_architect_agent": lambda **kwargs: MagicMock(),
        "app.agents.research_brief.research_notes": lambda *args, **kwargs: "",
        "app.graph.workflow._fast_delivery": lambda: fast,
        "app.graph.workflow._run_gated_agent": gated,
        **(patches or {}),
    }
    update = run_node("principal_architect", state, state["repository"].root_path, every)
    return update, agent_requests, written


def a_design_finding(severity: str = "major", **fields: Any) -> Any:
    from app.agents.architecture_reviewer import ArchitectureReviewFinding

    return ArchitectureReviewFinding(severity=severity, description=fields.pop("description", "The testing section is thin."),
                                     evidence="testing", required_remediation="Say how each criterion is tested.",
                                     **fields)


def an_architecture_review(
    tmp_path,
    review: Any,
    *,
    state: dict[str, Any] | None = None,
    patches: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """`architecture_review` whose reviewer returns `review`, with none of the workflow's own checks finding
    anything unless `patches` says so: (the update, what the reviewer was asked)."""
    from unittest.mock import MagicMock

    asked: list[str] = []

    def gated(state, config, *, initial_request, output_key, **kwargs):
        asked.append(initial_request["messages"][-1]["content"])
        return {output_key: review}

    made = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "document": SimpleNamespace(text="Notes over HTTP."),
        "technical_specification": a_specification(),
        **(state or {}),
    }
    every = {
        "app.graph.workflow._approved_once_the_harness_s_findings_are_settled": lambda state, spec: None,
        "app.graph.workflow._decided_after_one_revision": lambda state, spec: None,
        "app.graph.workflow.create_architecture_reviewer_agent": lambda **kwargs: MagicMock(),
        "app.graph.workflow._the_setup_for_the_review": lambda state: "",
        "app.graph.workflow._a_success_measure_the_specification_drops": lambda state, spec: None,
        "app.graph.workflow._a_brief_feature_the_specification_defers": lambda state, spec: None,
        "app.graph.workflow._contract_lines_nothing_can_read": lambda state: None,
        "app.graph.workflow._the_same_command_in_another_order": lambda state, spec: None,
        "app.graph.workflow._behaviour_the_specification_gives_kept_files": lambda state, spec: None,
        "app.graph.workflow._run_gated_agent": gated,
        **(patches or {}),
    }
    return run_node("architecture_review", made, str(tmp_path), every), asked


def a_milestone_finding(severity: str = "major", category: str = "correctness", **fields: Any) -> Any:
    from app.agents.milestone_reviewer import MilestoneReviewFinding

    return MilestoneReviewFinding(severity=severity, category=category,
                                  description=fields.pop("description", "Deleting a note leaves it listed."),
                                  affected_files=fields.pop("affected_files", []), required_remediation="Remove it.",
                                  **fields)


def a_milestone_verdict(status: str, *findings: Any) -> Any:
    from app.agents.milestone_reviewer import MilestoneReviewOutput

    return MilestoneReviewOutput(status=status, findings=list(findings), acceptance_evidence="Ran the suite.",
                                 documentation_reviewed=True, tests_reviewed=True)


def a_milestone_review(
    tmp_path,
    review: Any,
    *,
    state: dict[str, Any] | None = None,
    fast: bool = False,
    patches: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """`milestone_review` whose reviewer returns `review` for a sprint with nothing else on record."""
    from unittest.mock import MagicMock

    made = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "milestone_plan": SimpleNamespace(selected_sprint_goal="Users can keep notes", milestone_scope=[],
                                          delegated_tasks=[]),
        "specialist_outputs": {},
        "current_sprint_index": 0,
        "milestone_revision_count": 0,
        **(state or {}),
    }
    every = {
        "app.graph.workflow.create_milestone_reviewer_agent": lambda **kwargs: MagicMock(),
        "app.graph.workflow.build_milestone_review_request":
            lambda *args, **kwargs: {"messages": [{"role": "user", "content": "Review the sprint."}]},
        "app.graph.acceptance_nodes.acceptance_text_for": lambda state: "",
        "app.models.vision.the_reviewer_reads_images": lambda: False,
        "app.graph.workflow._fast_delivery": lambda: fast,
        "app.graph.workflow._run_gated_agent": lambda state, config, **kwargs: {"__milestone_review__": review},
        **(patches or {}),
    }
    return run_node("milestone_review", made, str(tmp_path), every)


def a_defect(description: str, owner: str = "backend", **fields: Any) -> Any:
    """An open defect as the remediation cycle holds it."""
    from app.sprint import Defect

    return Defect(description=description, severity=fields.pop("severity", "major"), reproduction_steps="r",
                  expected_behavior=fields.pop("expected_behavior", "e"), actual_behavior=fields.pop("actual_behavior", "a"),
                  owner=owner, affected_files=fields.pop("affected_files", ["app/server.js"]), **fields)


def a_fix_stage(
    tmp_path,
    defects: list[Any],
    *,
    answer: Any = None,
    defect_index: int = 0,
    state: dict[str, Any] | None = None,
    patches: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, list[Any]]]:
    """`defect_remediation` on `defects[defect_index]`, whose fixer answers `answer` and whose fix breaks nothing
    unless `patches` says so. Returns the update and what was asked: the fixer's requests, the keyword arguments of
    the fix request's builder, and each `_run_gated_agent` call."""
    from unittest.mock import MagicMock

    from app.agents.specialists import SpecialistOutput
    from app.sprint import RemediationCycle

    asked: dict[str, list[Any]] = {"requests": [], "built": [], "gated": []}
    fixed = answer if answer is not None else SpecialistOutput(changed_files=["app/server.js"], tests=["tests/x.test.js"])

    def gated(state, config, *, initial_request, **kwargs):
        asked["gated"].append(kwargs)
        asked["requests"].append(initial_request["messages"][-1]["content"])
        return {"__fix_result__": fixed}

    def built(*args, **kwargs):
        asked["built"].append(kwargs)
        return {"messages": [{"role": "user", "content": "Fix the defect."}]}

    made = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "remediation": RemediationCycle(sprint_goal="g", defects=list(defects)),
        "defect_cursor": defect_index,
        "test_round": 2,
        "current_sprint_index": 0,
        "specialist_outputs": {},
        **(state or {}),
    }
    every = {
        "app.graph.workflow.create_specialist_agent": lambda *args, **kwargs: MagicMock(),
        "app.graph.workflow.build_defect_fix_request": built,
        "app.graph.workflow._what_the_last_failure_printed": lambda *args: "",
        "app.graph.workflow._closed_if_an_earlier_fix_resolved_it": lambda *args: None,
        "app.graph.workflow._what_the_ledger_confirms": lambda *args: "npm test",
        "app.graph.acceptance_nodes.done_by_the_definition": lambda state: [],
        "app.graph.engineering.before_a_fix": lambda *args: "",
        "app.graph.engineering.after_a_fix": lambda *args, **kwargs: [],
        "app.graph.workflow._run_gated_agent": gated,
        **(patches or {}),
    }
    return run_node("defect_remediation", made, str(tmp_path), every), asked


def a_work_order(role: str, description: str, files: list[str]) -> Any:
    from app.agents.technical_lead import SpecialistTask

    return SpecialistTask(specialist_role=role, task_description=description, acceptance_criteria=["works"],
                          files=list(files))


def a_builder(
    tmp_path,
    orders: list[Any],
    *,
    worker: int | None = None,
    state: dict[str, Any] | None = None,
    patches: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """The next work order of `orders` dispatched in linear mode - or, with `worker`, that one order run by the
    parallel worker. Returns the update and what each builder was asked. The plan counts as drafted already
    unless `state` says `drafted_for_plan` is False."""
    from unittest.mock import MagicMock

    from app.agents.specialists import SpecialistOutput

    asked: list[str] = []

    def gated(state, config, *, initial_request, output_key, **kwargs):
        asked.append(initial_request["messages"][-1]["content"])
        return {output_key: SpecialistOutput(changed_files=[])}

    made = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "milestone_plan": SimpleNamespace(selected_sprint_goal="g", milestone_scope=[], delegated_tasks=list(orders)),
        "specialist_outputs": {},
        "current_sprint_index": 0,
        "drafted_for_plan": True,
        **(state or {}),
    }
    if worker is not None:
        made.update({"__worker_task": orders[worker], "__worker_index": worker})
    every = {
        "app.server.runtime_settings.effective_settings": lambda: SimpleNamespace(execution_mode="linear"),
        "app.graph.workflow.create_specialist_agent": lambda *args, **kwargs: MagicMock(),
        "app.graph.workflow.build_specialist_task_request":
            lambda *args, **kwargs: {"messages": [{"role": "user", "content": "Build the work order."}]},
        "app.graph.workflow._run_gated_agent": gated,
        **(patches or {}),
    }
    node = "specialist_worker" if worker is not None else "specialist_dispatch"
    return run_node(node, made, str(tmp_path), every), asked


def a_lead(
    tmp_path,
    plan: Any,
    *,
    state: dict[str, Any] | None = None,
    patches: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, list[Any]]]:
    """`technical_lead` answering `plan` for sprint 1 of 2, in thorough delivery. Returns the update and what was
    asked: the lead's requests, and each readiness check's plan and keyword arguments."""
    from unittest.mock import MagicMock

    asked: dict[str, list[Any]] = {"requests": [], "readiness": []}

    def gated(state, config, *, initial_request, output_key, **kwargs):
        asked["requests"].append(initial_request["messages"][-1]["content"])
        return {output_key: plan}

    def readiness(milestone, root, **kwargs):
        asked["readiness"].append({"plan": milestone, **kwargs})
        return []

    from app.agents.scrum_master import SprintDefinition, SprintPlanOutput

    request = lambda *args, **kwargs: {"messages": [{"role": "user", "content": "Plan the sprint."}]}  # noqa: E731
    made = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "sprint_plan": SprintPlanOutput(sprints=[
            SprintDefinition(goal="Users can keep notes", user_value="v", in_scope=["Add a note", "List the notes"],
                             acceptance_criteria=["AC-1 a note is kept"]),
            SprintDefinition(goal="Users can share notes", user_value="v", in_scope=["Share a note"],
                             acceptance_criteria=["AC-9 a note is shared"]),
        ]),
        "current_sprint_index": 0,
        **(state or {}),
    }
    every = {
        "app.graph.workflow.create_technical_lead_agent": lambda **kwargs: MagicMock(),
        "app.graph.workflow._a_dispute_is_due": lambda state: False,
        "app.graph.acceptance_nodes.sprint_already_done": lambda state: "",
        "app.graph.acceptance_nodes.criteria_brief": lambda state: "",
        "app.graph.workflow.build_milestone_planning_request": request,
        "app.graph.workflow.build_milestone_revision_request": request,
        "app.graph.workflow._fast_delivery": lambda: False,
        "app.analysis.work_orders.readiness_problems": readiness,
        "app.graph.workflow._run_gated_agent": gated,
        **(patches or {}),
    }
    return run_node("technical_lead", made, str(tmp_path), every), asked


def a_plan(*orders: Any, goal: str = "Users can keep notes") -> Any:
    from app.agents.technical_lead import MilestonePlanOutput

    return MilestonePlanOutput(selected_sprint_goal=goal, milestone_scope=[goal], delegated_tasks=list(orders))


#: What `build_judgement_model` hands the graph in `a_dispute`, so a test can tell
#: the judgement model from the build model by identity.
JUDGEMENT_MODEL = SimpleNamespace(name="the judgement model")


def a_dispute(
    tmp_path,
    failing: list[tuple[str, str, str]],
    called_wrong: list[str],
    *,
    suite_text: str = "",
    reopened: dict[str, Any] | None = None,
    refused_for_their_quote: list[tuple[str, str]] = (),
    state: dict[str, Any] | None = None,
    patches: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, list[Any]]]:
    """`acceptance_dispute` on `failing` locked tests (name, criterion, message), whose ruling calls `called_wrong`
    wrong and has `refused_for_their_quote` refused; the suite reopens with `reopened` (None: it may not).
    Returns the update and what each step was asked."""
    asked: dict[str, list[Any]] = {"rulings": [], "reopen": []}
    suite_file = tmp_path / "tests" / "acceptance" / "test_suite.py"
    suite_file.parent.mkdir(parents=True, exist_ok=True)
    suite_file.write_text(suite_text, encoding="utf-8")

    def tests_it_names(ruling, names, *, standard, refused, criteria_of):
        asked["rulings"].append({"names": names, "standard": standard, "criteria_of": criteria_of})
        refused.extend(refused_for_their_quote)
        return list(called_wrong)

    def reopen(state, broken, return_to="test_and_triage", **kwargs):
        asked["reopen"].append({"broken": broken, "return_to": return_to, **kwargs})
        return reopened

    made = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "document": SimpleNamespace(text="The brief: notes are kept until deleted."),
        "current_sprint_index": 0,
        **(state or {}),
    }
    every = {
        "app.models.roles.build_judgement_model": lambda model, *args, **kwargs: JUDGEMENT_MODEL,
        "app.graph.workflow._the_locked_tests_still_failing": lambda state: list(failing),
        "app.graph.workflow.create_suite_dispute_agent": lambda **kwargs: object(),
        "app.graph.workflow._run_gated_agent": lambda state, config, **kwargs: {"__suite_dispute__": object()},
        "app.acceptance.suite.suite_files": lambda root: [suite_file],
        "app.acceptance.suite.the_suite_s_own_words_when_last_measured": lambda root: "",
        "app.acceptance.requests.shares_one_service": lambda root: False,
        "app.agents.suite_dispute.tests_it_names": tests_it_names,
        "app.graph.acceptance_nodes.tests_that_fail_alone": lambda root, named: (list(named), []),
        "app.graph.acceptance_nodes.tests_whose_service_stayed_up": lambda root, named: (list(named), []),
        "app.graph.acceptance_nodes.reopen_the_suite_for": reopen,
        **(patches or {}),
    }
    return run_node("acceptance_dispute", made, str(tmp_path), every), asked


def tool_names(agent: Any) -> set[str]:
    """The tools a compiled agent will run, read off its `tools` node (the graph has no tool list of its own)."""
    node = (getattr(agent, "nodes", None) or {}).get("tools")
    inner = getattr(node, "bound", None) or getattr(node, "runnable", None) or node
    return set(getattr(inner, "tools_by_name", None) or {})


#: A brief of three features, numbered AC-1 to AC-3 by `an_acceptance_review`.
NOTES_BRIEF = "# Brief\n## Features\n- Add a note\n- Delete a note\n- Notes persist between page refreshes\n"


def an_acceptance_review(
    tmp_path,
    spec: str,
    *,
    passed: list[str] | tuple[str, ...] = (),
    failed: list[str] | tuple[str, ...] = (),
    deferred: dict[str, str] | None = None,
    review: Any = None,
    state: dict[str, Any] | None = None,
    patches: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """`acceptance_review` of a suite holding `spec` (`notes/acceptance/notes.spec.js`) over `NOTES_BRIEF`'s criteria,
    with `deferred` deferred. The suite's run in the sandbox reports `passed` and `failed` test titles; the QA lead
    answers `review` (approved, no findings, when None). Returns the update."""
    from app.acceptance import junit, suite
    from app.acceptance.criteria import number
    from app.graph import acceptance_nodes

    (tmp_path / ".project-directory").write_text("notes\n")
    suite.save_criteria(tmp_path, number(NOTES_BRIEF), dict(deferred or {}))
    written = tmp_path / "notes" / "acceptance" / "notes.spec.js"
    written.parent.mkdir(parents=True, exist_ok=True)
    written.write_text(spec)
    ran = suite.AcceptanceResult(ran=True, exit_code=1 if failed else 0, command="npm run test:acceptance",
                                 report=junit.Report(found=True, tests=[
                                     *(junit.TestResult(name=n) for n in passed),
                                     *(junit.TestResult(name=n, outcome="failed", message="nope") for n in failed)]))
    answer = review if review is not None else SimpleNamespace(approved=True, findings=[])
    made = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "document": SimpleNamespace(text=NOTES_BRIEF),
        "product_intake": SimpleNamespace(product_name="Notes", success_measures=[]),
        "stack_selection": SimpleNamespace(technology_stack=SimpleNamespace(product_kind="browser_app")),
        "acceptance_round": 1,
        **(state or {}),
    }
    every = {
        "app.acceptance.suite.run": lambda root, **kwargs: ran,  # the suite's run in the sandbox
        "app.agents.acceptance_reviewer.create_acceptance_reviewer_agent": lambda *args, **kwargs: object(),
        "app.graph.workflow._run_gated_agent":
            lambda state, config, *, output_key, next_stage, **kwargs: {output_key: answer, "stage": next_stage},
        **(patches or {}),
    }
    with ExitStack() as stack:
        for target, replacement in every.items():
            stack.enter_context(patch(target, replacement))
        context = acceptance_nodes.Context(model=None, judgement_model=None, checkpointer=None, repo_root=None)
        return acceptance_nodes.acceptance_review(made, {"configurable": {"thread_id": "t"}}, context)


def an_acceptance_review_measured(
    tmp_path,
    measured: Any,
    *,
    files: dict[str, str] | None = None,
    pack: str | None = None,
    reviews: tuple[Any, ...] = (),
    state: dict[str, Any] | None = None,
    patches: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """`acceptance_review` on a suite of `files` (name -> text, under `notes/acceptance/`) that ran as `measured`.

    `measured` is what running the suite gave (an `AcceptanceResult`, or a function of the root): the product's own
    test command is the edge stood in for. The QA lead answers `reviews` in turn; nothing else is stubbed."""
    from app.acceptance import suite
    from app.stacks import contract, pack_named

    if pack:
        contract.write(tmp_path, pack_named(pack), "notes", "Notes")
    else:
        (tmp_path / ".project-directory").write_text("notes\n")
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in (files or {}).items():
        (folder / name).write_text(text)
    answers = list(reviews)

    def the_qa_lead(state, config, *, output_key, next_stage, **kwargs):
        return {output_key: answers.pop(0), "stage": next_stage}

    made = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "document": SimpleNamespace(text="# Brief\n## Acceptance Criteria\n- Notes are kept\n"),
        "acceptance_round": 1,
        **(state or {}),
    }
    every = {
        "app.acceptance.suite.run": measured if callable(measured) else (lambda root: measured),
        "app.acceptance.spec_dry_run.findings": lambda root: [],
        "app.graph.workflow._run_gated_agent": the_qa_lead,
        "app.agents.specialists.create_specialist_agent": lambda *args, **kwargs: object(),
        "app.agents.acceptance_reviewer.create_acceptance_reviewer_agent": lambda *args, **kwargs: object(),
        **(patches or {}),
    }
    return run_node("acceptance_review", made, str(tmp_path), every)



def a_scripted_model(*replies: Any) -> Any:
    """A chat model that answers `replies` in turn and records each request it is sent, in `requests`.

    The model endpoint is a role agent's one unmanaged edge; this stands in for it, so the agent runs for real - its
    tools, its middleware, its workspace - and a test reads what the model was offered and sent."""
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

    class _Scripted(GenericFakeChatModel):
        requests: list[dict[str, Any]] = []

        def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
            names = [getattr(tool, "name", None) or (tool.get("function") or tool).get("name") for tool in tools]
            self.requests.append({"tools": names})
            return self

        def _generate(self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any) -> Any:
            if not self.requests or "messages" in self.requests[-1]:
                self.requests.append({})
            self.requests[-1]["messages"] = list(messages)
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    model = _Scripted(messages=iter(replies))
    model.requests = []
    return model


def an_answer(**fields: Any) -> Any:
    """A model reply handing back a role agent's answer, as `a_role_agent` builds the agent."""
    from langchain_core.messages import AIMessage

    return AIMessage(content="", tool_calls=[{"name": "Answer", "args": {"summary": "done", **fields},
                                              "id": "answer", "type": "tool_call"}])


def a_role_agent(root: Any, *replies: Any, name: str = "specialist_backend_0", stage: str = "build",
                 config: dict[str, Any] | None = None, **kwargs: Any) -> tuple[Any, Any]:
    """A role agent built as a run builds one on `root`, driven by a model that answers `replies` in turn.

    Returns what the agent ended with and the model (`requests`: the tools offered and the messages sent on each
    call). With no `replies` it is built only, and `(None, agent)` comes back."""
    from pydantic import BaseModel

    from app.agents.role_agent import create_role_agent

    class Answer(BaseModel):
        summary: str

    model = kwargs.pop("model", None) or a_scripted_model(*replies)
    agent = create_role_agent(name=name, stage=stage, system_prompt="Do the work.", response_format=Answer,
                              model=model, repo_root=str(root), **kwargs)
    if not replies:
        return None, agent
    configurable = {"thread_id": "t", **((config or {}).get("configurable") or {})}
    result = agent.invoke({"messages": [{"role": "user", "content": "Go."}]},
                          {**(config or {}), "configurable": configurable, "recursion_limit": 30})
    return result, model


def a_served_model(name: str = "m", **kwargs: Any) -> tuple[Any, list[dict[str, Any]]]:
    """The deployment's chat model class, its server stood in for at the HTTP edge.

    Returns the model and the request bodies the server was sent, in order; every request is answered "ok"."""
    import json

    import httpx

    from app.models import CompatibleChatOpenAI

    sent: list[dict[str, Any]] = []

    def server(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={
            "id": "c", "object": "chat.completion", "created": 1, "model": name,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        })

    model = CompatibleChatOpenAI(model=name, api_key="unused", base_url="http://model.test/v1", max_retries=0,
                                 http_client=httpx.Client(transport=httpx.MockTransport(server)), **kwargs)
    return model, sent


def offered_tools(agent: Any) -> set[str]:
    """The tools a built agent can run."""
    return set(agent.nodes["tools"].bound._tools_by_name)
