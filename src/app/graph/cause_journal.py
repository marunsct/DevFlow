"""What was tried on each cause, kept for the whole run: through re-plans, rewinds and new fix cycles.

Deep review 2026-11-18, item 1.4: each defect's `attempts` lived on its remediation cycle, and a sprint that ran out of
fix rounds was planned again with `remediation=None`, so every record of what had been tried died with the cycle. The
next cycle's fixers, and the lead planning the sprint again, were shown the open defects but not what had already
failed on them. Measured: one run was planned again three times with the same change each time; a re-plan costs about
34 active minutes, and the share of defects fixed fell from 29% at a first attempt to 22% and then 11%.

The journal is a file in the workspace (`FILE`), keyed by a defect's cause key (`app.sprint.cause`), else by its
ledger id. Each fix records the files it changed, its own one-line account of what it did and how the harness
measured it. Fixers and the lead's re-plan request read it back, newest first and bounded. When one cause has failed
`DIAGNOSE_AFTER` times, the next fix of it is preceded by one call that only diagnoses (`diagnosed`, behind
`DIAGNOSE_A_RECURRING_CAUSE`); its hypothesis is kept here and shown to the fixer.
"""

from __future__ import annotations

import datetime
import json
import logging
import threading
from pathlib import Path
from typing import Any, Iterable

from app.switches import is_on

logger = logging.getLogger(__name__)

FILE = ".harness/fix-journal.json"
#: Entries kept per cause, newest last.
MOST_KEPT = 12
#: Attempts shown to one fixer, newest first.
MOST_SHOWN = 5
#: Causes shown to the lead planning a sprint again.
MOST_CAUSES_FOR_THE_LEAD = 6
#: The most a block of the journal takes in a request.
MOST_CHARACTERS = 2_400
#: Failed attempts at one cause before the next is preceded by a diagnosis.
DIAGNOSE_AFTER = 2

#: Off in code like every switch; the compose file says whether it is on.
ON_BY_DEFAULT = False

#: Parallel fixers diagnose at once; their writes to the one file are made one at a time.
_WRITING = threading.Lock()

HEADING = "--- Tried before on this cause (the harness's fix journal, newest first) ---"
LEAD_HEADING = "--- Tried before on the causes this sprint still has open (the harness's fix journal, newest first) ---"
#: What opens a diagnosis in a fixer's request; the audit's switch-firing check reads it.
DIAGNOSIS = "A diagnosis made after the attempts above failed, before this attempt:"


class _DiagnoseARecurringCause:
    """`DIAGNOSE_A_RECURRING_CAUSE` as the switch registry reads one: off in code until measured."""

    ON_BY_DEFAULT = ON_BY_DEFAULT
    #: What the admin page says this switch does.
    explanation = ("Before the third fix of a cause the first two did not fix, one call that changes nothing says why "
                   "they missed and where the cause is; the fixer is shown it. One extra call per recurring cause.")

    @staticmethod
    def enabled() -> bool:
        return is_on("DIAGNOSE_A_RECURRING_CAUSE", _DiagnoseARecurringCause.ON_BY_DEFAULT)


diagnosis_switch = _DiagnoseARecurringCause()


def diagnosis_enabled() -> bool:
    return diagnosis_switch.enabled()


def key_of(defect: Any) -> str:
    """The journal's key for a defect: its cause key, else its ledger id; "" when neither can be made."""
    try:
        from app.sprint.cause import key_of as cause_key_of

        keyed = cause_key_of(defect)
        if keyed:
            return keyed
        from app.observability.defect_ledger import defect_id

        return f"ledger:{defect_id(defect)}"
    except Exception:  # noqa: BLE001
        return ""


