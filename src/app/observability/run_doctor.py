"""The run doctor: a read-only account of one run and what to do next, from its records (deep review 2026-11-18, F1).

A customer install has no operator auditing every ten minutes with the loop's scripts (`loop.sh audit`, `defects`),
which read the run's transcript inside the worker. This reads the same records the same way - the live branch of the
transcript (`run_kpis.live_branch`), its stages (`stage_usage`) and its `defect` records (`defect_ledger`) - and says:
the stages in the order they ran and the time each took, the defects raised, fixed, left open and reverted, the
defects raised again round after round, the commands refused for want of memory or disk, the model errors and the
restarts, and the harness's own mechanisms that did not run (`degraded`); then the actions that fit (resume with a
direction, rewind to a stage, check the model server or the machine). Nothing here acts or calls a model.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

#: A tool result refused for want of memory or disk on the machine running the commands.
_RESOURCE_REFUSAL = re.compile(
    r"Not enough memory is free|No space left on device|ENOSPC|disk is full|Cannot allocate memory", re.IGNORECASE)
#: How the defect ledger's events end a defect's attempt.
_OUTCOMES = ("fixed", "left open", "unverified", "reverted", "closed", "closed without a fixer", "deferred")
#: A defect raised in at least this many rounds without being fixed is going round in circles.
REPEATED_ROUNDS = 3
#: Model errors past which the model server is the first thing to check.
MANY_MODEL_ERRORS = 5
#: A running run with no record for this long has stalled, or waits on something.
QUIET_MINUTES = 30
#: How many stage switches the order shows, the latest last.
ORDER_SHOWN = 20


def _when(record: dict) -> datetime | None:
    try:
        found = datetime.fromisoformat(str(record.get("at")))
    except (TypeError, ValueError):
        return None
    return found if found.tzinfo else found.replace(tzinfo=timezone.utc)


def _text(value: Any) -> str:
    return value if isinstance(value, str) else str(value or "")


def stage_order(records: Iterable[dict]) -> list[str]:
    """The stages in the order the run moved through them, a stage repeated only when the run came back to it."""
    order: list[str] = []
    for record in records:
        stage = str(record.get("stage") or "")
        if stage and (not order or order[-1] != stage):
            order.append(stage)
    return order


def defects(records: Iterable[dict]) -> dict[str, Any]:
    """The defect ledger's events summed: raised, and how each attempt ended; and the defects raised round after round."""
    events = [r for r in records if r.get("kind") == "defect"]
    counted = Counter(str(e.get("event") or "") for e in events)
    by_id: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        if event.get("defect_id"):
            by_id[str(event["defect_id"])].append(event)
    repeated = []
    for defect_id, its in by_id.items():
        rounds = sorted({e.get("round") for e in its if e.get("event") == "raised" and isinstance(e.get("round"), int)})
        outcomes = [str(e.get("event")) for e in its if e.get("event") in _OUTCOMES]
        ending = outcomes[-1] if outcomes else "open"
        if len(rounds) >= REPEATED_ROUNDS and ending != "fixed":
            first = next((e for e in its if e.get("event") == "raised"), its[0])
            repeated.append({"id": defect_id, "rounds": len(rounds), "ending": ending,
                             "description": " ".join(_text(first.get("description")).split())[:300],
                             "first_stage": str(first.get("stage") or "")})
    repeated.sort(key=lambda d: -d["rounds"])
    return {"raised": counted["raised"], "fixed": counted["fixed"], "left_open": counted["left open"],
            "unverified": counted["unverified"],
            "reverted": counted["reverted"], "closed": counted["closed"] + counted["closed without a fixer"],
            "deferred": counted["deferred"], "repeated": repeated}


def degraded_mechanisms(records: Iterable[dict]) -> list[dict[str, Any]]:
    """Each mechanism that did not run (`degraded` records), most often first: how often, where, and its last error."""
    by_name: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        if record.get("kind") == "degraded" and record.get("mechanism"):
            by_name[str(record["mechanism"])].append(record)
    found = []
    for name, its in by_name.items():
        last = its[-1]
        found.append({"mechanism": name, "count": len(its),
                      "stages": sorted({str(r.get("stage") or "") for r in its} - {""}),
                      "last_error": (f"{last.get('error_type')}: " if last.get("error_type") else "")
                      + _text(last.get("message"))[:200]})
    found.sort(key=lambda d: (-d["count"], d["mechanism"]))
    return found


