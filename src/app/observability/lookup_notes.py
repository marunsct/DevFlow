"""Each lookup note a fixer is shown, and whether the next fix closed its defect (plan HK.4, LF.1296).

A stuck lookup (`app.graph.stuck_lookup`) put what others found into a fixer's request, and the ledger said only that a
search was made: nothing tied the note to what became of the defect, so "did looking things up help" could be answered
only by an audit stitching records together by hand (2 of 9 such defects fixed afterwards, counted that way).

- `record`: one ledger `lookup` record per note shown - its id (`note`), the defect it was for, the trigger, the
  sources asked and how many results each gave; a note shown again to another defect, or to the same one in a later
  round, is a `lookup shown again` record with the same id.
- The defect's next outcome (`fixed`, `left open`, `reverted`, ...) is then followed by a `lookup outcome` record:
  closed by the next fix or not (`outcome_seen`, called by `defect_ledger.note`).
- `outcome_lines` and `source_lines`: what `loop.sh effects` prints, read from the run's records alone - the share of
  looked-up fixes that closed their defect against stuck fixes made without a note, and each source's answer rate.
"""

from __future__ import annotations

import hashlib
import re
import threading
from collections import Counter
from typing import Any, Iterable

#: The ledger's events for a note shown, shown again, and what the next fix made of its defect.
SHOWN = "lookup"
SHOWN_AGAIN = "lookup shown again"
OUTCOME = "lookup outcome"
#: The ledger's event for what became of one fixer's lookup: looked up, or the gate that stopped it (FX.11).
GATE = "lookup gate"

#: A defect's outcomes after a fix stage, and those of them that close it.
OUTCOMES = frozenset({"fixed", "unverified", "left open", "reverted", "closed", "closed without a fixer",
                      "closed by the round's measurement"})
CLOSING = frozenset({"fixed", "closed", "closed without a fixer", "closed by the round's measurement"})

#: Where a found result came from, by the start of its label (`app.tools.lookups`), as the source is named.
_LABELS: tuple[tuple[str, str], ...] = (
    ("stack overflow", "stack exchange"), ("stack exchange", "stack exchange"), ("github", "github issues"),
    ("context7", "context7"), ("web search (brave)", "brave"), ("web search (tavily)", "tavily"),
    ("web search", "private search"),
)

#: (run, defect id) -> (note id, trigger) shown and not yet followed by an outcome; only for the outcome record.
_PENDING: dict[tuple[str, str], tuple[str, str]] = {}
_LOCK = threading.Lock()


def note_id(query: str) -> str:
    """A note's id: the same cleaned query is the same note, in any run."""
    return hashlib.sha1(str(query or "").encode("utf-8", errors="replace")).hexdigest()[:8]


def _source_of(label: str) -> str:
    said = str(label or "").strip().lower()
    return next((name for start, name in _LABELS if said.startswith(start)), "other")


def answered_by(answer: dict[str, Any]) -> dict[str, int]:
    """Results each asked source gave: from the answer's own `by_source` when it has one, else by each result's
    label; a source asked that gave nothing is 0."""
    given = answer.get("by_source")
    if isinstance(given, dict):
        return {str(name): int(n) if isinstance(n, int) else int(str(n).strip().lower() == "answered")
                for name, n in given.items()}
    counts: Counter = Counter({str(name): 0 for name in answer.get("asked") or []})
    for item in answer.get("found") or []:
        counts[_source_of(str(item.get("source") or ""))] += 1
    return dict(counts)


def _run_id() -> str:
    try:
        from app.observability.transcript import _run_id_from_config

        return str(_run_id_from_config() or "")
    except Exception:  # noqa: BLE001
        return ""


def record(stage: str, answer: dict[str, Any], *, trigger: str, defect: Any = None, again: bool = False,
           fields: dict[str, Any] | None = None) -> str:
    """The ledger record of one note shown (`again`: one already found this run, shown once more); its id. `fields`:
    more of what the note was made of, kept beside them - its queries, sources and verdict (`stuck_research`). Never
    raises."""
    query = str(answer.get("query") or "")
    the_id = note_id(query)
    try:
        from app.observability import defect_ledger

        found = len(answer.get("found") or [])
        by_source = answered_by(answer)
        detail = (f"{trigger}: shown again, searched {query!r} earlier in the run; note {the_id}" if again else
                  f"{trigger}: searched {query!r}: {found} found"
                  + (" (cached)" if answer.get("cached") else f" from {', '.join(answer.get('asked') or [])}")
                  + (f"; skipped {'; '.join(answer['skipped'])}" if answer.get("skipped") else "")
                  + f"; note {the_id}")
        defect_ledger.note(SHOWN_AGAIN if again else SHOWN, stage, defect=defect, detail=detail, note=the_id,
                           trigger=trigger, **({} if again else {
                               "asked": list(answer.get("asked") or []), "answered": by_source, "found": found,
                               "cached": bool(answer.get("cached")), **(fields or {})}))
        if defect is not None and (again or found):
            with _LOCK:
                _PENDING[(_run_id(), defect_ledger.defect_id(defect))] = (the_id, trigger)
    except Exception:  # noqa: BLE001 - a record must never fail the stage
        pass
    return the_id


def gate_seen(stage: str, defect: Any, gate: str, *, trigger: str = "") -> None:
    """One ledger record per fixer shown: whether its error was looked up, or the gate that stopped it (FX.11).
    Measured before it: on a medium run none of eight fixers' lookups got past its gates, and nothing said which gate,
    so the audit could only print "not reached". Never raises."""
    try:
        from app.observability import defect_ledger

        defect_ledger.note(GATE, stage, defect=defect, gate=str(gate or ""), trigger=str(trigger or ""),
                           detail=f"{trigger}: {gate}" if trigger else str(gate or ""))
    except Exception:  # noqa: BLE001 - a record must never fail the stage
        pass


