"""Fast delivery holds the build on a design finding only when it says the product cannot work (LF.1524, behind
`FAST_DESIGN_GATE_ON_PRODUCT_BREAKING`).

The owner asked why fast delivery builds a product with blocking, critical and major design findings open. Measured on
135 scored runs from 11-18: 23 were built with a gap naming such a finding, and their hidden score (mean 0.980, 13%
losing a hidden test) was that of all runs (13%). Most such findings are about the documents - contract lines in none
of the reader's forms, sections that word one thing two ways - and some were false. Holding on every serious finding is
not supported; holding on the ones that mean the product cannot work is.

So in fast delivery a gating finding (blocking, critical, major, high) holds the build only if it is product-breaking,
in one of four classes (`PHRASINGS`, read from the reviewer's own words with the specification's quotes taken out):

- **start**: the product cannot start in the harness setup - a secret, variable or service it needs that the setup does
  not give and that has no development default, or a port or path the setup does not give;
- **brief**: a requirement of the brief is dropped, deferred or redefined, by the reviewer's words, by the workflow's own
  coverage and deferral checks, or by `brief_actions_the_text_defers` on the finding's own quotes;
- **security**: one user can read or change another's data, or authentication the product has is skipped;
- **contract**: what the acceptance suite is written from contradicts itself on a status code or a field.

Anything else - the document's form, wording or completeness - is not held: recorded as before, by the design
escalation, as a known risk. A held finding gets one revision more than fast delivery gives (`MOST_REVISIONS`, two),
each followed by a review that says whether it is still open; then the design escalation records it as before. Never a
loop. Every held finding's course is a decision in the log; `effects_lines` counts them.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from app.switches import is_on

logger = logging.getLogger(__name__)

#: Off in code like every switch; the compose file says whether it is on.
ON_BY_DEFAULT = False
SWITCH = "FAST_DESIGN_GATE_ON_PRODUCT_BREAKING"

#: The state key of the ledger: {"round": the last review round, "findings": [entry, ...]}.
KEY = "fast_design_gate"

#: Revisions a held finding gets in fast delivery: one more than fast delivery gives any other.
MOST_REVISIONS = 2

#: What a held finding's decision says (the switch-firing register and the effects report read it).
SAID = "held as product-breaking"
#: What a review round's decision about the gating findings not held says.
NOT_HELD = "not held: about the document, not the product"
#: What the decision of the extra revision says.
EXTRA = "a revision more for the product-breaking findings"

START, BRIEF, SECURITY, CONTRACT = "start", "brief", "security", "contract"

#: Each class in the words the decision log uses.
CLASSES: dict[str, str] = {
    START: "the product cannot start in the harness setup",
    BRIEF: "a requirement of the brief is dropped, deferred or redefined",
    SECURITY: "one user's data is open to another, or authentication is skipped",
    CONTRACT: "the contract the acceptance suite is written from contradicts itself on a status code or a field",
}

#: The workflow's own design checks by the class of what they find; a check not listed finds the document's form
#: (`contract`: lines in none of the reader's forms) or a kept file's place (`kept`, `signature`), which are not held.
CHECKS: dict[str, str] = {"coverage": BRIEF, "deferrals": BRIEF, "order": CONTRACT}

#: What the harness setup gives every product it starts (`app.acceptance.start_probe`): a finding about one of these
#: being unset is about a case the setup never makes.
GIVEN_BY_THE_SETUP = frozenset({"PORT", "HOST", "DATA_DIR"})


def _p(text: str) -> re.Pattern[str]:
    return re.compile(text, re.I)


#: The phrasings, in plain English, the reviewer's own words are matched against: (class, what it says, pattern).
#: The document class is read first and holds nothing; the others in the order listed.
PHRASINGS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("document", "lines of the contract follow none of its forms",
     _p(r"\bfollows? none of (its|the|three)\b|\b(do|does) not follow any of the (three )?(prescribed|accepted|allowed)")),
    ("document", "a typo, the wording, the formatting or the numbering",
     _p(r"\b(typos?|misspel\w*|wording|phrasing|formatting|numbering)\b")),
    (START, "the setup does not give what the product needs",
     _p(r"\b(the harness|the setup|the harness's setup|the environment)\b[^.]{0,60}\b(does not|doesn't|never|will not) "
        r"(give|provide|set|pass|supply|expose)\b")),
    (START, "it needs a service the setup does not run",
     _p(r"\brequires? (an? )?(external|running|separate|third-party|hosted) (service|server|database|broker|cache|api)\b")),
    # The setup hands the product a data folder that does not exist yet (`app.acceptance.start_probe`): measured on one
    # run, a service that never made it stopped at once.
    (START, "nothing makes the data folder, which the setup gives not yet made",
     _p(r"\b(data_dir|data directory|data folder)\b[^.]{0,120}\b(is not|isn't|never|not) (be )?(created|made)\b"
        r"|\bno (mechanism|step|code)\b[^.]{0,80}\b(creates?|make|makes|mkdir)\b[^.]{0,40}\b(data_dir|directory|folder)\b"
        r"|\b(does not|doesn't|do not) create (the )?(data_dir|data directory|data folder)\b")),
    (START, "a path outside the data folder the setup gives",
     _p(r"\b(path|directory|folder|file)s?\b[^.]{0,60}\b(outside|not under|instead of) (the )?data_dir\b")),
    (START, "a fixed port instead of the one the setup gives",
     _p(r"\b(hard-?coded|fixed) port\b|\bport \d{2,5}\b[^.]{0,40}\b(instead of|rather than|regardless of) (the )?port\b"
        r"|\bignores? (the )?port\b")),
    (BRIEF, "it defers a feature or a requirement",
     _p(r"\bdefers? (a|the|an) (feature|requirement|capability)|\b(explicitly |entirely )?defers\b[^.]{0,160}"
        r"\b(brief|requirement|core feature)")),
    (BRIEF, "despite the brief",
     _p(r"\bdespite (the brief|it being|this being|the brief's)")),
    (BRIEF, "it contradicts, redefines, narrows or drops the brief",
     _p(r"\b(contradicts|redefines|narrows|drops|omits|ignores|violates) (the|what the|a) (operator's )?brief")),
    (BRIEF, "the brief requires it",
     _p(r"\brequired by the (operator's )?brief")),
    (BRIEF, "the brief says one thing and the specification another",
     _p(r"\bthe brief (requires|states|says|asks|lists|specifies)\b[^.]{0,200}\b(but|yet|while|whereas|however)\b"
        r"[^.]{0,80}\b(defers|drops|omits|redefines|narrows|replaces|changes|contradicts|never)\b")),
    (SECURITY, "another user's data",
     _p(r"\b(another|other|any other|different) (user|account|owner)s?'?s?\b[^.]{0,60}\b(data|notes?|items?|records?|"
        r"resources?|bookmarks?|rows?|lists?)\b")),
    (SECURITY, "any user can read or change it",
     _p(r"\bany (authenticated |logged-in |signed-in )?(user|account|client) (can|could|may) "
        r"(read|modify|delete|change|access|see|edit|update|list)\b")),
    (SECURITY, "not scoped to the user",
     _p(r"\bnot (scoped|restricted|filtered|limited) (to|by) the (current|authenticated|owning|requesting|signed-in) "
        r"(user|account)\b|\b(no|missing|without an?) (ownership|owner) (check|verification|filter)\b"
        r"|\b(idor|insecure direct object)")),
    (SECURITY, "authentication skipped",
     _p(r"\b(skips?|bypass\w*|do not require|does not require|never checks?|never requires?)\b[^.]{0,20}"
        r"\b(authentication|authorization|auth check|sign[- ]in|login)\b"
        r"|\bunauthenticated (users?|clients?|requests?|callers?) (can|could|may)\b")),
)

#: A contradiction, in the reviewer's words.
_CONTRADICTS = _p(r"\b(contradict\w*|inconsisten\w*|conflict\w*|mismatch\w*|disagree\w*|mutually exclusive|instead of)\b")
#: A status code a request is answered with.
_STATUS = _p(r"\b(200|201|202|204|301|302|303|304|307|308|400|401|403|404|405|406|409|410|411|413|415|422|429|500|501|"
             r"502|503)\b|\bstatus codes?\b|\bhttp status\b")
#: A field of what is sent or answered.
_FIELD = _p(r"\b(fields?|keys?|propert(y|ies)|attributes?)\b")
_WIRE = _p(r"\b(requests?|responses?|json|payloads?|bod(y|ies)|schemas?)\b")
#: A line of the specification the reviewer points at, or a size or a time: its number is not a status code.
_A_LINE = _p(r"\blines? \d+(\s*[-–]\s*\d+)?|\b\d+[- ](lines?|characters?|chars|bytes|ms|seconds|minutes|kb|mb)\b")
#: The specification's own words quoted in a finding: what it says, not what the reviewer says of it.
_QUOTED = re.compile(r"`[^`]*`|\"[^\"]*\"|“[^”]*”|(?<![A-Za-z])'[^']{2,}?'(?![A-Za-z])")
#: A setting by name, as the environment gives it.
_A_VARIABLE = re.compile(r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b|\b(?:PORT|HOST)\b")
_UNSET = _p(r"\b(no (development |dev |local |usable )?default|not set|unset|missing|keyerror)\b")
_NEEDED = _p(r"\b(secret|key|token|credential|password|url|service)s?\b")


def enabled() -> bool:
    return is_on(SWITCH, ON_BY_DEFAULT)


def applies() -> bool:
    """Whether this run holds the build on product-breaking design findings: on, and fast delivery."""
    try:
        from app.graph import design_gate

        return enabled() and not design_gate.applies()
    except Exception:  # noqa: BLE001 - not applied: the run goes on as before
        return False


def _field(finding: Any, name: str) -> str:
    value = finding.get(name) if isinstance(finding, dict) else getattr(finding, name, "")
    return str(value or "")


def _said(text: str) -> str:
    """The reviewer's own words: the quotes of the specification taken out, and the line numbers it points at."""
    return _A_LINE.sub(" ", _QUOTED.sub(" ", text))


