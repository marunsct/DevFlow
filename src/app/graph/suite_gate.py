"""Thorough delivery locks no acceptance suite while a finding of a gating severity about it is open (TG.2).

The owner's rule (2026-11-25): in thorough delivery every review finding of severity blocking, major, critical or high
is resolved before development starts. The architecture review has kept it since `app.graph.design_gate`; the suite,
which decides when the product is done, did not: past `MAX_ACCEPTANCE_ROUNDS` it was locked "with these still open",
whatever they were - a test no product can pass among them.

At the lock, in thorough delivery, for a suite written before its development (not one reopened for a repair):

- the QA lead's findings carry the severity it gave them (`AcceptanceReviewFinding.severity`; a finding written
  without one is `minor`, so it locks as every finding did before);
- the harness's own findings take the severity of what they break (`severity_of_a_check`);
- a gating finding (blocking or major) keeps the suite from locking. The run waits for a person at the escalation
  gate, whoever the run asked to review: Approve locks the suite as it stands with each finding recorded as that
  person's; Request changes sends the suite back to its writers with the findings and the guidance. A gate's timeout
  does not approve one, and an unattended run's own approvals cover the files it writes, never these;
- a gating finding the next review no longer raises is resolved in that round, recorded in the decision log.

Fast delivery, a suite reopened for a repair, and findings below the gating severities lock as before.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

logger = logging.getLogger(__name__)

#: The state key of the ledger: {"round": the last acceptance round it was read at, "approved_at": the round a person
#: approved it at, "findings": [entry, ...]}.
KEY = "suite_gate"

#: Where an entry came from: the QA lead, or one of the harness's checks by its name.
QA_LEAD = "qa_lead"

#: Where a criterion nothing tests is recorded from.
NO_TEST = "criteria_with_no_test"

#: What the escalation's decision says when the run waits for a person (an audit reads it).
WAITS = "wait for a person: a finding of a gating severity about the acceptance suite is open"

#: The harness's checks whose finding is a test no product can pass: the definition of done can never be met.
#: Every check inside `suite.tests_that_cannot_pass` is one too, and comes in as `cannot`.
_NEVER_PASSES = frozenset({
    "tests_that_cannot_pass",
    # The contract answers 204 with no body; a test that reads one fails on every product that keeps the contract.
    "tests_that_want_json_from_a_204",
    # A success status the contract does not give: every product that keeps the contract fails it.
    "tests_whose_success_status_the_contract_does_not_give",
})

#: The harness's checks whose finding is a test that passes a product not meeting its criterion: done is not defined.
_PASSES_WITHOUT_THE_PRODUCT = frozenset({
    # An assertion made only when the answer was good: a product that answers badly passes the test.
    "tests_guarded_by_the_answer",
    NO_TEST,
})

#: How much of a finding's words a later one must share to be the same finding raised again.
_SAME_FINDING = 0.6


def severity_of_a_check(check: str) -> str:
    """The severity of a finding by the harness's check that raised it: what the finding breaks.

    blocking: the test can never pass, so the suite defines a done no product reaches. major: the test passes a
    product that does not meet its criterion, or a criterion has no test, so the suite defines no done for it.
    minor: everything else the harness reads in the tests' code - how a control is found, how closely an output is
    held, a line of the contract no test calls, a test that passes before anything is built (the scaffold may already
    do what it checks; the QA lead is shown those and weighs each). The test still fails when its criterion is not
    met, so the suite is a fair definition of done, if a looser one. Files the harness put back itself are a report
    of what it did, not a fault left open.
    """
    if check in _NEVER_PASSES:
        return "blocking"
    if check in _PASSES_WITHOUT_THE_PRODUCT:
        return "major"
    return "minor"


def _gates(severity: Any) -> bool:
    from app.graph.workflow import _severity_gates

    return _severity_gates(severity)


def applies(state: Any) -> bool:
    """Whether this lock is gated: thorough delivery, a suite written before its development (not one reopened)."""
    from app.graph.workflow import _fast_delivery

    return not _fast_delivery() and not (state.get("acceptance_return_to") if hasattr(state, "get") else None)


def _ledger(state: Any) -> dict[str, Any]:
    held = state.get(KEY) if hasattr(state, "get") else None
    return held if isinstance(held, dict) else {"round": 0, "findings": []}


def open_findings(state: Any) -> list[dict[str, Any]]:
    """The ledger's gating findings still open, in the order they were raised."""
    return [dict(entry) for entry in _ledger(state).get("findings") or [] if entry.get("status") == "open"]


def holds(state: Any) -> bool:
    """Whether the suite may not lock: a gating finding about it open, in a lock this gate applies to."""
    return bool(open_findings(state)) and applies(state)


def approved_as_it_stands(state: Any) -> bool:
    """Whether a person approved locking the suite as it stands at this round: it is locked, not reviewed again."""
    ledger = _ledger(state)
    return applies(state) and ledger.get("approved_at") == int(state.get("acceptance_round") or 1)


