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


def _rebuilt(entry: dict[str, Any], why_still_open: str = "") -> Any:
    from app.agents.architecture_reviewer import ArchitectureReviewFinding

    fields = dict(entry.get("finding") or {})
    evidence = str(fields.get("evidence") or "Raised by an earlier review of the specification.")
    return ArchitectureReviewFinding(
        severity=str(fields.get("severity") or "major"),
        description=str(fields.get("description") or entry.get("text") or ""),
        evidence=(f"{evidence} Still open: {why_still_open}" if why_still_open else evidence),
        required_remediation=str(fields.get("required_remediation") or "Resolve it in the specification."),
    )


# --- What a resolution rests on (LF.1440) ---------------------------------------------------------------------------
#
# Measured on a medium run: three of the last six gating findings were resolved on the re-review's word about a
# sentence of the specification that was false or could not be built - "SQLAlchemy maps ARRAY columns to JSON type" on
# SQLite (it does not: the tables could not be created), "database.py calls alembic.command.upgrade(engine, 'head')"
# (the command takes a configuration, not an engine), and "each acceptance test runs in its own Playwright worker
# process with a separate SQLite file" (the harness starts the product once for the suite). Every quote was in the
# specification, so "is the quote there" would not have caught them; what was wrong was the kind of evidence. Sprint 1
# took 9 h 53 min for 8 -> 9 of 21 tests, with the three stacked blockers in the code.
#
# Now a resolution must quote the specification's own words; one that rests on how a tool of the chosen stack behaves
# is resolved on a claim to verify, which every later builder and the lead read as such; and one that rests on how the
# harness runs the acceptance suite is refused at the gate, since the product does not change that.

#: Consecutive words of a resolution that must be found in the specification for it to count as quoting it.
QUOTED_WORDS = 6
#: Where the claims are kept for the stages that build on them.
CLAIMS_FILE = ".harness/design-claims.json"
#: Words a sentence uses about how a test runner runs the suite: its configuration, its workers or processes.
_HOW_THE_SUITE_RUNS = re.compile(r"\bconfig\w*|\bworkers?\b|\bworkerid\b|\bprocess(?:es)?\b|\bparallel\b", re.I)
#: Where a stack entry's tool name ends: its note in brackets, or what it is used for.
_NAME_ENDS = re.compile(r"\s*\(|\s+(?:for|with|against|on|via|as)\s+", re.I)


class _RestsOn:
    """What a resolution rests on: the stack's tools it names, the claim it quotes, and why it is refused ("")."""

    def __init__(self, tools: list[str] | None = None, claim: str = "", refused: str = "", *,
                 unquoted: bool = False) -> None:
        self.tools, self.claim, self.refused = list(tools or []), claim, refused
        #: Refused only for quoting nothing of the specification: the harness may check it itself (LF.1504).
        self.unquoted = unquoted


def _strings(value: Any) -> list[str]:
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings(item)]
    if isinstance(value, (list, tuple)):
        return [text for item in value for text in _strings(item)]
    return []


