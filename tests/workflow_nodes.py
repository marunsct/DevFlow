"""Run one node of the compiled workflow graph on a made state, for behaviour tests.

The nodes are closures inside `build_workflow_graph`; the compiled graph is the
one handle on them that holds wherever they come to be defined. Tests here call
a node through `graph.nodes[name]` rather than read its source, so a node lifted
out of `workflow.py` keeps its tests.
"""
from __future__ import annotations

from contextlib import ExitStack
from types import SimpleNamespace
from typing import Any, Callable
from unittest.mock import patch

from langgraph.checkpoint.memory import MemorySaver

CONFIG = {"configurable": {"thread_id": "t", "run_id": "r"}}


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