def the_qa_lead_reads_again(state: Any) -> bool:
    """Whether a gating finding the QA lead raised is open, which only its own reading of the suite can settle."""
    return applies(state) and any(entry.get("source") == QA_LEAD for entry in open_findings(state))


def approved_qa_lead_findings(state: Any) -> list[str]:
    """The QA lead's findings a person approved locking with, for the lock's record of what is still open."""
    return [str(entry.get("text")) for entry in _ledger(state).get("findings") or []
            if entry.get("status") == "approved" and entry.get("source") == QA_LEAD]


def _words(text: str) -> set[str]:
    import re

    return set(re.findall(r"[a-z][a-z0-9_]{3,}", str(text or "").lower()))


def _the_same(one: str, other: str) -> bool:
    if one == other:
        return True
    mine, theirs = _words(one), _words(other)
    if not mine or not theirs:
        return False
    return len(mine & theirs) / min(len(mine), len(theirs)) >= _SAME_FINDING


def gating_findings(
    root: Any,
    problems: Iterable[Any],
    findings: Iterable[Any],
    graded: dict[str, str],
    cannot: Iterable[Any],
    raised: Iterable[tuple[str, str]],
) -> list[tuple[str, str, str]]:
    """(text, source, severity) of each finding at this lock whose severity gates.

    `problems` are the harness's, `cannot` those of them that say no product can pass a test, `raised` each of the
    harness's findings with the check that raised it; `findings` the QA lead's, with `graded` its severity of each.
    """
    from app.acceptance import suite

    by_check = {text: check for check, text in raised}
    never = {str(item) for item in cannot}
    excused = set(suite.deferred(root))
    try:
        from app.acceptance import sprint_scope

        excused |= set(sprint_scope.not_yet_due(root))
    except Exception:  # noqa: BLE001 - every criterion is due, as at the release
        pass
    covered = suite.coverage(root)
    untested = tuple(f"{c.id} (" for c in suite.criteria(root) if c.id not in covered and c.id not in excused)
    found: list[tuple[str, str, str]] = []
    for problem in dict.fromkeys(str(item) for item in problems):
        check = ("tests_that_cannot_pass" if problem in never
                 else NO_TEST if untested and problem.startswith(untested)
                 else by_check.get(problem, ""))
        severity = severity_of_a_check(check)
        if _gates(severity):
            found.append((problem, check, severity))
    for finding in dict.fromkeys(str(item) for item in findings):
        severity = str(graded.get(finding) or "minor")
        if _gates(severity):
            found.append((finding, QA_LEAD, severity))
    return found


def before_the_lock(
    state: Any,
    update: dict[str, Any],
    *,
    root: Any,
    problems: Iterable[Any],
    findings: Iterable[Any],
    graded: dict[str, str] | None,
    cannot: Iterable[Any],
    raised: Iterable[tuple[str, str]],
) -> dict[str, Any] | None:
    """The update that sends the run to wait for a person instead of locking, or None when the suite may lock.

    `graded` is the QA lead's severity of each finding, None when the QA lead did not read the suite this time: its
    earlier gating findings then stay as they were, neither resolved nor raised again. The ledger and the decision
    log are brought up to date in `update` either way. Never raises: a gate that cannot be read locks as before.
    """
    if not applies(state):
        return None
    try:
        return _before_the_lock(state, update, root, problems, findings, graded, cannot, raised)
    except Exception as error:  # noqa: BLE001 - the suite locks as it did before the gate
        from app.observability.degraded import degraded

        degraded("suite_gate.before_the_lock", error)
        return None


def _before_the_lock(state, update, root, problems, findings, graded, cannot, raised):
    from app.graph.workflow import _handing_on

    rounds = int(state.get("acceptance_round") or 1)
    current = gating_findings(root, problems, findings, graded or {}, cannot, raised)
    entries = [dict(entry) for entry in _ledger(state).get("findings") or []]
    matched: set[int] = set()

    def the_current_one(entry: dict[str, Any]) -> int | None:
        for at, (text, source, _severity) in enumerate(current):
            if at not in matched and source == entry.get("source") and _the_same(text, str(entry.get("text") or "")):
                return at
        return None

    for entry in entries:
        if entry.get("status") not in ("open", "approved"):
            continue
        at = the_current_one(entry)
        if at is not None:
            matched.add(at)
            if entry.get("status") == "open":
                entry.update(text=current[at][0], severity=current[at][2])
            continue
        if entry.get("status") == "approved" or (entry.get("source") == QA_LEAD and graded is None):
            continue
        reader = "the QA lead" if entry.get("source") == QA_LEAD else f"the harness's check `{entry.get('source')}`"
        entry.update(status="resolved", settled=f"acceptance round {rounds}", how=f"{reader} no longer finds it")
        _record(state, update, entry, f"resolved in acceptance round {rounds}", entry["how"], decided_by="auto")
    for at, (text, source, severity) in enumerate(current):
        if at not in matched:
            entries.append({"number": len(entries) + 1, "source": source, "severity": severity, "text": text,
                            "raised": rounds, "status": "open"})
    if not entries:
        return None
    # A person's approval locks the suite as it stood when they gave it, once: never a later sprint's addition.
    ledger = {**_ledger(state), "round": rounds, "findings": entries, "approved_at": None}
    update[KEY] = ledger
    still = [entry for entry in entries if entry.get("status") == "open"]
    if not still:
        return None
    logger.warning("The acceptance suite is not locked: %d finding(s) of a gating severity open", len(still))
    held = {**state, KEY: ledger}
    return _handing_on(
        **update,
        stage="escalation",
        escalation={"kind": SUITE, "error": why_it_waits(held, rounds), "findings": the_open_findings_text(held)},
    )