def _word_list(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", str(text or "").lower())


def quotes_the_specification(where: str, specification: Any) -> bool | None:
    """Whether `where` holds `QUOTED_WORDS` consecutive words of the specification; None when there is none to read."""
    spec_words = " " + " ".join(word for text in _strings(specification) for word in _word_list(text)) + " "
    if not spec_words.strip():
        return None
    words = _word_list(where)
    if len(words) < QUOTED_WORDS:
        return False
    return any(f" {' '.join(words[at:at + QUOTED_WORDS])} " in spec_words for at in range(len(words) - QUOTED_WORDS + 1))


def _the_stack_s_tools(stack: Any) -> tuple[list[str], set[str]]:
    """The tool names of the chosen stack, and those of them that run the acceptance tests."""
    def field(name: str) -> Any:
        return stack.get(name) if isinstance(stack, dict) else getattr(stack, name, None)

    entries: list[tuple[str, bool]] = []
    for name in ("framework", "frontend_framework", "database"):
        entries.append((str(field(name) or ""), False))
    for part in str(field("testing_framework") or "").split(","):
        entries.append((part, "acceptance" in part.lower()))
    entries.extend((str(item), False) for item in field("additional_tools") or [])
    tools: list[str] = []
    acceptance: set[str] = set()
    for text, runs_acceptance in entries:
        head = _NAME_ENDS.split(text.strip(), maxsplit=1)[0].strip(" .;:")
        if len(head) < 3 or len(head) > 40:
            continue
        if head.lower() not in {tool.lower() for tool in tools}:
            tools.append(head)
        if runs_acceptance:
            acceptance.add(head.lower())
    unit_runners = {(_NAME_ENDS.split(part.strip(), maxsplit=1)[0].strip(" .;:")).lower()
                    for part in str(field("testing_framework") or "").split(",") if "acceptance" not in part.lower()}
    return tools, acceptance - unit_runners


def _names(tool: str, text: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(tool)}(?![\w-])", text, re.I) is not None


def what_a_resolution_rests_on(where: str, specification: Any, stack: Any) -> _RestsOn:
    """What the re-review's resolution `where` rests on, judged against the specification and the chosen stack."""
    quoted = quotes_the_specification(where, specification)
    if quoted is False:
        return _RestsOn(refused="the re-review said it is resolved without quoting the specification's own words; "
                                "a resolution is the specification's text that resolves it, word for word",
                        unquoted=True)
    return _what_a_quote_rests_on(where, stack)


def _what_a_quote_rests_on(where: str, stack: Any) -> _RestsOn:
    """What a quote of the specification rests on: the stack's tools it names, and whether it is about how the
    acceptance suite is run."""
    tools, acceptance = _the_stack_s_tools(stack) if stack is not None else ([], set())
    named = [tool for tool in tools if _names(tool, where)]
    claim = " ".join(str(where or "").split())[:600]
    if any(tool.lower() in acceptance for tool in named) and _HOW_THE_SUITE_RUNS.search(where):
        return _RestsOn(named, claim, refused=(
            "the resolution rests on how the acceptance tests are run (their runner's configuration, workers or "
            "processes), which is the harness's and which the product does not change: the harness starts the product "
            "once and runs the whole suite against it. Resolve it in what the product itself does"))
    return _RestsOn(named, claim)


def _what_it_rests_on(state: Any, where: str) -> _RestsOn:
    try:
        stack = getattr(state.get("stack_selection"), "technology_stack", None)
        return what_a_resolution_rests_on(where, state.get("technical_specification"), stack)
    except Exception as error:  # noqa: BLE001 - resolved as the re-review says, as before
        from app.observability.degraded import degraded

        degraded("design_gate.what_it_rests_on", error)
        return _RestsOn()


# --- The harness's own check (LF.1504) -------------------------------------------------------------------------------
#
# A re-review that says a finding is resolved but quotes nothing usable is refused by the quote rule above. Where the
# finding says a section, a key or a term is missing, the harness looks for it in the current specification itself
# (`app.graph.design_gate_check`): found, the finding is resolved on the harness's own quote. The rules above still
# apply to that quote: one naming a tool of the stack is a claim to verify, one about how the suite is run is refused.
# The same check runs on every open finding before the run waits for a person.

#: How the decision log names a resolution the harness checked.
CHECKED = "resolved: checked by the harness - "


def _checked_by_the_harness(state: Any, entry: dict[str, Any]) -> tuple[str, _RestsOn] | None:
    """The specification's own words that answer `entry`, and what they rest on; None when they do not. Never raises."""
    try:
        from app.graph.design_gate_check import answered_by_the_specification

        quote = answered_by_the_specification(str(entry.get("text") or ""), state.get("technical_specification"),
                                              entry.get("absent"))
    except Exception as error:  # noqa: BLE001 - not checked: the finding stays as it is
        from app.observability.degraded import degraded

        degraded("design_gate.checked_by_the_harness", error)
        return None
    if not quote:
        return None
    try:
        # The quote is the specification's own text, so only what it rests on is judged, not whether it quotes.
        rests = _what_a_quote_rests_on(quote, getattr(state.get("stack_selection"), "technology_stack", None))
    except Exception as error:  # noqa: BLE001 - not checked: the finding stays as it is
        from app.observability.degraded import degraded

        degraded("design_gate.checked_by_the_harness", error)
        return None
    return None if rests.refused else (quote, rests)


def _resolved_by_the_check(entry: dict[str, Any], checked: tuple[str, _RestsOn]) -> str:
    """How `entry` was resolved on the harness's check; a quote that names a tool of the stack is a claim to verify."""
    quote, rests = checked
    entry.pop("refused", None)
    if rests.tools:
        entry["assumption"] = {"claim": rests.claim, "rests_on": rests.tools}
        return (f"{CHECKED}{quote} - a claim about how {', '.join(rests.tools)} "
                f"behave{'s' if len(rests.tools) == 1 else ''}, which nothing has checked - a claim to verify, not a fact")
    return f"{CHECKED}{quote}"


def _absent(text: str, state: Any) -> list[str]:
    try:
        from app.graph.design_gate_check import absent_terms

        return absent_terms(text, state.get("technical_specification"))
    except Exception:  # noqa: BLE001 - no terms kept: the check then settles only sections
        return []


def holds_after_checking(state: Any, update: dict[str, Any]) -> bool:
    """`holds`, once each open gating finding the reviewer raised has been checked against the specification itself.

    Called when the run is about to wait for a person: one the specification now answers is resolved on the harness's
    quote and recorded, so the run does not stop on it. One the last re-review said is still open is left to the
    person. Never raises.
    """
    try:
        ledger = _ledger(state)
        entries = [dict(entry) for entry in ledger.get("findings") or []]
        last = int(ledger.get("round") or 0)
        settled = []
        for entry in entries:
            if entry.get("status") != "open" or entry.get("source") != REVIEWER or entry.get("still_open") == last:
                continue
            checked = _checked_by_the_harness(state, entry)
            if checked is None:
                continue
            how = _resolved_by_the_check(entry, checked)
            entry.update(status="resolved", settled="the harness's check before waiting for a person", how=how)
            settled.append(entry)
            _record(state, update, entry, "resolved before waiting for a person"
                    + (", on a claim to verify" if entry.get("assumption") else ""), how, decided_by="auto")
        if settled:
            logger.info("Design gate: %d open gating finding(s) answered by the specification itself", len(settled))
            update[KEY] = {**ledger, "findings": entries}
            _keep_the_claims(state, entries)
            return holds({**dict(state), KEY: update[KEY]})
    except Exception as error:  # noqa: BLE001 - held as before: a person can always answer
        from app.observability.degraded import degraded

        degraded("design_gate.holds_after_checking", error)
    return holds(state)


def _keep_the_claims(state: Any, entries: list[dict[str, Any]]) -> None:
    """Keep the resolved findings that rest on a claim, for `the_claims_section`. Never raises."""
    try:
        import json
        from pathlib import Path

        claims = [{"finding": f"G{entry.get('number')}", "text": str(entry.get("text") or "")[:400],
                   "claim": entry["assumption"].get("claim", ""), "rests_on": entry["assumption"].get("rests_on", [])}
                  for entry in entries if entry.get("status") == "resolved" and isinstance(entry.get("assumption"), dict)]
        root = getattr(state.get("repository"), "root_path", None) if hasattr(state, "get") else None
        if not root or not claims:
            return
        path = Path(root) / CLAIMS_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(claims, indent=1), encoding="utf-8")
    except Exception as error:  # noqa: BLE001 - the decision log still says so
        from app.observability.degraded import degraded

        degraded("design_gate.keep_the_claims", error)