def product_breaking(finding: Any, *, source: str = "review", brief: str = "") -> str:
    """The class of product-breaking finding `finding` is (`CLASSES`), or "" when it does not say the product cannot
    work. `source` is the workflow's check that raised it, or "review"; `brief` the operator's brief. Never raises."""
    try:
        return _product_breaking(finding, source, brief)
    except Exception as error:  # noqa: BLE001 - not held: recorded as before
        from app.observability.degraded import degraded

        degraded("fast_design_gate.product_breaking", error)
        return ""


def _product_breaking(finding: Any, source: str, brief: str) -> str:
    if source != "review":
        return CHECKS.get(source, "")
    description = _field(finding, "description")
    whole = " ".join(_field(finding, name) for name in ("description", "evidence", "required_remediation"))
    said, said_of_it_all = _said(description), _said(whole)
    for kind, _what, pattern in PHRASINGS:
        if kind == "document" and pattern.search(said):
            return ""
    for kind, _what, pattern in PHRASINGS:
        if kind in (START, SECURITY) and pattern.search(said):
            return kind
        if kind == BRIEF and pattern.search(said_of_it_all):
            return kind
    if set(_A_VARIABLE.findall(whole)) - GIVEN_BY_THE_SETUP and _UNSET.search(said) and _NEEDED.search(said):
        return START
    if brief:
        from app.analysis.integration_checks import brief_actions_the_text_defers

        if brief_actions_the_text_defers(brief, whole):
            return BRIEF
    if _CONTRADICTS.search(said) and (_STATUS.search(said) or (_FIELD.search(said) and _WIRE.search(said))):
        return CONTRACT
    return ""


