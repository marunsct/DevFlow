"""What happens when a sprint cannot be finished: the last rung of the ladder.

    fix -> fix again -> re-plan the sprint -> re-plan it on the judgement model
        -> escalation: a decision, recorded

Every earlier rung tries again. This one decides. In approval mode the person
reviewing the run is asked, with the problem and the options in front of them;
in auto mode the harness decides the way a software company would - it ships
what works and records, with reasons, what it could not make work - as long as
what works is most of the product. A run that cannot make most of its criteria
pass is stopped rather than shipped.

Before this, every one of these points ended the run, whatever was left
undone and however much already worked.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.acceptance import suite

logger = logging.getLogger(__name__)

#: Review point: a sprint that cannot be finished.
ESCALATION_REVIEW = "escalation"

#: How many escalations a run may have before it stops: one decision per
#: stuck sprint is the expectation, and a run that keeps getting stuck is not
#: converging on anything.
MAX_ESCALATIONS = 3


def _root(state: Any) -> str:
    return state["repository"].root_path


def asks_a_person(state: Any) -> bool:
    """Only when this review point was asked for. A sprint review alone is not
    one: that gate's question is "accept this sprint?", and a stuck sprint must
    not be accepted in one click without the problem in front of the reviewer."""
    from app.graph.workflow import _review_enabled

    return _review_enabled(state, ESCALATION_REVIEW)


def _where_next(state: Any) -> str:
    sprints = list(getattr(state.get("sprint_plan"), "sprints", None) or [])
    index = int(state.get("current_sprint_index") or 0)
    return "sprint_advance" if index < len(sprints) - 1 else "release"


def _failing(state: Any) -> list[dict[str, Any]]:
    from app.graph.acceptance_nodes import _failing_due

    failing, _ = _failing_due(state)
    return failing


def _page(state: Any, error: str, failing: list[dict[str, Any]]) -> str:
    lines = [
        "# The sprint could not be finished",
        "",
        "The team tried to fix it, then re-planned the sprint, and it still does not pass.",
        "",
        "## What is wrong",
        "",
        error.strip() or "(no detail recorded)",
        "",
    ]
    if failing:
        lines += ["## Acceptance criteria still failing", ""]
        lines += [f"- {e.get('id')}: {e.get('text')}" for e in failing]
        lines.append("")
    lines += [
        "## Your options",
        "",
        "- **Approve**: defer what still fails - recorded with this reason - and carry on with "
        "the rest of the product.",
        "- **Request changes**: say what to do differently; the sprint is planned again with "
        "your guidance.",
        "",
    ]
    return "\n".join(lines)


def escalation(state: Any, config: RunnableConfig, ctx: Any) -> dict[str, Any]:
    """Decide how a stuck sprint goes on, or ask the person who decides."""
    from app.decisions import record_decision
    from app.graph.workflow import _handing_on, _record_document

    error = str((state.get("escalation") or {}).get("error") or "")
    count = int(state.get("escalation_count") or 0) + 1
    root = _root(state)
    failing = _failing(state)
    update: dict[str, Any] = {"escalation_count": count}

    if count > MAX_ESCALATIONS:
        record_decision(
            state, update, point="escalation",
            question="The run is stuck again: how does it go on?",
            options=["stop the run"], decision="stop the run",
            rationale=f"{count - 1} escalations already; the run is not converging.",
        )
        return _handing_on(**update, stage="failed", error=error)

    if asks_a_person(state):
        _record_document(state, "docs/reviews/escalation.md", _page(state, error, failing))
        return _handing_on(**update, stage="user_review_escalation")

    criteria = suite.criteria(root)
    if not criteria:
        record_decision(
            state, update, point="escalation",
            question="The sprint could not be finished: how does the run go on?",
            options=["stop the run"], decision="stop the run",
            rationale="There is no acceptance suite to say what works, so nothing can be shipped with confidence.",
        )
        return _handing_on(**update, stage="failed", error=error)

    deferred = suite.deferred(root)
    after = len(deferred) + len([e for e in failing if e.get("id") not in deferred])
    if after * 2 > len(criteria):
        record_decision(
            state, update, point="escalation",
            question="The sprint could not be finished: how does the run go on?",
            options=["defer the failing criteria and continue", "stop the run"],
            decision="stop the run",
            rationale=(
                f"Deferring {', '.join(str(e.get('id')) for e in failing)} would leave {after} of "
                f"{len(criteria)} criteria undelivered - more than half the product."
            ),
        )
        return _handing_on(**update, stage="failed", error=error)

    return _defer_and_continue(state, update, failing, error, decided_by="auto")


def _defer_and_continue(
    state: Any, update: dict[str, Any], failing: list[dict[str, Any]], error: str, *, decided_by: str
) -> dict[str, Any]:
    from app.decisions import record_decision
    from app.graph.workflow import _handing_on

    root = _root(state)
    reason = (error.strip().splitlines() or ["could not be made to pass"])[0][:200]
    to_defer = {
        str(e.get("id")): f"could not be made to pass after fixes and re-planning ({reason})"
        for e in failing if str(e.get("id", "")).startswith("AC-")
    }
    if to_defer:
        suite.defer(root, to_defer)
    record_decision(
        state, update, point="escalation",
        question="The sprint could not be finished: how does the run go on?",
        options=["defer what fails and continue", "stop the run"],
        decision=(
            f"defer {', '.join(sorted(to_defer))} and continue" if to_defer
            else "accept the sprint with its open problems recorded as known issues"
        ),
        rationale=error[:1500],
        decided_by=decided_by,
        affects=sorted(to_defer),
    )
    known = [*(state.get("known_issues") or []), *([error[:600]] if error and not to_defer else [])]
    return _handing_on(
        **update,
        stage=_where_next(state),
        escalation=None,
        known_issues=known,
    )


def accept(state: Any, config: RunnableConfig, ctx: Any) -> dict[str, Any]:
    """The person approved going on: defer what fails and continue."""
    error = str((state.get("escalation") or {}).get("error") or "")
    return _defer_and_continue(state, {}, _failing(state), error, decided_by="user")


def retry(state: Any, config: RunnableConfig, ctx: Any) -> dict[str, Any]:
    """The person asked for another way: plan the sprint again with their guidance."""
    from app.graph.workflow import _handing_on

    return _handing_on(
        stage="technical_lead",
        escalation=None,
        # The milestone plan stays, so the lead revises it with the guidance
        # rather than planning from nothing without it.
        revision_comments=[c for c in state.get("revision_comments") or [] if str(c).strip()],
        specialist_outputs={},
        remediation=None,
        test_round=0,
        defect_cursor=0,
        milestone_revision_count=0,
        sprint_replan_count=0,
    )
