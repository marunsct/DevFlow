"""The stages between an approved architecture and the first sprint plan.

    scaffold -> acceptance_author -> acceptance_review -> [user review] -> scrum_master

and the parts of every later stage that read the acceptance suite. Kept out of
`workflow.py` so the definition of done has one home; the graph builder wraps
each function in a node with the run's models and checkpointer.

The order is how a software company starts a product: the project is set up so
its tests run, QA writes the tests that decide when it is done from the agreed
criteria, a QA lead reviews them, and only then is the work planned - against
criteria every sprint can be measured by.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.acceptance import requests as acceptance_requests
from app.acceptance import suite
from app.acceptance.criteria import number
from app.stacks import contract, pack_named

logger = logging.getLogger(__name__)

#: How many times QA writes the suite before it is locked as it stands. Each
#: pass after the first is handed what the last review found.
MAX_ACCEPTANCE_ROUNDS = 3

#: Review point: the acceptance suite, before it is locked.
ACCEPTANCE_REVIEW = "acceptance_tests"


@dataclass
class Context:
    """What every node of the run is built with."""

    model: Any
    judgement_model: Any
    checkpointer: Any
    repo_root: str | None
    allow_subdirectories: bool = True


def _root(state: Any) -> str:
    return state["repository"].root_path


def _stack(state: Any) -> Any:
    return getattr(state.get("stack_selection"), "technology_stack", None)


# --- scaffold ------------------------------------------------------------------

def scaffold(state: Any, config: RunnableConfig, ctx: Context) -> dict[str, Any]:
    """Scaffold the chosen pack into the project directory, proven by its smoke tests."""
    from app.graph.workflow import APP_RUN_ID_KEY, _handing_on, _stop_if_cancelled

    _stop_if_cancelled(config["configurable"].get(APP_RUN_ID_KEY))
    root = _root(state)
    pack = pack_named(state.get("stack_pack"))
    update: dict[str, Any] = {}
    if pack is not None and contract.read(root) is None:
        from app.stacks.scaffold import scaffold as scaffold_pack
        from app.tools.repository import pin_the_directory_the_product_names, pinned_project_directory

        title = str(getattr(state.get("product_intake"), "product_name", "") or "").strip()
        project = pinned_project_directory(Path(root)) or pin_the_directory_the_product_names(root, title)
        if project:
            from app.stacks import stated_module

            brief = getattr(state.get("document"), "text", "") or ""
            package = stated_module(brief) if pack.language == "python" else None
            result = scaffold_pack(root, pack, project, title or project, package=package)
            update["scaffold_result"] = {
                "ok": result.ok, "pack": pack.name, "project": project, "problem": result.problem,
            }
            if result.ok:
                logger.info("Scaffolded %s into %s/; its smoke tests passed", pack.title, project)
            else:
                logger.warning("Scaffold %s was not kept: %s", pack.name, result.problem)
                update["stack_pack"] = None
            _decide(
                state, update, point="scaffold",
                question="How is the project set up?",
                options=[pack.title, "left to the agents"],
                decision=pack.title if result.ok else "left to the agents",
                rationale=(
                    f"The {pack.title} scaffold installed and passed its own unit and acceptance "
                    "smoke tests." if result.ok else f"The scaffold could not be proven: {result.problem}"
                ),
            )
    return _handing_on(**update, stage="acceptance_author")


# --- acceptance author ---------------------------------------------------------

def acceptance_author(state: Any, config: RunnableConfig, ctx: Context) -> dict[str, Any]:
    """QA writes the acceptance suite from the numbered criteria."""
    from app.agents.specialists import create_specialist_agent
    from app.graph.workflow import _handing_on, _run_gated_agent

    root = _root(state)
    criteria = suite.criteria(root)
    if not criteria:
        brief = getattr(state.get("document"), "text", "") or ""
        criteria = number(brief, state.get("product_intake"))
        if not criteria:
            logger.warning("No acceptance criteria could be read from the brief or the intake")
            return _handing_on(stage="scrum_master")
        suite.save_criteria(root, criteria)
    suite.unlock(root)
    round_ = int(state.get("acceptance_round") or 0)
    feedback = [*(state.get("acceptance_feedback") or []), *(state.get("revision_comments") or [])]
    agent = create_specialist_agent(
        "testing", model=ctx.judgement_model, checkpointer=ctx.checkpointer,
        repo_root=ctx.repo_root, allow_subdirectories=ctx.allow_subdirectories,
    )
    request = acceptance_requests.build_author_request(
        root, criteria, _stack(state), feedback=feedback, change_requests=suite.change_requests(root),
    )
    update = _run_gated_agent(
        state, config,
        stage_name=f"acceptance_author_{round_}",
        agent=agent,
        initial_request=request,
        output_key="__acceptance_author__",
        next_stage="acceptance_review",
    )
    if "__acceptance_author__" not in update:
        return update
    output = update.pop("__acceptance_author__")
    reasons = acceptance_requests.not_automatable(getattr(output, "blockers", None) or [])
    if reasons:
        suite.defer(root, reasons)
        logger.info("QA marked %s as not automatable", ", ".join(sorted(reasons)))
    return {
        **update,
        "acceptance_round": round_ + 1,
        "acceptance_feedback": [],
        "revision_comments": [],
    }


# --- acceptance review ---------------------------------------------------------

def _scenarios(root: str) -> str:
    """`docs/acceptance_tests.md`: the suite in plain language, grouped by criterion."""
    covered = suite.coverage(root)
    deferred = suite.deferred(root)
    lines = [
        "# Acceptance tests",
        "",
        "The tests that decide when this product is done, grouped by the criterion each "
        "proves. Written by QA before the product was built; locked once approved.",
        "",
    ]
    for criterion in suite.criteria(root):
        lines.append(f"## {criterion.id}: {criterion.text}")
        if criterion.id in deferred:
            lines.append(f"- not tested automatically: {deferred[criterion.id]}")
        for name in covered.get(criterion.id, []):
            lines.append(f"- {name}")
        if criterion.id not in deferred and criterion.id not in covered:
            lines.append("- (no test)")
        lines.append("")
    for change_id, text in suite.change_requests(root).items():
        lines.append(f"## {change_id}: {text}")
        lines.extend(f"- {name}" for name in covered.get(change_id, []))
        lines.append("")
    return "\n".join(lines)


def acceptance_review(state: Any, config: RunnableConfig, ctx: Context) -> dict[str, Any]:
    """Check the suite mechanically, have a QA lead judge it, then lock it."""
    from app.agents.acceptance_reviewer import (
        build_acceptance_review_request,
        create_acceptance_reviewer_agent,
    )
    from app.graph.workflow import _handing_on, _record_document, _review_enabled, _run_gated_agent

    root = _root(state)
    rounds = int(state.get("acceptance_round") or 1)
    problems = suite.gaps(root)
    result = suite.run(root)
    if not result.ran:
        problems.append(
            f"The suite does not run: {result.problem}.\n{result.output[-1500:]}".strip()
        )
    if problems and rounds < MAX_ACCEPTANCE_ROUNDS:
        logger.info("Acceptance suite sent back to QA: %d problem(s)", len(problems))
        return _handing_on(stage="acceptance_author", acceptance_feedback=problems)

    findings: list[str] = []
    update: dict[str, Any] = {}
    if not problems:
        already_passing = [test.name for test in result.report.tests if test.outcome == "passed"]
        deferred = suite.deferred(root)
        deferred_text = (
            "--- Criteria QA says no automated test can check ---\n"
            + "\n".join(f"- {cid}: {why}" for cid, why in deferred.items())
            + "\nJudge whether each reason holds; a criterion that can be tested must be.\n\n"
            if deferred else ""
        )
        agent = create_acceptance_reviewer_agent(
            model=ctx.judgement_model, checkpointer=ctx.checkpointer,
            repo_root=ctx.repo_root, allow_subdirectories=ctx.allow_subdirectories,
        )
        request = build_acceptance_review_request(
            acceptance_requests.criteria_text(suite.criteria(root), deferred),
            acceptance_requests.suite_text(root),
            result.summary(),
            already_passing,
            deferred_text,
        )
        update = _run_gated_agent(
            state, config,
            stage_name=f"acceptance_review_{rounds}",
            agent=agent,
            initial_request=request,
            output_key="__acceptance_review__",
            next_stage="acceptance_review",
        )
        if "__acceptance_review__" not in update:
            return update
        review = update.pop("__acceptance_review__")
        update.pop("stage", None)
        if not review.approved and review.findings:
            findings = [str(item) for item in review.findings]
            if rounds < MAX_ACCEPTANCE_ROUNDS:
                logger.info("QA lead sent the acceptance suite back: %d finding(s)", len(findings))
                return _handing_on(**update, stage="acceptance_author", acceptance_feedback=findings)

    suite.lock(root)
    from app.graph.engineering import suite_locked

    suite_locked(root)
    open_problems = [*problems, *findings]
    _record_document(state, "docs/acceptance_tests.md", _scenarios(root))
    tests = len(result.report.tests)
    _decide(
        state, update, point="acceptance_tests",
        question="Is the acceptance suite a fair definition of done?",
        options=["lock it", "send it back to QA"],
        decision="lock it",
        rationale=(
            f"{tests} test(s) over {len(suite.criteria(root))} criteria; "
            + ("every criterion is covered and the QA lead approved."
               if not open_problems else
               f"locked after {rounds} round(s) with these still open: " + "; ".join(open_problems)[:800])
        ),
    )
    logger.info("Acceptance suite locked: %d test(s)", tests)
    # A change request's tests go straight back to the sprint that asked for
    # them, carrying what must now pass. See `app.graph.delivery`.
    return_to = state.get("acceptance_return_to")
    if return_to:
        from app.graph.delivery import change_request_brief

        return _handing_on(
            **update,
            stage=return_to,
            acceptance_return_to=None,
            acceptance_feedback=[],
            acceptance_open_problems=open_problems,
            acceptance_result=result.as_dict(),
            revision_comments=change_request_brief(root),
        )
    next_stage = "user_review_acceptance" if _review_enabled(state, ACCEPTANCE_REVIEW) else "scrum_master"
    return _handing_on(
        **update,
        stage=next_stage,
        acceptance_feedback=[],
        acceptance_open_problems=open_problems,
        acceptance_result=result.as_dict(),
    )


# --- what later stages read --------------------------------------------------------

def criteria_due(state: Any) -> list[str] | None:
    """The criteria the current sprint must leave passing, or None for "all of them".

    A sprint delivers the criteria the plan assigned to it and keeps every
    earlier sprint's passing. A plan that assigned none makes the last sprint
    answer for all of them, and no earlier sprint for any.
    """
    plan = state.get("sprint_plan")
    sprints = list(getattr(plan, "sprints", None) or [])
    index = int(state.get("current_sprint_index") or 0)
    root = _root(state)
    known = [c.id for c in suite.criteria(root)]
    if not known:
        return []
    assigned_any = any(getattr(s, "criteria", None) for s in sprints)
    if not sprints or not assigned_any:
        return known if index >= len(sprints) - 1 else []
    due: list[str] = []
    for sprint in sprints[: index + 1]:
        for item in getattr(sprint, "criteria", None) or []:
            if item in known and item not in due:
                due.append(item)
    if index >= len(sprints) - 1:
        due.extend(item for item in known if item not in due)
    return due + list(suite.change_requests(root))


def criteria_brief(state: Any) -> str:
    """What the technical lead must plan this milestone to make pass, or ""."""
    root = _root(state)
    if not suite.criteria(root) or not suite.is_locked(root):
        return ""
    due = criteria_due(state) or []
    if not due:
        return ""
    texts = {c.id: c.text for c in suite.criteria(root)}
    texts.update(suite.change_requests(root))
    covered = suite.coverage(root)
    saved = suite.last_result(root)
    status = {
        **{k: v.get("status") for k, v in (saved.get("criteria") or {}).items()},
        **{k: v.get("status") for k, v in (saved.get("change_requests") or {}).items()},
    }
    lines = []
    for item in due:
        tests = covered.get(item, [])
        lines.append(
            f"- {item}: {texts.get(item, '')}"
            + (f" - currently {str(status[item]).upper()}" if status.get(item) else "")
            + (f"\n    tests: {'; '.join(tests[:4])}" if tests else "")
        )
    return (
        "\n\n--- Acceptance criteria this milestone must leave passing ---\n"
        + "\n".join(lines)
        + f"\nThe tests are in `{suite.relative_directory(root)}/` and are locked: read them to "
        "see exactly what each checks - the labels, routes, commands or names it uses - and "
        "plan work orders that make them pass. The milestone is not accepted until they do."
    )


def run_for_sprint(state: Any) -> tuple[suite.AcceptanceResult | None, list[str]]:
    """The harness's own run of the suite, and the ids due now. (None, []) when there is no suite."""
    root = _root(state)
    if not suite.criteria(root) or not suite.is_locked(root):
        return None, []
    due = criteria_due(state) or []
    return suite.run(root), due