# --- The ledger -------------------------------------------------------------------------------------------------------


def _ledger(state: Any) -> dict[str, Any]:
    held = state.get(KEY) if hasattr(state, "get") else None
    return held if isinstance(held, dict) else {"round": 0, "findings": []}


def open_held(state: Any) -> list[dict[str, Any]]:
    """The held findings still open, in the order they were raised."""
    return [dict(entry) for entry in _ledger(state).get("findings") or [] if entry.get("status") == "open"]


def a_held_finding_is_open(state: Any) -> bool:
    """Whether a product-breaking finding is open, which only a review can say is resolved: on and fast delivery."""
    return applies() and bool(open_held(state))


def a_held_finding_the_reviewer_raised_is_open(state: Any) -> bool:
    return applies() and any(entry.get("source") == "review" for entry in open_held(state))


def checks_to_ask_again(state: Any, asked: list[str]) -> list[str]:
    """The workflow's checks that raised an open held finding and were not asked on this review."""
    if not applies():
        return []
    return [name for name in dict.fromkeys(str(entry.get("source")) for entry in open_held(state))
            if name != "review" and name not in asked]


def after_a_review(state: Any, update: dict[str, Any], review: Any, raised_by_checks: dict[str, Any],
                   gating: list[Any]) -> None:
    """The ledger brought up to date with this review, and the decision log with what it settled. Never raises.

    `gating` is the review's findings that gate, `raised_by_checks` what each of the workflow's checks found on it. A
    held finding is still open when the re-review says so, raises it again, or its check still finds it; otherwise it
    is resolved. The gating findings not held are recorded in one decision.
    """
    if not applies():
        return
    try:
        _after_a_review(state, update, review, raised_by_checks, gating)
    except Exception as error:  # noqa: BLE001 - nothing held: the run goes on as before
        from app.observability.degraded import degraded

        degraded("fast_design_gate.after_a_review", error)


