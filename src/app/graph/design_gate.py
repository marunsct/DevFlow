"""Thorough delivery starts no development while a design finding of a gating severity is open (owner, 2026-11-25).

The owner's instruction: in thorough delivery, every review finding of the categories high, major, critical or blocking
is resolved before development. Measured on one medium run before it: the architecture review raised five blocking and
one major finding, one revision answered them, `ONE_DESIGN_REVIEW` asked nobody again, and the design escalation built
from the latest specification "recording the open points as known risks" with nine points open. The product shipped
with no interface at all, the thing two of the open findings were about.

The design reviews before the first development stage are the architecture review (the reviewer's findings and the
workflow's own checks). In thorough delivery, with no switch:

- every review of a revised specification is a full one: neither `ONE_DESIGN_REVIEW` nor, while a finding the reviewer
  raised is open, `HARNESS_FINDINGS_RECHECKED` stands in for it;
- the reviewer is given what it asked for before, numbered, and answers each gating one (`earlier_findings`);
- the workflow's own checks are asked again on every review, so one they raised is open until they no longer find it;
- a gating finding is open until the re-review says it is resolved or no longer finds it (for a check: the check no
  longer finds it), or a person approves it at the escalation gate. One the reviewer says is still open stays open,
  listed again or not, and goes back to the architect with the rest;
- past the revision limit the run waits at the escalation gate for a person, whoever the run asked to review: it never
  builds by itself with one open, and a gate's timeout does not approve one;
- each gating finding's end is recorded in the decision log: the review round that resolved it, or the person.

Fast delivery and findings below the gating severities are as before.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

#: The state key of the ledger: {"round": the last review round, "findings": [entry, ...]}.
KEY = "design_gate"

#: Where an entry came from: the reviewer, or one of the workflow's own design checks by its name.
REVIEWER = "review"

#: How much of a finding's words a later one must share to be the same finding raised again.
_SAME_FINDING = 0.6

#: What the escalation's decision says when the run waits for a person (an audit reads it).
WAITS = "wait for a person: a design finding of a gating severity is open"


def applies() -> bool:
    """Whether this run gates development on the design findings: thorough delivery."""
    from app.graph.workflow import _fast_delivery

    return not _fast_delivery()


def _ledger(state: Any) -> dict[str, Any]:
    held = state.get(KEY) if hasattr(state, "get") else None
    return held if isinstance(held, dict) else {"round": 0, "findings": []}


def open_findings(state: Any) -> list[dict[str, Any]]:
    """The ledger's gating findings still open, in the order they were raised."""
    return [dict(entry) for entry in _ledger(state).get("findings") or [] if entry.get("status") == "open"]


def holds(state: Any) -> bool:
    """Whether development may not start: thorough delivery, with a gating design finding open."""
    return bool(open_findings(state)) and applies()


def a_finding_the_reviewer_raised_is_open(state: Any) -> bool:
    """Whether an open gating finding is the reviewer's own, which only a review can settle."""
    return applies() and any(entry.get("source") == REVIEWER for entry in open_findings(state))


def _text(finding: Any) -> str:
    from app.graph.workflow import _format_finding

    return _format_finding(finding)


def _words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z][a-z0-9_]{3,}", str(text or "").lower())}


def _the_same(one: str, other: str) -> bool:
    """Whether two findings say the same thing: most of the shorter one's words are the other's."""
    mine, theirs = _words(one), _words(other)
    if not mine or not theirs:
        return False
    return len(mine & theirs) / min(len(mine), len(theirs)) >= _SAME_FINDING


def _dumped(finding: Any) -> dict[str, Any]:
    if hasattr(finding, "model_dump"):
        return finding.model_dump()
    return dict(finding) if isinstance(finding, dict) else {"description": str(finding)}


def _rebuilt(entry: dict[str, Any]) -> Any:
    from app.agents.architecture_reviewer import ArchitectureReviewFinding

    fields = dict(entry.get("finding") or {})
    return ArchitectureReviewFinding(
        severity=str(fields.get("severity") or "major"),
        description=str(fields.get("description") or entry.get("text") or ""),
        evidence=str(fields.get("evidence") or "Raised by an earlier review of the specification."),
        required_remediation=str(fields.get("required_remediation") or "Resolve it in the specification."),
    )


