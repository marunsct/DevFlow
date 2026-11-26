"""What the design review approved the specification on, kept when the harness approves and handed to the stages after it.

Measured on one medium run in thorough delivery: the architecture reviewer approved with three approval conditions
(for one, that the error catalogue section stays and holds every error code the specification uses), four accepted
risks and three earlier findings, each resolved with where. The workflow's own design checks overturned the approval,
the architect revised, and the harness then approved on the reviewer's behalf with an empty review: state and
`docs/architecture_review.md` said "No findings", "None answered" and no conditions or risks (LF.1511).

And nothing read the conditions or the risks even when they survived: they reached only the document, so the stages
that plan and build never saw what the specification was approved on (LF.1512). Both are quality fixes, always on.

- `approval_keeping_what_the_reviewer_said` is the approval the harness gives, built from the last review in state.
- `with_the_conditions` appends the conditions to the sprint planning, milestone planning and work-order requests, and
  the accepted risks to the two planning requests only, as known risks.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

CONDITIONS_HEADING = "--- Conditions the design review approved the specification on ---"
RISKS_HEADING = "--- Known risks the design review accepted ---"
#: Each block goes into every planning and build request: the lines whole, up to this many characters.
MOST_CHARS = 1_500


def _field(review: Any, name: str) -> list[Any]:
    value = review.get(name) if isinstance(review, dict) else getattr(review, name, None)
    return list(value or [])


def _lines(review: Any, name: str) -> list[str]:
    return [" ".join(str(line).split()) for line in _field(review, name) if str(line or "").strip()]


def approval_keeping_what_the_reviewer_said(previous: Any) -> Any:
    """An approval with no findings that keeps the last review's approval conditions, accepted risks and answers to
    the earlier findings. `previous` is the review in state (a model, a dict, or None). Never raises."""
    from app.agents.architecture_reviewer import ArchitectureReviewOutput

    try:
        return ArchitectureReviewOutput(
            status="approved", findings=[],
            approval_conditions=_lines(previous, "approval_conditions"),
            accepted_risks=_lines(previous, "accepted_risks"),
            earlier_findings=_field(previous, "earlier_findings"),
        )
    except Exception:  # noqa: BLE001 - the approval stands without what could not be read
        logger.debug("Could not carry the review's conditions into the approval", exc_info=True)
        return ArchitectureReviewOutput(status="approved", findings=[])


def what_is_carried(approval: Any) -> str:
    """The rationale's sentence for what the approval kept of the reviewer's; "" when it kept nothing."""
    conditions, risks = len(_lines(approval, "approval_conditions")), len(_lines(approval, "accepted_risks"))
    if not (conditions or risks):
        return ""
    return (f" The reviewer's {conditions} approval condition(s) and {risks} accepted risk(s) are carried with the "
            "approval, and the stages that plan and build are given them.")


def _approved(state: Any) -> Any:
    review = state.get("architecture_review") if isinstance(state, dict) else None
    status = review.get("status") if isinstance(review, dict) else getattr(review, "status", None)
    return review if status == "approved" else None


def _block(heading: str, lines: list[str], closing: str) -> str:
    if not lines:
        return ""
    shown: list[str] = []
    used = 0
    for line in lines:
        entry = f"- {line}"
        if used + len(entry) > MOST_CHARS:
            if not shown:
                shown.append(entry[: MOST_CHARS - 1] + "…")
            break
        shown.append(entry)
        used += len(entry) + 1
    more = len(lines) - len(shown)
    if more:
        shown.append(f"- And {more} more in docs/architecture_review.md.")
    return f"\n\n{heading}\n" + "\n".join(shown) + f"\n{closing}\n"


def conditions_section(state: Any) -> str:
    """The approved review's conditions, quoted; "" when the review is not approved or set none."""
    return _block(
        CONDITIONS_HEADING, _lines(_approved(state), "approval_conditions"),
        "These bind as the specification does: what is planned and built keeps every one of them true.",
    )


def risks_section(state: Any) -> str:
    """The approved review's accepted risks, quoted; "" when the review is not approved or accepted none."""
    return _block(
        RISKS_HEADING, _lines(_approved(state), "accepted_risks"),
        "They were accepted, not resolved: plan with them in mind, and do not reopen the design over them.",
    )


def with_the_conditions(request: dict[str, Any], state: Any, *, risks: bool = False) -> dict[str, Any]:
    """`request` with the conditions (and, with `risks`, the accepted risks) appended to its last message. Never raises."""
    try:
        section = conditions_section(state) + (risks_section(state) if risks else "")
        if section and request.get("messages"):
            last = request["messages"][-1]
            if isinstance(last, dict) and isinstance(last.get("content"), str):
                last["content"] += section
    except Exception:  # noqa: BLE001 - a request without them is the request as it was
        logger.debug("Could not add the design review's conditions to a request", exc_info=True)
    return request


__all__ = [
    "CONDITIONS_HEADING", "MOST_CHARS", "RISKS_HEADING", "approval_keeping_what_the_reviewer_said",
    "conditions_section", "risks_section", "what_is_carried", "with_the_conditions",
]