def _after_a_review(state: Any, update: dict[str, Any], review: Any, raised_by_checks: dict[str, Any],
                    gating: list[Any]) -> None:
    from app.graph.design_gate import _answers, _numbered, _text, _the_same

    ledger = _ledger(state)
    this_round = int(ledger.get("round") or 0) + 1
    entries = [dict(entry) for entry in ledger.get("findings") or []]
    by_check = {id(finding): name for name, finding in raised_by_checks.items() if finding is not None}
    brief = getattr(state.get("document"), "text", "") or ""
    current = []
    not_held = []
    for finding in gating:
        source = by_check.get(id(finding), "review")
        kind = product_breaking(finding, source=source, brief=brief)
        if kind:
            current.append((finding, _text(finding), source, kind))
        else:
            not_held.append(_text(finding))
    answers = _answers(review)
    numbers = _numbered(state.get("architecture_review"))
    matched: set[int] = set()
    for entry in entries:
        if entry.get("status") != "open":
            continue
        at = next((at for at, (_f, text, source, _k) in enumerate(current)
                   if at not in matched and source == entry.get("source")
                   and (source != "review" or text == entry.get("text") or _the_same(text, entry.get("text", "")))),
                  None)
        if at is not None:
            matched.add(at)
            entry["text"] = current[at][1]
            continue
        answer = answers.get(numbers.get(str(entry.get("text")), -1))
        if entry.get("source") == "review" and answer is not None and not answer[0]:
            continue  # the re-review says it is still open
        if entry.get("source") != "review":
            how = f"the workflow's check `{entry.get('source')}` no longer finds it"
        elif answer is not None:
            how = "the re-review says it is resolved" + (f": {answer[1]}" if answer[1] else "")
        else:
            how = "the re-review no longer finds it"
        entry.update(status="resolved", settled=f"review round {this_round}")
        _record(state, update, entry, f"{SAID}, resolved in review round {this_round}", how)
    for at, (finding, text, source, kind) in enumerate(current):
        if at not in matched:
            entries.append({"number": len(entries) + 1, "source": source, "text": text, "kind": kind,
                            "raised": this_round, "status": "open"})
    # One decision names each finding not held, the first time it is raised: a re-review that repeats it adds nothing.
    seen = list(ledger.get("not_held") or [])
    not_held = [text for text in dict.fromkeys(not_held)
                if not any(text == earlier or _the_same(text, earlier) for earlier in seen)]
    update[KEY] = {"round": this_round, "findings": entries, "not_held": [*seen, *not_held]}
    if not_held:
        from app.decisions import record_decision

        logger.info("Fast design gate: %d gating finding(s) not held, %d held open", len(not_held),
                    len([e for e in entries if e.get("status") == "open"]))
        record_decision(
            state, update, point="technical_specification",
            question=f"Do the review round {this_round} design findings that are not product-breaking hold the build?",
            options=["hold the build", "record them as before"],
            decision=f"{len(not_held)} gating finding(s) {NOT_HELD}",
            rationale=("Fast delivery holds the build only on a finding that says the product cannot work: it cannot "
                       "start in the harness setup, a requirement of the brief is dropped, deferred or redefined, one "
                       "user's data is open to another, or the contract the suite is written from contradicts itself "
                       "on a status code or a field. These are recorded as before: "
                       + "; ".join(not_held))[:1500],
        )