def _answers(review: Any) -> dict[int, tuple[bool, str]]:
    found: dict[int, tuple[bool, str]] = {}
    for answer in getattr(review, "earlier_findings", None) or []:
        number = getattr(answer, "number", None)
        if isinstance(number, int):
            found[number] = (bool(getattr(answer, "resolved", False)), str(getattr(answer, "where", "") or ""))
    return found


def _numbered(previous: Any) -> dict[str, int]:
    """Each finding of the previous review by its text, with the number the re-review was given it under."""
    listed = (previous.get("findings") if isinstance(previous, dict) else getattr(previous, "findings", None)) or []
    numbers: dict[str, int] = {}
    for number, finding in enumerate(listed, start=1):
        try:
            numbers.setdefault(_text(finding), number)
        except Exception:  # noqa: BLE001 - a finding that cannot be read is not numbered
            continue
    return numbers


def after_a_review(
    state: Any, update: dict[str, Any], review: Any, raised_by_checks: dict[str, Any], gating: list[Any]
) -> Any:
    """`review` with every gating finding still open in it; the ledger and the decision log brought up to date.

    `raised_by_checks` is what each of the workflow's own checks found on this review, by name; `gating` the review's
    findings that gate. An earlier gating finding is resolved here when the reviewer says so, or neither says it is
    open nor raises it again; for a check, when the check no longer finds it. One the reviewer says is still open and
    did not list again is put back into the review, so the next revision is told of it. Never raises.
    """
    try:
        return _after_a_review(state, update, review, raised_by_checks, gating)
    except Exception as error:  # noqa: BLE001 - the review stands as written; nothing it found is dropped
        from app.observability.degraded import degraded

        degraded("design_gate.after_a_review", error)
        return review


def _after_a_review(
    state: Any, update: dict[str, Any], review: Any, raised_by_checks: dict[str, Any], gating: list[Any]
) -> Any:
    ledger = _ledger(state)
    this_round = int(ledger.get("round") or 0) + 1
    entries = [dict(entry) for entry in ledger.get("findings") or []]
    by_check = {id(finding): name for name, finding in raised_by_checks.items() if finding is not None}
    current = [(finding, _text(finding), by_check.get(id(finding), REVIEWER)) for finding in gating]
    matched: set[int] = set()
    answers = _answers(review)
    numbers = _numbered(state.get("architecture_review"))
    carried: list[Any] = []
    resolved: list[tuple[dict[str, Any], str]] = []

    def the_current_one(entry: dict[str, Any]) -> int | None:
        for at, (_finding, text, source) in enumerate(current):
            if at in matched or source != entry.get("source"):
                continue
            if source != REVIEWER or text == entry.get("text") or _the_same(text, entry.get("text", "")):
                return at
        return None

    for entry in entries:
        if entry.get("status") != "open":
            continue
        at = the_current_one(entry)
        if entry.get("source") != REVIEWER:
            if at is None:
                resolved.append((entry, f"the workflow's check `{entry.get('source')}` no longer finds it"))
            else:
                matched.add(at)
                entry["text"] = current[at][1]
            continue
        answer = answers.get(numbers.get(str(entry.get("text")), -1))
        if answer is not None and answer[0]:
            resolved.append((entry, "the re-review says it is resolved" + (f": {answer[1]}" if answer[1] else "")))
            # Raised again in other words, the new one is open as a finding of this round (added below).
            continue
        if at is not None:
            matched.add(at)
            entry["text"] = current[at][1]
            entry["finding"] = _dumped(current[at][0])
            continue
        if answer is not None:
            carried.append(_rebuilt(entry))
            continue
        resolved.append((entry, "the re-review no longer finds it"))

    for at, item in enumerate(current):
        if at not in matched:
            entries.append(_an_entry(len(entries) + 1, item, this_round))
    for entry, how in resolved:
        entry.update(status="resolved", settled=f"review round {this_round}", how=how)
        _record(state, update, entry, f"resolved in review round {this_round}", how, decided_by="auto")
    update[KEY] = {"round": this_round, "findings": entries}
    if carried:
        logger.info("Design gate: %d gating finding(s) the re-review says are still open put back into it", len(carried))
        review = review.model_copy(update={"findings": [*review.findings, *carried], "status": "changes_required"})
    return review