def diagnose(records: list[dict], *, status: str = "", current_stage: str = "", error: str = "",
             now: datetime | None = None) -> dict[str, Any]:
    """The doctor's account of a run from its transcript records, with the next actions that fit."""
    from app.observability.run_kpis import live_branch
    from app.observability.stage_usage import stage_usage

    live = live_branch(list(records))
    stages = stage_usage(live)
    order = stage_order(live)
    found = defects(live)
    refusals = [r for r in live if r.get("kind") == "tool_result" and _RESOURCE_REFUSAL.search(_text(r.get("content"))[:2000])]
    model_errors = sum(1 for r in live if r.get("kind") == "model_error")
    restarts = sum(1 for r in live if r.get("kind") == "resumed")
    rewinds = sum(1 for r in records if r.get("kind") == "rewound")
    last = max((at for at in (_when(r) for r in live) if at is not None), default=None)
    now = now or datetime.now(timezone.utc)
    quiet_minutes = round((now - last).total_seconds() / 60) if last is not None else None
    total = sum(float(s.get("wall_seconds") or 0) for s in stages) or 0.0

    suggestions: list[dict[str, str]] = []
    if status == "running" and quiet_minutes is not None and quiet_minutes >= QUIET_MINUTES:
        suggestions.append({"action": "check_the_worker", "said": (
            f"Nothing was recorded for {quiet_minutes} minutes while the run reads as running: check that the worker "
            "and the model server are up (the health page says), then pause and resume the run if it does not move.")})
    if model_errors >= MANY_MODEL_ERRORS:
        suggestions.append({"action": "check_the_model", "said": (
            f"The model answered with an error {model_errors} times: check the model server on the health page and "
            "in Settings before resuming.")})
    if refusals:
        suggestions.append({"action": "free_resources", "said": (
            f"{len(refusals)} command(s) were refused for want of memory or disk: free space or memory on the "
            "machine that runs the workers (or let fewer runs share it), then resume.")})
    for defect in found["repeated"][:2]:
        suggestions.append({"action": "resume_with_direction", "said": (
            f"A defect came back in {defect['rounds']} test rounds and ended {defect['ending']}: "
            f"\"{defect['description'][:160]}\". Resume with a direction that says how it should be fixed.")})
    if found["repeated"] and "technical_lead" in order:
        suggestions.append({"action": "rewind", "stage": "technical_lead", "said": (
            "Defects going round in circles are often a plan problem: rewind to the sprint's planning and resume "
            "with a direction for the plan.")})
    if status in ("failed", "cancelled", "paused", "waiting_for_budget") and not any(
            s["action"] == "resume_with_direction" for s in suggestions):
        suggestions.append({"action": "resume_with_direction", "said": (
            "The run stopped" + (f": {error[:200]}" if error else "") + ". Resume it, with a direction if you know "
            "what it should do differently, or rewind to the stage where it went wrong.")})
    degraded = degraded_mechanisms(live)
    if degraded:
        named = ", ".join(f"{d['mechanism']} ({d['count']})" for d in degraded[:5])
        suggestions.append({"action": "report_degraded", "said": (
            f"{len(degraded)} of the harness's own mechanisms did not run as built: {named}. The run went on "
            "without them; send the diagnostic bundle with the run so they can be looked at.")})
    if not suggestions:
        suggestions.append({"action": "none", "said": "Nothing in the run's records calls for an action now."})

    return {
        "status": status,
        "current_stage": current_stage,
        "records": len(live),
        "last_record_minutes_ago": quiet_minutes,
        "stage_order": order[-ORDER_SHOWN:],
        "stage_switches": max(0, len(order) - 1),
        "stages": [{"stage": s["stage"], "wall_seconds": s["wall_seconds"], "model_calls": s["model_calls"],
                    "tool_failures": s["tool_failures"],
                    "share": round(float(s["wall_seconds"] or 0) / total, 3) if total else 0.0} for s in stages],
        "defects": found,
        "resource_refusals": len(refusals),
        "model_errors": model_errors,
        "restarts": restarts,
        "rewinds": rewinds,
        "degraded": degraded,
        "suggestions": suggestions,
    }


__all__ = ["degraded_mechanisms", "diagnose", "defects", "stage_order"]
