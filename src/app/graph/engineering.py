"""CI and code review between a batch of work orders and its test rounds, and the
guard that keeps a defect fix from making the product worse.

    specialists -> ci_gate -> code_review -> test_and_triage -> fixes ...

The work orders of a milestone are committed as one batch. CI runs the unit and
acceptance suites and compares them with the state the last sprint was accepted
in: anything that passed then and fails now is a regression, recorded as a
defect. A senior engineer then reads the batch's diff against its work orders;
what blocks becomes a defect with an owner. Both reach the sprint's ordinary
fix loop through the first test round, so nothing new is needed to fix them.

A fix is different: it is one change, made to repair one thing, and a fix that
breaks something else while it is at it is reverted to exactly where it
started. Its defect stays open, with what the attempt broke, so the next try
knows.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from app import ci
from app.acceptance import suite
from app.stacks import contract

logger = logging.getLogger(__name__)

#: How many regressions a CI run turns into defects; one broken build fails
#: every test, and fifty defects for one cause help nobody.
MOST_REGRESSION_DEFECTS = 6


def _root(state: Any) -> str:
    return state["repository"].root_path


def ci_applies(root: str) -> bool:
    """Whether there is anything to measure: a scaffolded project or a locked suite."""
    return contract.read(root) is not None or suite.is_locked(root)


def _tasks(state: Any) -> list[Any]:
    return list(getattr(state.get("milestone_plan"), "delegated_tasks", None) or [])


def _title(task: Any) -> str:
    return str(getattr(task, "title", "") or getattr(task, "task_description", "") or "")[:80]


def _owner_of(state: Any, work_order: str) -> str:
    tasks = _tasks(state)
    for task in tasks:
        if work_order and work_order.strip().lower() in _title(task).lower():
            return str(task.specialist_role)
    for task in tasks:
        if str(task.specialist_role) != "testing":
            return str(task.specialist_role)
    return "backend"


def regression_defects(state: Any, lost: list[str]) -> list[Any]:
    from app.agents.specialists import ReportedDefect

    owner = _owner_of(state, "")
    defects = [
        ReportedDefect(
            description=f"Regression: `{name}` passed when the last sprint was accepted and fails now.",
            severity="major",
            reproduction_steps=f"Run the {name.split(':', 1)[0]} tests in the project directory.",
            expected_behavior="It passes, as it did before this sprint's work orders.",
            actual_behavior="It fails after them.",
            affected_files=[],
            owner=owner,
        )
        for name in lost[:MOST_REGRESSION_DEFECTS]
    ]
    if len(lost) > MOST_REGRESSION_DEFECTS:
        defects[-1].actual_behavior += f" ({len(lost) - MOST_REGRESSION_DEFECTS} more tests regressed with it.)"
    return defects


def ci_gate(state: Any, config: RunnableConfig, ctx: Any) -> dict[str, Any]:
    """Commit the batch, run CI, and record what it broke."""
    from app.graph.workflow import APP_RUN_ID_KEY, _handing_on, _stop_if_cancelled

    _stop_if_cancelled(config["configurable"].get(APP_RUN_ID_KEY))
    root = _root(state)
    if not ci_applies(root):
        return _handing_on(stage="test_and_triage")
    titles = "; ".join(_title(task) for task in _tasks(state)) or "work orders"
    batch = ci.commit(root, f"Work orders: {titles}")
    accepted = ci.load(root, "accepted")
    after = ci.take(root, "after the work orders")
    lost = ci.regressions(accepted, after)
    ci.save(root, after)
    if lost:
        logger.warning("CI: %d test(s) regressed since the last accepted sprint", len(lost))
    report = (
        f"Unit tests: {sum(o == 'passed' for o in after.unit.values())} of {len(after.unit)} pass"
        + ("" if after.unit_ran else " (no unit report)")
        + f"; acceptance tests: {sum(o == 'passed' for o in after.acceptance.values())} of "
        f"{len(after.acceptance)} pass."
        + (("\nRegressed since the last accepted sprint:\n" + "\n".join(f"- {n}" for n in lost)) if lost else "")
    )
    return _handing_on(
        stage="code_review",
        ci_report=report,
        ci_batch_commit=batch,
        review_defects=regression_defects(state, lost),
    )


def _later_sprints(state: Any) -> str:
    """Each later sprint's goal and criteria, for a reviewer of this one."""
    sprints = list(getattr(state.get("sprint_plan"), "sprints", None) or [])
    index = int(state.get("current_sprint_index") or 0)
    texts = {c.id: c.text for c in suite.criteria(_root(state))}
    lines = []
    for number, sprint in enumerate(sprints[index + 1:], index + 2):
        ids = list(getattr(sprint, "criteria", None) or [])
        lines.append(
            f"- Sprint {number}: {getattr(sprint, 'goal', '')}"
            + "".join(f"\n    {cid}: {texts.get(cid, '')}" for cid in ids)
        )
    return "\n".join(lines)