def outcome_seen(event: str, stage: str, defect: Any, defect_key: str) -> None:
    """After a defect's outcome is recorded: when it had a note shown since its last outcome, a `lookup outcome`
    record says whether this fix closed it. Never raises."""
    if event not in OUTCOMES or not defect_key:
        return
    try:
        with _LOCK:
            pending = _PENDING.pop((_run_id(), defect_key), None)
        if pending is None:
            return
        from app.observability import defect_ledger

        the_id, trigger = pending
        closed = event in CLOSING
        defect_ledger.note(OUTCOME, stage, defect=defect, note=the_id, trigger=trigger, closed=closed,
                           detail=f"{trigger}: {'closed' if closed else 'not closed'} by the next fix ({event}); "
                                  f"note {the_id}")
    except Exception:  # noqa: BLE001
        pass


# --- read back from a run's records ----------------------------------------------------------------------------------

def _ledger(records: Iterable[dict]) -> list[dict]:
    return [r for r in records if isinstance(r, dict) and r.get("kind") == "defect" and r.get("defect_id")]


_N_FOUND = re.compile(r": (\d+) found\b")


def _a_note_was_shown(record: dict) -> bool:
    """Whether a lookup record put a note in a request: a search that found nothing showed none. A record written
    before the `found` field says it in its detail."""
    if record.get("event") == SHOWN_AGAIN:
        return True
    if "found" in record:
        return int(record.get("found") or 0) > 0
    said = _N_FOUND.search(str(record.get("detail") or ""))
    return said is None or int(said.group(1)) > 0


def outcomes(records: Iterable[dict]) -> dict[str, list[bool | None]]:
    """For a run's records, in order: "with a note" - for each note shown to a defect, whether that defect's next
    outcome closed it (None: no outcome yet); "without a note" - for each fix that left a defect open with no note
    shown before its next one, whether that next one closed it."""
    with_note: list[bool | None] = []
    without: list[bool | None] = []
    waiting_note: dict[str, list[int]] = {}
    left_open: set[str] = set()
    noted: set[str] = set()
    for record in _ledger(records):
        defect, event = str(record["defect_id"]), str(record.get("event") or "")
        if event in {SHOWN, SHOWN_AGAIN} and _a_note_was_shown(record):
            waiting_note.setdefault(defect, []).append(len(with_note))
            with_note.append(None)
            noted.add(defect)
        elif event in OUTCOMES:
            closed = event in CLOSING
            for at in waiting_note.pop(defect, []):
                with_note[at] = closed
            if defect in left_open and defect not in noted:
                without.append(closed)
            left_open.discard(defect)
            noted.discard(defect)
            if not closed:
                left_open.add(defect)
    return {"with a note": with_note, "without a note": without}


def outcome_lines(records: Iterable[dict]) -> list[str]:
    """`loop.sh effects`' line for HK.4: looked-up fixes that closed their defect, against stuck fixes without one."""
    label = "HK.4 looked-up defects closed by the next fix"
    found = outcomes(list(records))
    shown, without = found["with a note"], found["without a note"]
    if not shown:
        return [f"     -  {label}: not reached"]
    measured = [o for o in shown if o is not None]
    closed = sum(1 for o in measured if o)
    rest = [o for o in without if o is not None]
    return [f"  {closed:>4}  {label}: {closed} of {len(measured)}"
            + (f" ({len(shown) - len(measured)} with no outcome yet)" if len(measured) < len(shown) else "")
            + f"; stuck fixes without a note: {sum(1 for o in rest if o)} of {len(rest)} closed by their next fix"]


def source_lines(records: Iterable[dict]) -> list[str]:
    """`loop.sh effects`' line for KS.6: each lookup source's answer rate over the lookups that asked it (an answer
    from the cache asked no one)."""
    asked: Counter = Counter()
    answered: Counter = Counter()
    for record in records:
        if not isinstance(record, dict) or record.get("kind") != "defect" or record.get("event") != SHOWN:
            continue
        if record.get("cached") or not isinstance(record.get("answered"), dict):
            continue
        for name, n in record["answered"].items():
            asked[name] += 1
            answered[name] += 1 if int(n or 0) > 0 else 0
    label = "KS.6 lookup sources answering"
    if not asked:
        return [f"     -  {label}: not reached"]
    return [f"  {sum(asked.values()):>4}  {label}: "
            + ", ".join(f"{name} {answered[name]} of {n}" for name, n in asked.most_common())]


def gate_lines(records: Iterable[dict]) -> list[str]:
    """`loop.sh effects`' line for FX.11: for the fixers shown, how many lookups ran and what stopped the rest."""
    gates: Counter = Counter()
    looked_up: Counter = Counter()
    for record in _ledger(records):
        if record.get("event") != GATE:
            continue
        gate = str(record.get("gate") or "?")
        gates[gate] += 1
        if gate == "looked up":
            looked_up[str(record.get("trigger") or "?")] += 1
    label = "FX.11 fixers' lookups, by the gate that stopped them"
    if not gates:
        return [f"     -  {label}: not reached"]
    said = []
    for gate, n in gates.most_common():
        said.append(f"{gate} {n}" + (" (" + ", ".join(f"{t} {k}" for t, k in looked_up.most_common()) + ")"
                                     if gate == "looked up" else ""))
    return [f"  {sum(gates.values()):>4}  {label}: " + ", ".join(said)]


__all__ = ["CLOSING", "GATE", "OUTCOME", "OUTCOMES", "SHOWN", "SHOWN_AGAIN", "answered_by", "gate_lines",
           "gate_seen", "note_id", "outcome_lines", "outcome_seen", "outcomes", "record", "source_lines"]