def approved_by_the_person(state: Any, update: dict[str, Any]) -> None:
    """Every open gating finding is approved by the person who answered the escalation gate; the suite locks as it
    stands at this round."""
    ledger = _ledger(state)
    entries = [dict(entry) for entry in ledger.get("findings") or []]
    for entry in entries:
        if entry.get("status") == "open":
            entry.update(status="approved", settled="the person at the escalation gate",
                         how="approved at the escalation gate")
            _record(state, update, entry, "approved by the person at the escalation gate",
                    "The person approved locking the suite with it open, with the open findings in front of them",
                    decided_by="user")
    update[KEY] = {**ledger, "findings": entries, "approved_at": int(state.get("acceptance_round") or 1)}


def _record(state: Any, update: dict[str, Any], entry: dict[str, Any], decision: str, how: str, *,
            decided_by: str) -> None:
    from app.decisions import record_decision

    source = "the QA lead" if entry.get("source") == QA_LEAD else f"the harness's check `{entry.get('source')}`"
    record_decision(
        state, update, point="acceptance_tests",
        question=f"Is suite finding S{entry.get('number')} ({entry.get('severity')}, raised by {source} in acceptance "
                 f"round {entry.get('raised')}) resolved before the suite is locked?",
        options=["resolved by a revision", "approved by a person", "still open"],
        decision=decision,
        rationale=f"{how}. The finding: {entry.get('text')}"[:1500],
        decided_by=decided_by,
    )


def the_open_findings_text(state: Any) -> list[str]:
    """Each open gating finding as the escalation page lists it."""
    return [f"S{entry.get('number')} ({entry.get('severity')}, round {entry.get('raised')}): {entry.get('text')}"
            for entry in open_findings(state)]


def why_it_waits(state: Any, rounds: int) -> str:
    """The reason recorded when the run waits for a person rather than locking the suite with gating findings open."""
    return (
        f"Thorough delivery locks no acceptance suite while a finding about it of a gating severity (blocking, major, "
        f"critical or high) is open, and {len(open_findings(state))} still are after {rounds} round(s). The run "
        "decides nothing about them by itself, whether or not it asked for a reviewer at this gate: an unattended "
        "run's own approvals cover the files it writes, never these. It waits for a person: Approve locks the suite "
        "as it stands with them recorded as approved by that person; Request changes sends the suite back to its "
        "writers with them and the guidance. Open: " + "; ".join(the_open_findings_text(state))
    )[:1500]


def page(error: str, findings: list[str]) -> str:
    """The escalation page a person reads at the gate."""
    lines = [
        "# The acceptance suite has findings of a gating severity open",
        "",
        error.strip() or "The suite's review still has gating findings open.",
        "",
        "This run delivers thoroughly: the suite is not locked while a finding about it of a gating severity "
        "(blocking, major, critical or high) is open, so the run waits for your decision. A gate's timeout does not "
        "decide it.",
        "",
    ]
    if findings:
        lines += ["## Still open", "", *(f"- {finding}" for finding in findings), ""]
    lines += [
        "## Your options",
        "",
        "- **Approve**: lock the suite as it stands; these findings are recorded as approved by you, and the "
        "product is built to the suite as it is.",
        "- **Request changes**: say what to do; the suite goes back to its writers with these findings and your "
        "guidance, and is reviewed again.",
        "",
    ]
    return "\n".join(lines)


def held_for_a_person(state: Any, delivery_mode: str | None = None) -> bool:
    """Whether a run's paused escalation gate holds gating suite findings, which a gate's timeout does not approve.

    Read by the approval-timeout sweep, outside the run, so the run's own delivery mode is passed. Never raises.
    """
    try:
        from app import delivery

        if str((state.get("escalation") or {}).get("kind") or "") != SUITE:
            return False
        with delivery.for_the_run(delivery_mode):
            return holds(state)
    except Exception:  # noqa: BLE001 - unknown is held: a person can always answer
        return True


#: The kind of a suite held for a person, in `state["escalation"]["kind"]`.
SUITE = "suite"


__all__ = [
    "KEY", "QA_LEAD", "SUITE", "WAITS", "applies", "approved_as_it_stands", "approved_by_the_person",
    "approved_qa_lead_findings", "before_the_lock", "gating_findings", "held_for_a_person", "holds",
    "open_findings", "page", "severity_of_a_check", "the_open_findings_text", "the_qa_lead_reads_again",
    "why_it_waits",
]