def code_review(state: Any, config: RunnableConfig, ctx: Any) -> dict[str, Any]:
    """A senior engineer reads the batch's diff; what blocks becomes a defect."""
    from app.acceptance.requests import criteria_text
    from app.agents.code_reviewer import build_code_review_request, create_code_reviewer_agent
    from app.agents.specialists import ReportedDefect
    from app.graph.acceptance_nodes import criteria_due
    from app.graph.workflow import _handing_on, _run_gated_agent

    root = _root(state)
    accepted = ci.load(root, "accepted")
    diff = ci.diff_since(root, accepted.commit if accepted else "")
    if not diff.strip():
        return _handing_on(stage="test_and_triage")
    due = set(criteria_due(state) or [])
    criteria = criteria_text([c for c in suite.criteria(root) if not due or c.id in due])
    orders = "\n".join(
        f"- {_title(task)} ({task.specialist_role}): {getattr(task, 'task_description', '')[:400]}"
        for task in _tasks(state)
    )
    later = _later_sprints(state)
    agent = create_code_reviewer_agent(
        model=ctx.judgement_model, checkpointer=ctx.checkpointer,
        repo_root=ctx.repo_root, allow_subdirectories=ctx.allow_subdirectories,
    )
    attempt = int(state.get("sprint_replan_count") or 0), int(state.get("milestone_revision_count") or 0)
    update = _run_gated_agent(
        state, config,
        stage_name=f"code_review_{attempt[0]}_{attempt[1]}",
        agent=agent,
        initial_request=build_code_review_request(diff, orders, criteria, str(state.get("ci_report") or ""), later),
        output_key="__code_review__",
        next_stage="code_review",
    )
    if "__code_review__" not in update:
        return update
    review = update.pop("__code_review__")
    update.pop("stage", None)
    from app.graph.acceptance_nodes import criteria_only_later

    later = [
        finding for finding in getattr(review, "findings", None) or []
        if criteria_only_later(state, f"{finding.problem} {finding.fix or ''}")
    ]
    if later:
        logger.info("Code review raised %d finding(s) about criteria later sprints deliver; not defects now", len(later))
    found = [
        ReportedDefect(
            description=f"Code review ({finding.work_order}): {finding.problem}",
            severity="blocking" if finding.severity == "blocking" else "major",
            reproduction_steps=f"Read {finding.file or 'the files the work order names'}.",
            expected_behavior=finding.fix or "What the work order asked for.",
            actual_behavior=finding.problem,
            affected_files=[finding.file] if finding.file else [],
            owner=_owner_of(state, finding.work_order),
        )
        for finding in getattr(review, "findings", None) or []
        if finding.severity in {"blocking", "major"} and finding not in later
    ]
    if found:
        logger.info("Code review found %d problem(s) to fix", len(found))
    return _handing_on(
        **update,
        stage="test_and_triage",
        review_defects=[*(state.get("review_defects") or []), *found],
    )


# --- the guard around a fix -----------------------------------------------------------

def before_a_fix(root: str, stage_name: str) -> str:
    """Commit the workspace as the fix will find it; the commit to revert to."""
    if not ci_applies(root):
        return ""
    base = ci.commit(root, f"Before {stage_name}")
    latest = ci.load(root, "latest")
    if latest is None or latest.commit != base:
        # Something changed since the last measurement (a test round edited
        # tests, say), so measure what the fix starts from.
        ci.save(root, ci.take(root, f"before {stage_name}"))
    return base


def after_a_fix(root: str, base: str, stage_name: str, description: str) -> list[str]:
    """Measure the fix. A fix that broke what passed before it is reverted; returns what it broke."""
    if not base or not ci_applies(root):
        return []
    before = ci.load(root, "latest")
    after = ci.take(root, f"after {stage_name}")
    lost = ci.regressions(before, after)
    if lost and ci.revert_to(root, base):
        logger.warning("Reverted %s: it broke %d test(s) that passed before it", stage_name, len(lost))
        return lost
    ci.save(root, after)
    ci.commit(root, f"Fix: {description[:60]}")
    return []


def accepted_state(root: str) -> None:
    """Measure the workspace as the sprint is accepted: the next sprint's baseline."""
    if not ci_applies(root):
        return
    try:
        ci.save(root, ci.take(root, "accepted"), accepted=True)
    except Exception:  # noqa: BLE001 - a missing baseline only means fewer regressions found
        logger.warning("Could not measure the accepted state", exc_info=True)


def suite_locked(root: str) -> None:
    """The first baseline: the scaffold and the locked suite, before any feature."""
    if not ci_applies(root):
        return
    try:
        commit_id = ci.commit(root, "Acceptance suite locked")
        ci.save(root, ci.Snapshot(label="suite locked", commit=commit_id), accepted=True)
    except Exception:  # noqa: BLE001
        logger.debug("Could not record the first baseline", exc_info=True)