def _owner_for(state: Any) -> str:
    """Who fixes a failing criterion when the test round did not say."""
    kind = getattr(_stack(state), "product_kind", "") or ""
    return "ui_ux" if kind == "browser_app" else "backend"


def _failing_due(state: Any) -> tuple[list[dict[str, Any]], str]:
    """The due criteria the harness's last run of the suite found failing, and its command."""
    root = _root(state)
    saved = suite.last_result(root)
    if not saved or not suite.is_locked(root):
        return [], ""
    due = criteria_due(state) or []
    entries = {**(saved.get("criteria") or {}), **(saved.get("change_requests") or {})}
    failing = [
        entries[item] for item in due
        if item in entries and entries[item].get("status") in {"failed", "untested"}
    ]
    if not saved.get("ran") and due:
        failing = [entries[item] for item in due if item in entries] or failing
    return failing, str(saved.get("command") or "")


def failing_due_defects(state: Any, reported: list[Any]) -> list[Any]:
    """A defect for each due criterion that fails and that the round did not report.

    The round is handed the suite's result and asked to report every failing
    criterion with its owner; this is the backstop for one it leaves out, so a
    red criterion can never reach the milestone review unreported.
    """
    failing, command = _failing_due(state)
    if not failing:
        return []
    from app.acceptance.junit import tags_in
    from app.agents.specialists import ReportedDefect

    mentioned: set[str] = set()
    for item in reported:
        text = " ".join(
            str(getattr(item, name, "") or "")
            for name in ("description", "reproduction_steps", "expected_behavior", "actual_behavior")
        )
        mentioned.update(tags_in(text))
    defects = []
    for entry in failing:
        if entry.get("id") in mentioned:
            continue
        tests = entry.get("tests") or []
        failed = [t for t in tests if t.get("outcome") == "failed"] or tests
        detail = "; ".join(
            f"{t.get('name')}: " + (((t.get("message") or "").strip().splitlines() or ["failed"])[0][:300])
            for t in failed[:3]
        ) or "no test carrying this id ran"
        defects.append(ReportedDefect(
            description=f"[{entry.get('id')}] {entry.get('text')} - the acceptance suite says this does not work yet.",
            severity="major",
            reproduction_steps=f"Run `{command}` in the project directory and read the {entry.get('id')} tests.",
            expected_behavior=str(entry.get("text") or ""),
            actual_behavior=detail,
            affected_files=[],
            owner=_owner_for(state),
        ))
    return defects