def another_revision(state: Any, update: dict[str, Any], revisions: int, limit: int) -> bool:
    """Whether the specification goes back to the architect for revision `revisions` although fast delivery's `limit`
    is reached: a held finding is open and it has had fewer than `MOST_REVISIONS`. Each open held finding's decision is
    recorded: sent back, or to the design escalation. Never raises; False when off."""
    if not applies():
        return False
    try:
        entries = [dict(entry) for entry in (update.get(KEY) or _ledger(state)).get("findings") or []]
        held = [entry for entry in entries if entry.get("status") == "open"]
        if not held:
            return False
        extra = revisions >= limit and revisions <= MOST_REVISIONS
        back = revisions < limit or extra
        for entry in held:
            if back:
                _record(state, update, entry, f"{SAID}: sent back for revision {revisions} of {MOST_REVISIONS}",
                        "it says the product cannot work, so the build waits for the revision")
            else:
                entry["status"] = "escalated"
                _record(state, update, entry,
                        f"{SAID}, still open after {MOST_REVISIONS} revisions: to the design escalation",
                        "the revisions fast delivery gives a product-breaking finding are spent; the design escalation "
                        "records it as a known risk, as before")
        if not back:
            update[KEY] = {**(update.get(KEY) or _ledger(state)), "findings": entries}
        if extra:
            from app.decisions import record_decision

            logger.info("Fast design gate: %d product-breaking finding(s) open: revision %d", len(held), revisions)
            record_decision(
                state, update, point="technical_specification",
                question="Does the specification get another revision before it is built?",
                options=["revise it again", "record the open points as known risks"],
                decision=EXTRA,
                rationale=(f"{len(held)} finding(s) that say the product cannot work are still open after "
                           f"{revisions - 1} revision(s); fast delivery gives them {MOST_REVISIONS}. Open: "
                           + "; ".join(f"H{entry.get('number')}: {entry.get('text')}" for entry in held))[:1500],
            )
        return extra
    except Exception as error:  # noqa: BLE001 - as before: no revision more
        from app.observability.degraded import degraded

        degraded("fast_design_gate.another_revision", error)
        return False


def settled_by_the_checks(state: Any, update: dict[str, Any], how: str) -> None:
    """Every open held finding is resolved: the workflow's checks that raised them no longer find them."""
    if not applies():
        return
    ledger = _ledger(state)
    entries = [dict(entry) for entry in ledger.get("findings") or []]
    this_round = int(ledger.get("round") or 0) + 1
    for entry in entries:
        if entry.get("status") == "open":
            entry.update(status="resolved", settled=f"review round {this_round}")
            _record(state, update, entry, f"{SAID}, resolved in review round {this_round}", how)
    if entries:
        update[KEY] = {**ledger, "round": this_round, "findings": entries}


def _record(state: Any, update: dict[str, Any], entry: dict[str, Any], decision: str, how: str) -> None:
    from app.decisions import record_decision

    source = "the reviewer" if entry.get("source") == "review" else f"the workflow's check `{entry.get('source')}`"
    record_decision(
        state, update, point="technical_specification",
        question=(f"Is design finding H{entry.get('number')} (product-breaking: {CLASSES.get(entry.get('kind'), '')}; "
                  f"raised by {source} in review round {entry.get('raised')}) settled before the build?"),
        options=["revised", "sent back for a revision", "recorded as a known risk by the design escalation"],
        decision=decision,
        rationale=f"{how}. The finding: {entry.get('text')}"[:1500],
    )


# --- What it did, for `loop.sh effects` -------------------------------------------------------------------------------

_HELD = re.compile(r"design finding H(\d+) \(product-breaking")
_NOT_HELD_COUNT = re.compile(r"(\d+) gating finding\(s\) " + re.escape(NOT_HELD))


def effects_lines(decisions: str) -> list[str]:
    """The effects report's lines for this run's decision log: findings held and not, and the revisions they took."""
    text = str(decisions or "")
    held = len(set(_HELD.findall(text)))
    not_held = sum(int(n) for n in _NOT_HELD_COUNT.findall(text))
    extra = text.count(EXTRA)
    resolved = len(set(re.findall(r"design finding H(\d+) \(product-breaking[^\n]*\n- \*\*Decision:\*\* [^\n]*resolved",
                                  text)))
    escalated = len(set(re.findall(r"design finding H(\d+) \(product-breaking[^\n]*\n- \*\*Decision:\*\* [^\n]*"
                                   r"to the design escalation", text)))
    if not (held or not_held):
        return ["     -  LF.1524 fast delivery's design findings held as product-breaking: not reached"]
    return [
        f"  {held:>4}  LF.1524 design findings held as product-breaking ({resolved} resolved, {escalated} to the "
        "design escalation)",
        f"  {not_held:>4}  LF.1524 gating design findings not held (about the document, recorded as before)",
        f"  {extra:>4}  LF.1524 design revisions spent beyond fast delivery's one on held findings",
    ]


__all__ = [
    "CHECKS", "CLASSES", "EXTRA", "KEY", "MOST_REVISIONS", "NOT_HELD", "ON_BY_DEFAULT", "PHRASINGS", "SAID", "SWITCH",
    "a_held_finding_is_open", "a_held_finding_the_reviewer_raised_is_open", "after_a_review", "another_revision",
    "applies", "checks_to_ask_again", "effects_lines", "enabled", "open_held", "product_breaking",
    "settled_by_the_checks",
]