def _an_entry(number: int, item: tuple[Any, str, str], this_round: int) -> dict[str, Any]:
    finding, text, source = item
    return {"number": number, "source": source, "text": text, "finding": _dumped(finding),
            "raised": this_round, "status": "open"}


def settled_by_the_checks(state: Any, update: dict[str, Any], how: str) -> None:
    """Every open gating finding is resolved: the workflow's checks that raised them no longer find them."""
    if not applies():
        return
    ledger = _ledger(state)
    this_round = int(ledger.get("round") or 0) + 1
    entries = [dict(entry) for entry in ledger.get("findings") or []]
    for entry in entries:
        if entry.get("status") == "open":
            entry.update(status="resolved", settled=f"review round {this_round}", how=how)
            _record(state, update, entry, f"resolved in review round {this_round}", how, decided_by="auto")
    update[KEY] = {"round": this_round, "findings": entries}


def approved_by_the_person(state: Any, update: dict[str, Any]) -> None:
    """Every open gating finding is approved by the person who answered the escalation gate."""
    ledger = _ledger(state)
    entries = [dict(entry) for entry in ledger.get("findings") or []]
    for entry in entries:
        if entry.get("status") == "open":
            entry.update(status="approved", settled="the person at the escalation gate",
                         how="approved at the escalation gate")
            _record(state, update, entry, "approved by the person at the escalation gate",
                    "The person approved building with it open, with the open findings in front of them.",
                    decided_by="user")
    if entries:
        update[KEY] = {**ledger, "findings": entries}


def _record(state: Any, update: dict[str, Any], entry: dict[str, Any], decision: str, how: str, *,
            decided_by: str) -> None:
    from app.decisions import record_decision

    raised = entry.get("raised")
    source = "the reviewer" if entry.get("source") == REVIEWER else f"the workflow's check `{entry.get('source')}`"
    record_decision(
        state, update, point="technical_specification",
        question=f"Is design finding G{entry.get('number')} (gating, raised by {source} in review round {raised}) "
                 "resolved before development?",
        options=["resolved by a revision", "approved by a person", "still open"],
        decision=decision,
        rationale=f"{how}. The finding: {entry.get('text')}"[:1500],
        decided_by=decided_by,
    )


def the_open_findings_text(state: Any) -> list[str]:
    """Each open gating finding as the escalation page lists it."""
    return [f"G{entry.get('number')} (round {entry.get('raised')}): {entry.get('text')}" for entry in open_findings(state)]


def why_it_waits(state: Any, revisions: int) -> str:
    """The reason recorded when the run waits for a person rather than building with gating findings open."""
    count = len(open_findings(state))
    return (
        f"Thorough delivery starts no development while a design finding of a gating severity (blocking, major, "
        f"critical or high) is open, and {count} still are after {revisions} revision(s). The run decides nothing "
        "about them by itself, whether or not it asked for a reviewer at this gate: an unattended run's own "
        "approvals cover the files it writes, never these. It waits for a person: Approve builds with them recorded "
        "as approved by that person; Request changes revises the specification again with the guidance. "
        "Open: " + "; ".join(the_open_findings_text(state))
    )[:1500]


def held_for_a_person(state: Any, delivery_mode: str | None = None) -> bool:
    """Whether a run's paused escalation gate holds gating design findings, which a gate's timeout does not approve.

    Read by the approval-timeout sweep, outside the run, so the run's own delivery mode is passed. Never raises.
    """
    try:
        from app import delivery
        from app.graph.escalation import DESIGN

        if str((state.get("escalation") or {}).get("kind") or "") != DESIGN:
            return False
        with delivery.for_the_run(delivery_mode):
            return holds(state)
    except Exception:  # noqa: BLE001 - unknown is held: a person can always answer
        return True


__all__ = [
    "KEY", "REVIEWER", "WAITS", "a_finding_the_reviewer_raised_is_open", "after_a_review", "applies",
    "approved_by_the_person", "held_for_a_person", "holds", "open_findings", "settled_by_the_checks",
    "the_open_findings_text", "why_it_waits",
]
