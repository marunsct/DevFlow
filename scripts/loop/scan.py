"""The improvement scan: where this run spends far more than the recent runs did, per stage family.

Runs INSIDE the worker, where the transcripts live:

    docker compose exec -T worker python - <run-id> < scripts/loop/scan.py

or `loop.sh scan [run]` (default: the current run). Read at every audit with `loop.sh patterns`
(owner 2026-10-24: the owner does not read every result, so a number that is far out must be
reported as a suggestion even when nothing failed). One run is compared with the median of the
other runs that produced a real amount of output: tokens a call, the longest reply, minutes in
the stage family. It names what to look at; it decides nothing.
"""
from __future__ import annotations

import collections
import glob
import json
import os
import re
import statistics
import sys
from datetime import datetime

#: A family is flagged when its tokens a call pass the other runs' median by this factor ...
FACTOR = 2.0
#: ... and the calls are enough, and big enough, to mean something.
MOST_CALLS_BEFORE_ANYTHING = 3
SMALL_TOKENS_A_CALL = 4_000
LONG_REPLY = 40_000
LONG_STAGE_MINUTES = 10
#: Runs with less output than this teach nothing about a stage's size.
REAL_RUN_TOKENS = 50_000
BASELINE_RUNS = 5

#: Which planned change answers which family (docs/work-batching.md).
WHAT_TO_TRY = {
    "acceptance_author": "WB.2 acceptance suite in batches of criteria",
    "defect_fix": "WB.3 fewer defects shown to one fixer",
    "principal_architect": "WB.4 specification core and parts by size",
    "technical_lead": "WB.5 plan per milestone",
    "scrum_master": "WB.5 plan per milestone",
    "acceptance_review": "WB.6 review by file group",
    "architecture_review": "WB.6 review by file group",
}
GENERIC = "ask what in the request makes one call this big (work in it, context in it) before calling it the model's behaviour"


def _family(stage: str) -> str:
    name = str(stage or "-").split(":")[-1]
    for pattern, label in (
        (r"^defect_fix(_\d+_\d+)?$", "defect_fix"), (r"^test_round_\d+$", "test_round"),
        (r"^acceptance_author_\d+$", "acceptance_author"), (r"^acceptance_review_\d+$", "acceptance_review"),
        (r"^consult_.+$", "consult"), (r"^advice_review_.+$", "advice_review"), (r"^specialist_.+$", "specialist"),
        (r"^code_review_.+$", "code_review"), (r"^stack_setup_\d+$", "stack_setup"),
    ):
        if re.match(pattern, name):
            return label
    return name


def _when(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def measure(path: str) -> dict[str, dict]:
    """Per stage family in one transcript: calls, output tokens, the longest reply, minutes between first and last record."""
    found: dict[str, dict] = collections.defaultdict(lambda: {"calls": 0, "tokens": 0, "longest": 0, "first": None, "last": None})
    with open(path, errors="replace") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            label = _family(str(record.get("stage") or ""))
            entry = found[label]
            moment = _when(str(record.get("at") or ""))
            if moment is not None:
                entry["first"] = moment if entry["first"] is None else min(entry["first"], moment)
                entry["last"] = moment if entry["last"] is None else max(entry["last"], moment)
            if record.get("kind") == "model_response":
                out = int((record.get("usage") or {}).get("output_tokens") or 0)
                entry["calls"] += 1
                entry["tokens"] += out
                entry["longest"] = max(entry["longest"], out)
    for entry in found.values():
        spans = (entry["last"] - entry["first"]).total_seconds() / 60 if entry["first"] and entry["last"] else 0.0
        entry["minutes"] = round(spans, 1)
    return dict(found)


def scan(paths: list[str], run: str) -> list[str]:
    """The lines of the scan for `run` against the most recent other runs in `paths` (oldest first); [] when nothing is out."""
    target = next((p for p in paths if os.path.basename(p).startswith(run)), None)
    if target is None:
        return [f"no transcript for {run}"]
    mine = measure(target)
    others = []
    for path in paths:
        if path == target:
            continue
        measured = measure(path)
        if sum(v["tokens"] for v in measured.values()) >= REAL_RUN_TOKENS:
            others.append(measured)
    others = others[-BASELINE_RUNS:]
    lines = []
    for label, now in sorted(mine.items(), key=lambda kv: -kv[1]["tokens"]):
        if now["calls"] < MOST_CALLS_BEFORE_ANYTHING:
            continue
        per_call = now["tokens"] / now["calls"]
        before = [v["tokens"] / v["calls"] for v in (o.get(label) for o in others) if v and v["calls"]]
        usual = statistics.median(before) if before else None
        minutes_before = [v["minutes"] for v in (o.get(label) for o in others) if v and v["calls"]]
        usual_minutes = statistics.median(minutes_before) if minutes_before else None
        notes = []
        if usual and per_call >= SMALL_TOKENS_A_CALL and per_call > FACTOR * usual:
            notes.append(f"{per_call:,.0f} tokens a call against {usual:,.0f} in {len(before)} recent run(s)")
        if now["longest"] >= LONG_REPLY:
            notes.append(f"longest reply {now['longest']:,} tokens")
        if usual_minutes and now["minutes"] >= LONG_STAGE_MINUTES and now["minutes"] > FACTOR * usual_minutes:
            notes.append(f"{now['minutes']:.0f} min against {usual_minutes:.0f}")
        if notes:
            lines.append(f"IMPROVEMENT {label}: " + "; ".join(notes) + f" -> {WHAT_TO_TRY.get(label, GENERIC)}")
    return lines


def main(argv: list[str]) -> int:
    root = os.environ.get("DATA_DIR") or "/app/data"
    paths = sorted(glob.glob(os.path.join(root, "transcripts", "run-*.jsonl")), key=os.path.getmtime)
    run = argv[1] if len(argv) > 1 else ""
    if not run:
        print("name a run")
        return 2
    lines = scan(paths, run if run.startswith("run-") else "run-" + run)
    print("\n".join(lines) if lines else "nothing is far out against the recent runs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
