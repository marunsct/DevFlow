"""Drive one defect's fix stage on a built graph, with every model call stubbed, recording what each step was given.

Not a test module: the fix-stage tests import it, so the behaviour they hold is reached through the graph's own
nodes (`defect_remediation`, `defect_fix_worker`) rather than through the text of `app.graph.workflow`, and a
restructured workflow module breaks none of them (launch review LR.50).

What is stubbed: the agent (`create_specialist_agent` and `_run_gated_agent`), the commits before and after a fix
(`engineering.before_a_fix` / `after_a_fix`), the rewrite and candidate fixes (`app.graph.rewritten_fixes`), the
localisation and the defect's own tests. What runs as it ships: the node, `_fix_one`, `_fixed_by_rewriting`,
`_the_fix_request` and the model choice (`_the_build_model`).
"""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from langgraph.checkpoint.memory import MemorySaver

from app.agents.specialists import SpecialistOutput
from app.sprint import Defect, RemediationCycle

CONFIG = {"configurable": {"thread_id": "t", "run_id": "r", "app_run_id": "r"}}
#: The text `build_defect_fix_request` is stubbed to return; every section the stage adds follows it.
BASE_REQUEST = "THE FIX REQUEST"


def a_defect(description: str = "The count is wrong", **extra: Any) -> Defect:
    fields = {"severity": "major", "reproduction_steps": "r", "expected_behavior": "e", "actual_behavior": "a",
              "owner": "backend", "affected_files": ["app/count.js"], **extra}
    return Defect(description=description, **fields)


def a_state(root: Any, *defects: Defect, **more: Any) -> dict[str, Any]:
    return {
        "repository": SimpleNamespace(root_path=str(root)),
        "remediation": RemediationCycle(sprint_goal="g", defects=list(defects) or [a_defect()]),
        "defect_cursor": 0, "test_round": 2, "current_sprint_index": 0, "specialist_outputs": {},
        **more,
    }


def two_models(monkeypatch: Any) -> tuple[Any, Any]:
    """A build model and a distinct judgement model; the graph is built on the first."""
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    build = FakeListChatModel(responses=["unused"], name="build")
    judge = FakeListChatModel(responses=["unused"], name="judge")
    monkeypatch.setattr("app.models.roles.build_judgement_model", lambda model, *a, **k: judge)
    return build, judge


@dataclass
class Seen:
    """What each step of the fix stage was given, in the order it happened."""

    events: list[str] = field(default_factory=list)
    agent_models: list[Any] = field(default_factory=list)
    requests: list[str] = field(default_factory=list)
    request_args: list[tuple] = field(default_factory=list)
    rewrites: list[dict[str, Any]] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    localised: list[tuple] = field(default_factory=list)
    tests_checked: list[tuple] = field(default_factory=list)
    shown: list[tuple] = field(default_factory=list)
    settled: list[Any] = field(default_factory=list)
    during: list[Any] = field(default_factory=list)


