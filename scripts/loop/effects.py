"""What each fix and switch did in one run, read from the run's own records (owner, 2026-10-22: review how effective our changes are).

    docker compose exec -T worker python - <run> < scripts/loop/effects.py

or `loop.sh effects [run]`. Read-only. For every change with a signal it leaves
in the transcript or the workspace, one line: how often it fired, and what it
saved or cost where that can be counted. A line reading "not reached" is a
change the run has not given a chance to act yet.
"""
from __future__ import annotations

import glob
import json
import re
import sys
from collections import Counter
from pathlib import Path

#: (label, where the signal lives, the text that marks it).
#: "request" - a model request's messages; "result" - a tool result;
#: "decision" - the decision log; "ledger" - a defect record's detail.
SIGNALS: list[tuple[str, str, str]] = [
    ("LF.191 approved lessons shown", "request", "LESSONS FROM EARLIER RUNS"),
    ("LF.188 a file given twice (should stay 0)", "request", "as they stood when this stage started"),
    ("IN.1 assumed answers handed to the architect", "request", "Open questions, answered"),
    ("CM.1 shared facts in a request", "request", "The facts this work is built and judged under"),
    ("PH.1 where things stand", "request", "Where things stand"),
    ("LF.203 the lead told why a release was held", "request", "Why the release was held back"),
    ("LF.186 where dependencies go", "request", "Declare every"),
    ("AY.1 a defect localised by one cheap call before its rewrite", "request", "You find where in a codebase a failure is caused"),
    ("AY.3 a write followed by the defect's tests - passing", "result", "they pass now. Your defect is fixed"),
    ("AY.3 a write followed by the defect's tests - still failing", "result", "after the write: they still fail"),
    ("PX.2/LF.197 a withheld tool refused", "result", "is withheld at this point of the stage"),
    ("LF.174 a re-run refused, nothing changed", "result", "nothing has been written since"),
    ("LF.202 a criterion moved to where its test can pass", "decision", "where a test of it can first pass"),
    ("AY.4 a defect left open at its call cap", "ledger", "model calls across its attempts"),
    ("LF.185 unstable criterion held as a dispute", "ledger", "pass when they run alone"),
]


def _text(value) -> str:
    return value if isinstance(value, str) else json.dumps(value, default=str)


def _lost(record: dict, usage: dict) -> bool:
    """A reply cut off at the cap with nothing in it - `run_kpis`' rule; by size alone only when its end is not recorded.

    By size alone a long reply that answered was lost: one architect's
    specification came back whole, as its tool call, at 33,613 tokens.
    """
    finish = record.get("finish_reason")
    if finish:
        answered = bool(str(record.get("text") or "").strip()) or record.get("tool_calls") not in (None, "", "[]", [])
        return finish == "length" and not answered
    return int(usage.get("output_tokens") or 0) >= 32_000


def effects(records: list[dict], decisions: str = "") -> list[str]:
    """The report's lines for these transcript records and this decision log."""
    counts: Counter = Counter()
    lost = lost_minutes = 0.0
    defects: Counter = Counter()
    salvaged: Counter = Counter()
    for record in records:
        if not isinstance(record, dict):
            continue
        kind = record.get("kind")
        if kind == "model_request":
            text = _text(record.get("messages"))
            for label, where, needle in SIGNALS:
                if where == "request" and needle in text:
                    counts[label] += 1
        elif kind == "tool_result":
            text = _text(record.get("content") or record.get("result") or record.get("output"))
            for label, where, needle in SIGNALS:
                if where == "result" and needle in text:
                    counts[label] += 1
        elif kind == "model_response":
            usage = record.get("usage") if isinstance(record.get("usage"), dict) else {}
            if record.get("salvaged"):
                # RS.1: its usage counts the cut-off reply too, so it is past
                # the cap, but it was answered (`app.models.reply_salvage`).
                salvaged[str(record["salvaged"])] += 1
            elif _lost(record, usage):
                lost += 1
        elif kind == "defect":
            defects[str(record.get("event") or "")] += 1
            detail = _text(record.get("detail"))
            for label, where, needle in SIGNALS:
                if where == "ledger" and needle in detail:
                    counts[label] += 1
    for label, where, needle in SIGNALS:
        if where == "decision":
            counts[label] += decisions.count(needle)
    lines = [f"  {counts[label]:>4}  {label}" if counts[label] else f"     -  {label}: not reached"
             for label, _, _ in SIGNALS]
    lines.append(f"  {int(lost):>4}  replies lost to the output cap (the cost the reasoning work targets)")
    lines.append(f"  {salvaged['reasoning']:>4}  RS.1 replies cut off while reasoning, answered from their reasoning")
    lines.append(f"  {salvaged['continuation']:>4}  RS.1 replies cut off part way through their text, continued")
    if defects:
        lines.append("  defects: " + ", ".join(f"{event} {n}" for event, n in sorted(defects.items())))
    return lines


def order_probe_line(probed: dict) -> str:
    """What the order probe recorded (`ORDER_PROBE`), to read beside the unstable disputes the signals above count."""
    return (f"  {len(probed.get('unstable') or []):>4}  tests failing only when their file runs alone "
            f"({probed.get('files_run', 0)} files probed, {probed.get('files_without_a_report', 0)} without a report)")


def main(run: str) -> None:
    paths = sorted(glob.glob(f"/app/data/transcripts/{run}*.jsonl"))
    if not paths:
        print("no transcript yet")
        return
    records = []
    for line in open(paths[0], errors="replace"):
        try:
            records.append(json.loads(line))
        except ValueError:
            continue
    decisions = ""
    for log in glob.glob(f"/app/data/workspaces/*/workspace-{run}*/docs/decision_log.md"):
        decisions = Path(log).read_text(encoding="utf-8", errors="replace")
    print(f"effects of the changes in {run} ({len(records)} records)")
    print("\n".join(effects(records, decisions)))
    for probed in glob.glob(f"/app/data/workspaces/*/workspace-{run}*/.harness/order_probe.json"):
        print(order_probe_line(json.loads(Path(probed).read_text(encoding="utf-8"))))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