def due_criteria_failing(state: Any) -> str:
    """What the milestone review must not accept: due criteria the suite says fail."""
    failing, command = _failing_due(state)
    if not failing:
        return ""
    lines = [
        f"- {entry.get('id')}: {entry.get('text')}"
        + "".join(
            f"\n    {t.get('name')}: {((t.get('message') or '').strip().splitlines() or ['failed'])[0][:200]}"
            for t in (entry.get("tests") or []) if t.get("outcome") == "failed"
        )
        for entry in failing
    ]
    return (
        f"The acceptance suite (`{command}`) says these criteria, due by the end of this "
        "sprint, do not work yet. The sprint is not done until they pass:\n" + "\n".join(lines)
    )


def acceptance_text_for(state: Any) -> str:
    """Run the suite now and describe it for a test round or a review; "" without a suite."""
    result, due = run_for_sprint(state)
    if result is None:
        return ""
    return acceptance_requests.acceptance_block(result, due)


# --- decision records ------------------------------------------------------------

def _decide(state: Any, update: dict[str, Any], **record: Any) -> None:
    """Add a decision record to `update` (see `app.decisions`); never raises."""
    try:
        from app.decisions import record_decision

        record_decision(state, update, **record)
    except Exception:  # noqa: BLE001 - a record is evidence, not control flow
        logger.debug("Could not record a decision", exc_info=True)
