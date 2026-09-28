"""Run metrics reduced from the transcript, rather than from a second table.

Item 4 of `docs/harness-hardening-plan-part3.md`. Part I's §3.5 proposes a
`run_metrics` table holding tool calls by kind, failure rate, repeat rate and
latency. Every one of those numbers is already in
`DATA_DIR/transcripts/<run_id>.jsonl`, which is written post-middleware, never
raises, and is the one observability component in this repository that has
always worked.

Adding a table would give the harness two records of the same facts and no way
to tell which is right when they disagree - the two-copies-drift mistake the
codebase already made with run state, and paid for. So this reduces the record
that exists instead.

**On the refusal counts.** A refusal is the harness stopping something bad, and
counting it as a failure makes the number this exists to drive down rise
whenever a guard works. `scripts/audit_run.py` learned that the hard way: six
of run b0db10b1's eight "costly failures" were guards, and correcting the
classification moved it from 1.2% to 0.3%. The markers live in one place, here,
and the script reads them rather than keeping a second copy.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)

#: Message fragments that mark a refusal which prevented damage. Kept beside
#: the reduction that uses them, and checked against the text the tools really
#: emit - a fragment that silently stops matching moves calls from "prevented"
#: to "cost", which is the wrong direction for every conclusion drawn from it.
PREVENTED_DAMAGE = (
    "Node cannot parse",
    "Refusing to write",
    "Refusing to change",
    # "already been applied" was here until an edit already in the file stopped
    # being a failure at all. It is now a success - `already_applied` - so it
    # never reaches this classification, and a marker no tool emits would only
    # rot. See `_already_there` in `app.tools.repository`.
    "exactly as it is",
    "already contained exactly",
    "is a test, and tests are part of what",
    "already holds this module",
    "you have been told that twice",
    "so it is ambiguous which one",
    "it can execute arbitrary code",
    "Moving onto it would delete it",
    "Not running this again",
    "it runs until it is stopped",
    "installs system packages as root",
)


def _is_failure(content: str) -> bool:
    head = content[:400]
    return '"error"' in head or head.lstrip().startswith("Error:")


def _prevented(content: str) -> bool:
    return any(mark in content for mark in PREVENTED_DAMAGE)


def transcript_metrics(run_id: str) -> dict[str, Any]:
    """Reduce one run's transcript to the numbers an operator asks for.

    Returns zeros rather than raising for a run with no transcript: a stage-end
    hook that throws is worse than a metric that is missing, and transcripts can
    be switched off.
    """
    try:
        from app.observability.transcript import read_transcript

        rows = read_transcript(run_id)
    except Exception:  # noqa: BLE001 - a metric must never fail the run it measures
        logger.debug("Could not read the transcript for %s", run_id, exc_info=True)
        rows = []

    results = {r.get("call_id"): r for r in rows if r.get("kind") == "tool_result"}
    calls = [r for r in rows if r.get("kind") == "tool_call"]
    model_calls = sum(1 for r in rows if r.get("kind") == "model_request")

    by_tool: Counter[str] = Counter()
    prevented = failed = 0
    shapes: Counter[tuple[str, str]] = Counter()
    for call in calls:
        tool = str(call.get("tool") or "?")
        by_tool[tool] += 1
        content = str((results.get(call.get("call_id")) or {}).get("content") or "")
        if not _is_failure(content):
            continue
        if _prevented(content):
            prevented += 1
        else:
            failed += 1
            shapes[(tool, re.sub(r"\d+", "N", content[:110]))] += 1

    # A repeat is the same tool with the same arguments inside one stage.
    seen: Counter[tuple[Any, ...]] = Counter()
    for call in calls:
        seen[(call.get("stage"), call.get("tool"), repr(call.get("args")))] += 1
    repeats = sum(count - 1 for count in seen.values() if count > 1)

    stages = Counter(
        r.get("stage") for r in rows if r.get("kind") == "model_request"
    )
    return {
        "run_id": run_id,
        "model_calls": model_calls,
        "tool_calls": len(calls),
        "tool_calls_by_kind": dict(by_tool),
        "refusals_that_prevented_damage": prevented,
        "failures_that_cost_the_run": failed,
        "failure_rate": round(failed / len(calls), 4) if calls else 0.0,
        "identical_repeats_in_a_stage": repeats,
        "repeat_rate": round(repeats / model_calls, 4) if model_calls else 0.0,
        "stages": len(stages),
        "model_calls_by_stage": dict(stages),
        "costly_failure_shapes": [
            {"tool": tool, "shape": shape, "count": count}
            for (tool, shape), count in shapes.most_common(5)
        ],
    }


__all__ = ["PREVENTED_DAMAGE", "transcript_metrics"]
