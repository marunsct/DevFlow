"""Each open question of the intake answered by an assumption, recorded as a decision before the specification (plan IN.1, behind `ASSUMPTIONS_GATE`).

The product manager listed open questions, and nothing answered them: the
architect read them as prose and chose for itself, differently from one run
to the next, and no record said what had been assumed. With the switch on,
the product manager writes the answer it assumes beside each question, each
is recorded as a decision (`docs/decision_log.md`, shown on the run page) -
in auto mode decided by the harness, and the owner sees them at the intake
review when that review is on - and the architect is given them as answers
to build to.

Behind `INTAKE_ASKS_FIRST` (deep review 2026-11-18, item C8): an earlier audit traced all four false acceptances it
found to an intake or a specification that overrode the brief, and "the simplest answer that meets the brief" is an
answer the brief did not give. With it on, the product manager asks at most `MOST_ASKED` questions, each one whose
answer would change what the product does, and answers each with the brief's own words and nothing added. A run a
person answers (its writes are not approved by the run itself) waits for the answers at the intake review, which
opens whether or not the run asked for it; an unattended run builds to the brief's own words. Either way each
assumption is listed in the release's notes for the reader.
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
    "in the form `question -> assumed: answer`. Assume the simplest answer that meets the brief. "
)


def _with_what_the_brief_states(rule: str) -> str:
    from app.agents.brief_over_spec import WHAT_THE_BRIEF_STATES

    return rule + WHAT_THE_BRIEF_STATES


RULE = _with_what_the_brief_states(RULE)
#: The answer to a question the product manager left without one.
SIMPLEST = "The simplest reading that meets the brief; nothing beyond it."
#: How an assumption's decision record begins, so it can be found again.
MARK = "Assumed until the owner says otherwise"
#: "-> assumed:" as asked, and "-> Assumption:" / "-> Assume:" as written: measured on one run, all five assumptions
#: were written "-> Assumption:", none split, and each was recorded with the generic answer.
_ASSUMED = re.compile(r"\s*(?:->|→|=>)\s*assum(?:ed|ption|e)\s*:\s*", re.I)
#: Assumptions recorded at most.
MOST = 12
#: Questions asked at most, with `INTAKE_ASKS_FIRST` on.
MOST_ASKED = 5
#: Asked of the product manager with `INTAKE_ASKS_FIRST` on, in place of `RULE`.
ASKING_RULE = _with_what_the_brief_states(
    "\n\nList at most 5 open questions, and only those whose answer would change what the product does; a question "
    "whose answer changes nothing is not an open question. For each, write the answer the brief's own words give, "
    "adding nothing the brief does not say, in the form `question -> assumed: answer`. Where the brief's words give "
    "no answer, write `question -> assumed: as the brief states it, nothing added`. "
)
#: The answer to a question left without one, with `INTAKE_ASKS_FIRST` on.
LITERAL = "As the brief states it; nothing added."
#: How each assumption is listed among the release's notes for the reader (`app.completion_verdict`).
AT_RELEASE = "Assumed at intake where the brief does not say:"


def enabled() -> bool:
    return is_on("ASSUMPTIONS_GATE", ON_BY_DEFAULT)


def asking() -> bool:
    """`INTAKE_ASKS_FIRST`: few questions, answered by the brief's own words, a person's answers waited for."""
    return is_on("INTAKE_ASKS_FIRST", False)


def active() -> bool:
    """Whether open questions are answered and recorded at all: either switch."""
    return enabled() or asking()


def with_the_rule(request: dict[str, Any]) -> dict[str, Any]:
    """The intake request with `ASKING_RULE` added when asking, else `RULE` when on."""
    rule = ASKING_RULE if asking() else RULE if enabled() else ""
    if rule and request.get("messages") and isinstance(request["messages"][-1].get("content"), str):
        request["messages"][-1]["content"] += rule
    return request


def assumed(questions: list[str] | None) -> list[tuple[str, str]]:
    """(question, assumed answer) for each open question."""
    pairs = []
    most, unanswered = (MOST_ASKED, LITERAL) if asking() else (MOST, SIMPLEST)
    for raw in (questions or [])[:most]:
        text = " ".join(str(raw).split())
        if not text:
            continue
        question, *answer = _ASSUMED.split(text, maxsplit=1)
        pairs.append((question.strip(" -"), (answer[0].strip() if answer else "") or unanswered))
    return pairs


def _latest(state: Any) -> dict[str, str]:
    """{question: its last answer} of the intake's recorded assumptions: the owner's, when the review carried one."""
    latest: dict[str, str] = {}
    for d in state.get("decisions") or []:
        if isinstance(d, dict) and d.get("point") == "product_intake" and d.get("question"):
            if str(d.get("rationale") or "").startswith(MARK) or str(d.get("question")).strip() in latest:
                latest[str(d.get("question")).strip()] = str(d.get("decision") or "")
    return latest


def record(state: Any, update: dict[str, Any]) -> None:
    """Record each assumption as a decision in `update`. Nothing when off."""
    if not active():
        return
    from app.decisions import record_decision

    already = {
        str(d.get("question") or "").strip() for d in (state.get("decisions") or [])
        if isinstance(d, dict) and d.get("point") == "product_intake"
    }
    answered = _latest(state)
    for question, answer in assumed(getattr(update.get("product_intake"), "open_questions", None)):
        # Once: intake sent back by its review asked the same questions again,
        # and each pass recorded every assumption anew. Asking, an answer that
        # changed at the review - a person's - is recorded again, and is the one built to.
        if question.strip() in already and not (asking() and answered.get(question.strip()) != answer):
            continue
        record_decision(
            state, update, point="product_intake", question=question, decision=answer,
            options=[answer, "the owner answers otherwise"],
            rationale=f"{MARK}: the brief does not say, and the specification needs an answer to build to.",
        )


def block(state: Any) -> str:
    """The assumed answers for the architect's request, or "". Never raises."""
    if not active():
        return ""
    try:
        # The last answer per question: the owner's, when the review carried one, else the assumed.
        lines = [f"- {question} -> {answer}" for question, answer in _latest(state).items()]
    except Exception:  # noqa: BLE001
        return ""
    if not lines:
        return ""
    return ("\n\n--- Open questions, answered (recorded as decisions; build to these answers) ---\n"
            + "\n".join(lines) + "\n")