def _read(root: str | Path | None) -> dict[str, Any]:
    if not root:
        return {}
    try:
        data = json.loads((Path(root) / FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _one_line(text: Any, most: int = 240) -> str:
    return " ".join(str(text or "").split())[:most]


def _append(root: str | Path, defect: Any, entry: dict[str, Any], sprint: Any = None) -> None:
    key = key_of(defect)
    if not root or not key:
        return
    with _WRITING:
        data = _read(root)
        causes = data.setdefault("causes", {})
        cause = causes.setdefault(key, {"defect": "", "entries": []})
        cause["defect"] = _one_line(getattr(defect, "description", ""), 200) or cause.get("defect", "")
        if sprint is not None:
            cause["sprint"] = sprint
        at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        cause["entries"] = [*(cause.get("entries") or []), {**entry, "at": at}][-MOST_KEPT:]
        path = Path(root) / FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")


def record(root: str | Path | None, defect: Any, attempt: dict[str, Any], *, sprint: Any = None) -> None:
    """One fix attempt at `defect` (`ledger.attempt_record`'s shape), as measured. Never raises."""
    try:
        if not root or not isinstance(attempt, dict):
            return
        _append(root, defect, {
            "stage": _one_line(attempt.get("stage"), 60),
            "files": [str(f) for f in attempt.get("files") or []][:8],
            "did": _one_line(attempt.get("did")),
            "outcome": _one_line(attempt.get("outcome"), 300),
        }, sprint)
    except Exception:  # noqa: BLE001 - a journal must never fail the fix it records
        logger.debug("Could not record the fix in the journal", exc_info=True)


def add_hypothesis(root: str | Path | None, defect: Any, hypothesis: str, *, sprint: Any = None) -> None:
    """A diagnosis of `defect`'s cause, kept beside its attempts. Never raises."""
    try:
        if root and str(hypothesis or "").strip():
            _append(root, defect, {"hypothesis": _one_line(hypothesis, 600)}, sprint)
    except Exception:  # noqa: BLE001
        logger.debug("Could not record the diagnosis in the journal", exc_info=True)


def _entries(root: str | Path | None, defect: Any) -> list[dict[str, Any]]:
    key = key_of(defect)
    cause = (_read(root).get("causes") or {}).get(key) if key else None
    return [e for e in (cause or {}).get("entries") or [] if isinstance(e, dict)]


def _failed(entry: dict[str, Any]) -> bool:
    return "outcome" in entry and not str(entry.get("outcome") or "").startswith("fixed")


def failures_on(root: str | Path | None, defect: Any) -> int:
    """How many recorded attempts at this defect's cause did not fix it."""
    return sum(1 for entry in _entries(root, defect) if _failed(entry))


def needs_a_diagnosis(root: str | Path | None, defect: Any) -> bool:
    """Whether the cause has failed `DIAGNOSE_AFTER` times with no diagnosis since its last failure."""
    entries = _entries(root, defect)
    if sum(1 for entry in entries if _failed(entry)) < DIAGNOSE_AFTER:
        return False
    for entry in reversed(entries):
        if "hypothesis" in entry:
            return False
        if _failed(entry):
            return True
    return False


def _as_shown(entry: dict[str, Any]) -> tuple[str, str, str]:
    return (_one_line(entry.get("stage"), 60), _one_line(entry.get("did")), _one_line(entry.get("outcome"), 300))


def _attempt_line(entry: dict[str, Any], indent: str = "- ") -> str:
    files = ", ".join(f"`{f}`" for f in entry.get("files") or []) or "no file"
    did = f"; {entry['did']}" if entry.get("did") else ""
    return f"{indent}{entry.get('stage') or 'a fix'}: changed {files}{did} -> {entry.get('outcome') or '?'}"


def tried_before(root: str | Path | None, defect: Any, *, shown: Iterable[Any] = ()) -> str:
    """What a fixer of `defect` reads of earlier attempts at its cause, newest first; "" when none.

    `shown`: attempt records the fixer is already shown another way (`ledger.earlier_attempts`), not listed twice.
    """
    try:
        entries = _entries(root, defect)
        already = {_as_shown(a) for a in shown or () if isinstance(a, dict)}
        attempts = [e for e in entries if "outcome" in e]
        unshown = [e for e in attempts if _as_shown(e) not in already]
        hypothesis = next((e["hypothesis"] for e in reversed(entries) if e.get("hypothesis")), "")
        if not unshown and not hypothesis:
            return ""
        failed = sum(1 for e in attempts if _failed(e))
        lines = [HEADING, f"Attempts at this cause so far: {len(attempts)}, of which {failed} did not fix it. Do not "
                          "repeat a change that was measured failing; find what it missed.",
                 *(_attempt_line(e) for e in list(reversed(unshown))[:MOST_SHOWN])]
        if hypothesis:
            lines += [DIAGNOSIS, hypothesis]
        return "\n" + "\n".join(lines)[:MOST_CHARACTERS] + "\n"
    except Exception:  # noqa: BLE001
        return ""


def for_a_replan(root: str | Path | None, sprint: Any) -> str:
    """What the lead planning sprint `sprint` again reads: each of its causes that failed, newest first; "" if none."""
    try:
        causes = [
            cause for cause in (_read(root).get("causes") or {}).values()
            if isinstance(cause, dict) and cause.get("sprint") == sprint
            and any(_failed(e) for e in cause.get("entries") or [] if isinstance(e, dict))
        ]
        if not causes:
            return ""
        causes.sort(key=lambda c: str((c.get("entries") or [{}])[-1].get("at") or ""), reverse=True)
        parts = [LEAD_HEADING, "Plan around these: a work order that repeats a change measured failing will fail again."]
        for cause in causes[:MOST_CAUSES_FOR_THE_LEAD]:
            entries = [e for e in cause.get("entries") or [] if isinstance(e, dict)]
            failed = [e for e in entries if _failed(e)]
            parts.append(f"* {cause.get('defect') or 'a defect'} - did not get fixed {len(failed)} time(s):")
            parts.extend(_attempt_line(e, "  - ") for e in list(reversed(failed))[:3])
            hypothesis = next((e["hypothesis"] for e in reversed(entries) if e.get("hypothesis")), "")
            if hypothesis:
                parts.append(f"  - diagnosis: {hypothesis}")
        return "\n\n" + "\n".join(parts)[:MOST_CHARACTERS * 2] + "\n"
    except Exception:  # noqa: BLE001 - the plan request stands as it was
        return ""


def diagnosed(root: str | Path | None, defect: Any, failure: str, model: Any, *, sprint: Any = None) -> str:
    """When the switch is on and the cause has failed `DIAGNOSE_AFTER` times: one diagnosis-only call, its hypothesis
    kept in the journal and returned; "" otherwise. Never raises."""
    if not diagnosis_enabled() or model is None or not needs_a_diagnosis(root, defect):
        return ""
    try:
        from app.graph.localisation import diagnosis

        hypothesis = diagnosis(defect, failure, root, model, tried_before(root, defect))
        if hypothesis:
            add_hypothesis(root, defect, hypothesis, sprint=sprint)
            logger.info("Diagnosed a cause that failed %d times: %s", failures_on(root, defect), hypothesis[:200])
        return hypothesis
    except Exception:  # noqa: BLE001 - the fixer goes on without one
        logger.debug("Could not diagnose the recurring cause", exc_info=True)
        return ""


__all__ = [
    "DIAGNOSE_AFTER", "DIAGNOSIS", "FILE", "HEADING", "LEAD_HEADING", "ON_BY_DEFAULT", "add_hypothesis", "diagnosed",
    "diagnosis_enabled", "failures_on", "for_a_replan", "key_of", "needs_a_diagnosis", "record", "tried_before",
]
