"""Each open question of the intake answered by an assumption, recorded as a decision before the specification (plan IN.1, behind `ASSUMPTIONS_GATE`).

The product manager listed open questions, and nothing answered them: the
architect read them as prose and chose for itself, differently from one run
to the next, and no record said what had been assumed. With the switch on,
the product manager writes the answer it assumes beside each question, each
is recorded as a decision (`docs/decision_log.md`, shown on the run page) -
in auto mode decided by the harness, and the owner sees them at the intake
review when that review is on - and the architect is given them as answers
to build to.
"""

from __future__ import annotations

import re
from typing import Any

from app.switches import is_on

#: `ASSUMPTIONS_GATE` set to on or off overrides this.
ON_BY_DEFAULT = False
#: Asked of the product manager when on.
RULE = (
    "\n\nFor each open question, write the answer this product assumes until the owner says otherwise, "
    "in the form `question -> assumed: answer`. Assume the simplest answer that meets the brief."
)
#: The answer to a question the product manager left without one.
SIMPLEST = "The simplest reading that meets the brief; nothing beyond it."
#: How an assumption's decision record begins, so it can be found again.
MARK = "Assumed until the owner says otherwise"
_ASSUMED = re.compile(r"\s*(?:->|→|=>)\s*assumed\s*:\s*", re.I)
#: Assumptions recorded at most.
MOST = 12


def enabled() -> bool:
    return is_on("ASSUMPTIONS_GATE", ON_BY_DEFAULT)


def with_the_rule(request: dict[str, Any]) -> dict[str, Any]:
    """The intake request with `RULE` added when on."""
    if enabled() and request.get("messages") and isinstance(request["messages"][-1].get("content"), str):
        request["messages"][-1]["content"] += RULE
    return request


def assumed(questions: list[str] | None) -> list[tuple[str, str]]:
    """(question, assumed answer) for each open question."""
    pairs = []
    for raw in (questions or [])[:MOST]:
        text = " ".join(str(raw).split())
        if not text:
            continue
        question, *answer = _ASSUMED.split(text, maxsplit=1)
        pairs.append((question.strip(" -"), (answer[0].strip() if answer else "") or SIMPLEST))
    return pairs


def record(state: Any, update: dict[str, Any]) -> None:
    """Record each assumption as a decision in `update`. Nothing when off."""
    if not enabled():
        return
    from app.decisions import record_decision

    for question, answer in assumed(getattr(update.get("product_intake"), "open_questions", None)):
        record_decision(
            state, update, point="product_intake", question=question, decision=answer,
            options=[answer, "the owner answers otherwise"],
            rationale=f"{MARK}: the brief does not say, and the specification needs an answer to build to.",
        )


def block(state: Any) -> str:
    """The assumed answers for the architect's request, or "". Never raises."""
    if not enabled():
        return ""
    try:
        lines = [
            f"- {d.get('question')} -> {d.get('decision')}"
            for d in state.get("decisions") or []
            if isinstance(d, dict) and d.get("point") == "product_intake" and str(d.get("rationale") or "").startswith(MARK)
        ]
    except Exception:  # noqa: BLE001
        return ""
    if not lines:
        return ""
    return ("\n\n--- Open questions, answered (recorded as decisions; build to these answers) ---\n"
            + "\n".join(lines) + "\n")


__all__ = ["MARK", "ON_BY_DEFAULT", "RULE", "SIMPLEST", "assumed", "block", "enabled", "record", "with_the_rule"]