def a_person_answers(run_id: str | None) -> bool:
    """Whether a person answers this run: it is recorded, and its writes are not approved by the run itself."""
    if not run_id:
        return False
    try:
        from app.server.run_store import RunStore

        found = RunStore.shared().load(run_id)
    except Exception:  # noqa: BLE001 - unknown is unattended
        return False
    return found is not None and not bool(getattr(found, "auto_approve", True))


def waits_for_answers(questions: list[str] | None, person_answers: bool) -> bool:
    """Whether the intake review opens for a person to answer the open questions (asking, and a person answers)."""
    return asking() and person_answers and bool(assumed(questions))


def at_release(state: Any) -> list[str]:
    """Each assumption built to, as a note for the release's reader; [] when not asking. Never raises."""
    if not asking():
        return []
    try:
        return [f"{AT_RELEASE} {question} -> {answer}" for question, answer in _latest(state).items()]
    except Exception:  # noqa: BLE001
        return []


__all__ = ["ASKING_RULE", "AT_RELEASE", "LITERAL", "MARK", "MOST_ASKED", "ON_BY_DEFAULT", "RULE", "SIMPLEST",
           "a_person_answers", "active", "asking", "assumed", "at_release", "block", "enabled", "record",
           "waits_for_answers", "with_the_rule"]


class _IntakeAsksFirst:
    """`INTAKE_ASKS_FIRST` as the switch registry reads one: off in code until measured."""

    ON_BY_DEFAULT = False
    #: What the admin page says this switch does.
    explanation = ("The product manager asks at most five open questions, each one whose answer changes what the "
                   "product does, and answers each with the brief's own words, nothing added. A run a person answers "
                   "waits for the answers at the intake review; every assumption is listed in the release notes.")

    @staticmethod
    def enabled() -> bool:
        return asking()


intake_asks_first_switch = _IntakeAsksFirst()