def run(
    root: Any,
    state: dict[str, Any],
    *,
    node: str = "defect_remediation",
    answer: Any = None,
    rewrite: Any = None,
    candidate: Any = None,
    candidate_model: Any = None,
    located: list[str] | None = None,
    fast: bool = False,
    approves: bool = True,
    broke: list[str] = (),
    model: Any = None,
    printed: dict[str, Any] | None = None,
    side_by_side: bool = False,
    during: Any = None,
    real_brief: bool = False,
    measure: Any = None,
) -> tuple[dict[str, Any], Seen]:
    """Run `node` once on `state`.

    `answer`: the agent loop's answer (`__fix_result__`). `rewrite` / `candidate`: what `fix_by_rewriting` /
    `fix_by_candidates` return. `candidate_model`: the model candidates are asked of (None asks none). `located`:
    what the localisation finds. `fast`: fast delivery. `approves`: whether the run approves its own writes.
    `broke`: what `engineering.after_a_fix` says the fix broke. `printed`: what each failure reader returns, by
    "criteria" / "unit" / "last". `side_by_side`: parallel mode's batches. `during`: called with the stage's name
    while its agent runs; what it returns is kept in `Seen.during`. `real_brief`: the brief and what each failure
    reader returns are built as they ship, from the workspace and the state. `measure`: called as
    `engineering.after_a_fix` is, in its place, when a test measures a workspace of its own (it may call the real one).
    A callable `rewrite` is called with the defect and the rewrite's arguments, and what it returns is the rewrite's output.
    """
    from app.graph import workflow

    seen = Seen()
    answer = answer if answer is not None else SpecialistOutput(changed_files=["app/count.js"], tests=["t.test.js"])
    printed = printed or {}

    def agent(owner, *args, **kwargs):
        seen.agent_models.append(kwargs.get("model"))
        seen.events.append("agent")
        return MagicMock()

    def request(*args, **kwargs):
        seen.request_args.append(args)
        return {"messages": [{"role": "user", "content": BASE_REQUEST}]}

    def gated(state, config, *, initial_request, **kwargs):
        content = initial_request["messages"][-1]["content"]
        seen.requests.append(content if isinstance(content, str) else str(content))
        seen.events.append("agent loop")
        if during is not None:
            seen.during.append(during(kwargs["stage_name"]))
        return {"__fix_result__": answer}

    def rewriting(defect, root_, model_, **kwargs):
        seen.rewrites.append({"defect": defect, "model": model_, **kwargs})
        seen.events.append("rewrite")
        return rewrite(defect, **kwargs) if callable(rewrite) else rewrite

    def candidates(defect, root_, model_, check, **kwargs):
        seen.candidates.append({"defect": defect, "model": model_, "check": check, **kwargs})
        seen.events.append("candidates")
        check()
        return candidate

    def localising(defect, failure, root_, model_, found, may_write):
        seen.localised.append((defect, model_))
        return list(located if located is not None else found)

    def the_tests_pass(root_, defect):
        seen.tests_checked.append((str(root_), defect))
        return False

    def measured(*args, **kwargs):
        seen.events.append("measured")
        return list(broke)

    original_settle = workflow._settle_the_fix

    def settle(state, cycle, index, stage_name, fix_result, **kwargs):
        seen.settled.append(fix_result)
        return original_settle(state, cycle, index, stage_name, fix_result, **kwargs)

    def shown(stage, defect, text, **kwargs):
        seen.shown.append((stage, text))

    stubs = {
        "app.delivery.fast": {"return_value": fast},
        "app.agents.thinking.without_reasoning": {"side_effect": lambda m: SimpleNamespace(quiet=m)},
        "app.graph.workflow._fixes_run_side_by_side": {"return_value": side_by_side},
        "app.graph.workflow.create_specialist_agent": {"side_effect": agent},
        "app.graph.workflow.build_defect_fix_request": {"side_effect": request},
        "app.graph.workflow._what_the_criteria_s_tests_printed": {"return_value": printed.get("criteria")},
        "app.graph.workflow._what_the_unit_tests_printed": {"return_value": printed.get("unit")},
        "app.graph.workflow._what_the_last_failure_printed": {"return_value": printed.get("last")},
        "app.graph.workflow._closed_if_an_earlier_fix_resolved_it": {"return_value": None},
        "app.graph.workflow._what_the_ledger_confirms": {"return_value": "npm test"},
        "app.graph.workflow._the_run_approves_its_own_writes": {"return_value": approves},
        "app.graph.workflow._the_defect_s_tests_pass": {"side_effect": the_tests_pass},
        "app.graph.workflow._settle_the_fix": {"side_effect": settle},
        "app.graph.workflow._run_gated_agent": {"side_effect": gated},
        "app.graph.acceptance_nodes.done_by_the_definition": {"return_value": []},
        "app.graph.engineering.before_a_fix": {"return_value": "base"},
        "app.graph.engineering.after_a_fix": {"side_effect": measure or measured},
        "app.graph.rewritten_fixes.fix_by_rewriting": {"side_effect": rewriting},
        "app.graph.rewritten_fixes.fix_by_candidates": {"side_effect": candidates},
        "app.graph.rewritten_fixes.what_failed": {"return_value": "it failed"},
        "app.graph.rewritten_fixes.files_to_fix": {"side_effect": lambda d, f, r, m: list(d.affected_files)},
        "app.graph.localisation.localised": {"side_effect": localising},
        "app.graph.bounded_fixes.the_candidate_model": {"return_value": candidate_model},
        "app.observability.defect_ledger.shown": {"side_effect": shown},
    }
    if real_brief:
        for built in ("build_defect_fix_request", "_what_the_criteria_s_tests_printed", "_what_the_unit_tests_printed",
                      "_what_the_last_failure_printed"):
            stubs.pop(f"app.graph.workflow.{built}")
    with ExitStack() as stack:
        for target, how in stubs.items():
            stack.enter_context(patch(target, **how))
        graph = workflow.build_workflow_graph(model, checkpointer=MemorySaver(), repo_root=str(root))
        update = graph.nodes[node].bound.invoke(state, CONFIG)
    return update, seen


def one_at_a_time(root: Any, defects: list[Defect], *, between: Any = None, **more: Any) -> list[str]:
    """The fix stage of every defect a linear fix round sends, in order, until it hands back to the test round.

    Each visit is given what the round records between visits (its cursor and the stages it has worked), as the
    graph's state carries them. `between(visits, defects)` returns the defects as the next visit reads them - as a
    test round raising one again, or a deploy changing the order, leaves them.
    """
    sent: list[str] = []
    carried: dict[str, Any] = {}
    for visits in range(4 * len(defects) + 4):
        if between is not None:
            defects = between(visits, defects)
        update, seen = run(root, a_state(root, *defects, **{**more, **carried}))
        if update.get("stage") == "test_and_triage":
            return sent
        sent += [stage for stage, _ in seen.shown]
        carried = {key: update[key] for key in ("defect_cursor", "fixes_tried") if key in update}
    raise AssertionError(f"the fix round never ended: it sent {sent}")