#: The heading of the claims every later stage reads.
CLAIMS_HEADING = "--- Design claims to verify, not facts ---"


def the_claims_section(root: Any) -> str:
    """The design findings resolved on a claim about how a tool of the stack behaves, as a block the lead and every
    builder read; "" when there are none. Never raises."""
    try:
        import json
        from pathlib import Path

        if not root:
            return ""
        claims = json.loads((Path(root) / CLAIMS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return ""
    if not isinstance(claims, list) or not claims:
        return ""
    lines = [f"- {item.get('finding')} (about {', '.join(item.get('rests_on') or [])}): \"{item.get('claim')}\""
             for item in claims if isinstance(item, dict)]
    return (
        f"\n\n{CLAIMS_HEADING}\n"
        "The design review settled these findings on a sentence of the specification about how a library, a tool or "
        "the test setup behaves. Nothing has checked the sentence. The first work that depends on one shows it holds "
        "with a command or a test before building on it; a failure that contradicts one means the claim is wrong, not "
        "the code around it.\n" + "\n".join(lines) + "\n"
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
            rests = _what_it_rests_on(state, answer[1])
            checked = _checked_by_the_harness(state, entry) if rests.unquoted else None
            if checked is not None:
                # Resolved, but on the harness's own quote of the specification (LF.1504).
                resolved.append((entry, _resolved_by_the_check(entry, checked)))
                continue
            if rests.refused:
                # Not resolved: kept open and sent back with the reason (LF.1440).
                logger.info("Design gate: G%s kept open: %s", entry.get("number"), rests.refused)
                entry["refused"] = rests.refused
                carried.append(_rebuilt(entry, rests.refused))
                continue
            if rests.tools:
                entry["assumption"] = {"claim": rests.claim, "rests_on": rests.tools}
                resolved.append((entry, f"the re-review says it is resolved on a claim about how {', '.join(rests.tools)}"
                                        f" behave{'s' if len(rests.tools) == 1 else ''}, which nothing has checked - a "
                                        f"claim to verify, not a fact: {answer[1]}"))
                continue
            resolved.append((entry, "the re-review says it is resolved" + (f": {answer[1]}" if answer[1] else "")))
            # Raised again in other words, the new one is open as a finding of this round (added below).
            continue
        if at is not None:
            matched.add(at)
            entry["text"] = current[at][1]
            entry["finding"] = _dumped(current[at][0])
            entry["still_open"] = this_round
            continue
        if answer is not None:
            entry["still_open"] = this_round
            carried.append(_rebuilt(entry))
            continue
        resolved.append((entry, "the re-review no longer finds it"))

    for at, item in enumerate(current):
        if at not in matched:
            entries.append(_an_entry(len(entries) + 1, item, this_round, _absent(item[1], state)))
    for entry, how in resolved:
        entry.update(status="resolved", settled=f"review round {this_round}", how=how)
        decision = f"resolved in review round {this_round}" + (", on a claim to verify" if entry.get("assumption") else "")
        _record(state, update, entry, decision, how, decided_by="auto")
    update[KEY] = {"round": this_round, "findings": entries}
    _keep_the_claims(state, entries)
    if carried:
        logger.info("Design gate: %d gating finding(s) the re-review says are still open put back into it", len(carried))
        review = review.model_copy(update={"findings": [*review.findings, *carried], "status": "changes_required"})
    return review


def _an_entry(number: int, item: tuple[Any, str, str], this_round: int,
              absent: list[str] | None = None) -> dict[str, Any]:
    finding, text, source = item
    entry = {"number": number, "source": source, "text": text, "finding": _dumped(finding),
             "raised": this_round, "status": "open"}
    if absent:
        # The terms it says are missing that the specification it was raised on does not name (LF.1504).
        entry["absent"] = absent
    return entry


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
    "approved_by_the_person", "held_for_a_person", "holds", "holds_after_checking", "open_findings", "settled_by_the_checks",
    "the_open_findings_text", "why_it_waits",
]
