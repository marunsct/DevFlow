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
        (r"^acceptance_author_\d+(_g\d+|_fill)?$", "acceptance_author"), (r"^acceptance_review_\d+$", "acceptance_review"),
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


#: A ceiling is suggested when this share of replies, over this size, hold most of the output.
TAIL_OVER = 16_000
TAIL_SHARE_OF_REPLIES = 0.10
TAIL_SHARE_OF_OUTPUT = 0.5
SUGGESTED_CEILING = 24_000


def tail_of(path: str) -> list[int]:
    sizes = []
    with open(path, errors="replace") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get("kind") == "model_response":
                sizes.append(int((record.get("usage") or {}).get("output_tokens") or 0))
    return sizes


def ceiling_suggestion(sizes: list[int]) -> str:
    """A line naming a reply ceiling when a few long replies hold most of the output; "" when the tail is light."""
    total = sum(sizes)
    big = [size for size in sizes if size > TAIL_OVER]
    if len(sizes) < 20 or not big or total <= 0:
        return ""
    held = sum(big) / total
    if len(big) / len(sizes) < TAIL_SHARE_OF_REPLIES or held < TAIL_SHARE_OF_OUTPUT:
        return ""
    saved = sum(max(0, size - SUGGESTED_CEILING) for size in sizes) / total
    return (f"REPLY CEILING: {len(big)} of {len(sizes)} replies are over {TAIL_OVER:,} tokens and hold {held:.0%} of the "
            f"output; a ceiling of {SUGGESTED_CEILING:,} would trim about {saved:.0%} (reply salvage answers a cut-off "
            f"reply) -> `loop.sh ceiling {SUGGESTED_CEILING} \"<why>\"`, taken at the next segment start")


#: Files that are not the product: tests, configuration, manifests, documents, reports.
_NOT_PRODUCT = ("test", "spec", "acceptance", "e2e", "vitest", "jest", "config", "package", "readme", "docs/",
                ".json", "tsconfig", "stack-setup", "reports/", "test-results/")
_SOURCE = re.compile(r"\.(py|ts|tsx|js|jsx|mjs|go|rs|rb|java|php|sh)$")


def _who(stage: str) -> str:
    stage = str(stage or "")
    for prefix, label in (("stack_setup", "setup"), ("drafting", "drafting"), ("specialist", "builders"),
                          ("defect_fix", "fixers"), ("acceptance_author", "qa")):
        if stage.startswith(prefix):
            return label
    return "other"


def provenance(path: str) -> tuple[dict[str, int], dict[str, int]]:
    """Who wrote the product, and what defects were raised: (file writes by stage kind, defects by source).

    Drafting writes a file in one model call with no write tool, so its calls are counted as writes. A product
    written by the setup stage is not a product the build stages built, and a run's defects differ with it
    (docs/single-writer-review.md); this is the standing number for that comparison.
    """
    wrote: collections.Counter = collections.Counter()
    defects: collections.Counter = collections.Counter()
    seen: set = set()
    with open(path, errors="replace") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            kind = record.get("kind")
            if kind == "tool_call" and record.get("tool") in ("write_artifact", "edit_artifact", "replace_lines"):
                args = record.get("args") or {}
                name = str(args.get("relative_path") or args.get("file_path") or "").lower()
                if _SOURCE.search(name) and not any(mark in name for mark in _NOT_PRODUCT):
                    wrote[_who(record.get("stage"))] += 1
            elif kind == "model_response" and str(record.get("stage") or "").startswith("drafting"):
                wrote["drafting"] += 1
            elif kind == "defect" and record.get("event") == "raised":
                key = (record.get("sprint"), record.get("index"), str(record.get("description"))[:60])
                if key not in seen:
                    seen.add(key)
                    defects[str(record.get("source") or "unknown")] += 1
    return dict(wrote), dict(defects)


def provenance_line(wrote: dict[str, int], defects: dict[str, int]) -> str:
    built = ", ".join(f"{who} {n}" for who, n in sorted(wrote.items(), key=lambda kv: -kv[1])) or "no source written"
    raised = ", ".join(f"{source} {n}" for source, n in sorted(defects.items(), key=lambda kv: -kv[1])) or "none"
    return f"PRODUCT WRITTEN BY (writes/calls): {built}. DEFECTS RAISED {sum(defects.values())}: {raised}"


def main(argv: list[str]) -> int:
    root = os.environ.get("DATA_DIR") or "/app/data"
    paths = sorted(glob.glob(os.path.join(root, "transcripts", "run-*.jsonl")), key=os.path.getmtime)
    run = argv[1] if len(argv) > 1 else ""
    if not run:
        print("name a run")
        return 2
    lines = scan(paths, run if run.startswith("run-") else "run-" + run)
    mine = next((p for p in paths if os.path.basename(p).startswith(run if run.startswith("run-") else "run-" + run)), None)
    suggestion = ceiling_suggestion(tail_of(mine)) if mine else ""
    if suggestion:
        lines.append(suggestion)
    if mine:
        lines.append(provenance_line(*provenance(mine)))
    print("\n".join(lines) if lines else "nothing is far out against the recent runs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
