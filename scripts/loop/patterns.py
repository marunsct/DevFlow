"""Patterns across every run's transcript, not only the live one: where replies run out, what recurs.

Runs INSIDE the worker, where the transcripts live:

    docker compose exec -T worker python - [since] < scripts/loop/patterns.py

or `loop.sh patterns [since]` (default: the last three days). The 10-minute
audit reads the live run; a finding that needs many runs - a fixer handed four
defects fixing a quarter as often as one handed one, a stage whose replies run
out on every model - shows only across all of them. Each deep analysis reads
this as well (owner 2026-10-21: "check whether any such findings were missed").
"""
from __future__ import annotations

import collections
import glob
import json
import os
import re
import statistics
import sys
import zlib
from datetime import datetime, timedelta, timezone

_FAMILIES = (
    (r"^defect_fix(_\d+_\d+)?$", "defect_fix"), (r"^test_round_\d+$", "test_round"),
    (r"^acceptance_author_\d+$", "acceptance_author"), (r"^acceptance_review_\d+$", "acceptance_review"),
    (r"^consult_.+$", "consult"), (r"^advice_review_.+$", "advice_review"), (r"^specialist_.+$", "specialist"),
    (r"^code_review_.+$", "code_review"), (r"^stack_setup_\d+$", "stack_setup"),
)
_MASK = ((re.compile(r"/[\w./-]+"), "<path>"), (re.compile(r"'[^']{0,80}'"), "'X'"), (re.compile(r"\d+"), "N"))


def family(stage: str) -> str:
    name = str(stage or "-").split(":")[-1]
    for pattern, label in _FAMILIES:
        if re.match(pattern, name):
            return label
    return name


def looping(text: str) -> bool:
    tail = text[-8000:].encode("utf-8", "replace")
    return len(tail) >= 2000 and len(zlib.compress(tail)) * 12 < len(tail)


def signature(text: str) -> str:
    out = str(text or "")[:160]
    for pattern, replacement in _MASK:
        out = pattern.sub(replacement, out)
    return out[:100]


def _failed(result: dict) -> tuple[bool, str]:
    content = result.get("content")
    text = content if isinstance(content, str) else json.dumps(content, default=str)
    failed = str(result.get("status") or "") == "error" or bool(result.get("raised")) \
        or bool(re.match(r'^\s*(\{"error"|Error:|Refus|Not )', text or ""))
    return failed, text or ""


def analyse(paths: list[str], since: str) -> dict:
    """Reply health per stage family, fix outcome per bundle size, and the failures that recur since `since`."""
    replies: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    sizes: dict[str, list[int]] = collections.defaultdict(list)
    fixes: list[dict] = []
    recurring: dict[tuple, dict] = {}
    for path in paths:
        run = os.path.basename(path)[:12]
        calls: dict = {}
        bundled: collections.Counter = collections.Counter()
        outcome: dict = {}
        tokens: collections.Counter = collections.Counter()
        cut: collections.Counter = collections.Counter()
        with open(path, errors="replace") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                kind, stage = record.get("kind"), str(record.get("stage") or "")
                at = str(record.get("at") or "")
                if kind == "model_response" and at >= since:
                    label, text = family(stage), str(record.get("text") or "")
                    out = int((record.get("usage") or {}).get("output_tokens") or 0)
                    counts = replies[label]
                    counts["replies"] += 1
                    sizes[label].append(out)
                    if record.get("finish_reason") == "length":
                        counts["cut"] += 1
                        if text.strip():
                            counts["cut_with_text"] += 1
                            counts["looping"] += looping(text)
                        elif not record.get("tool_calls"):
                            counts["all_reasoning"] += 1
                if kind == "model_response" and stage.startswith("defect_fix_"):
                    tokens[stage] += int((record.get("usage") or {}).get("output_tokens") or 0)
                    cut[stage] += record.get("finish_reason") == "length"
                elif kind == "defect" and stage.startswith("defect_fix_"):
                    event = record.get("event")
                    if event == "bundled":
                        bundled[stage] += 1
                    elif event in ("fixed", "left open", "reverted"):
                        match = re.match(r"defect_fix_\d+_(\d+)$", stage)
                        if match and str(record.get("index")) == match.group(1):
                            outcome[stage] = event
                elif kind == "tool_call":
                    calls[record.get("call_id")] = record.get("tool")
                elif kind == "tool_result" and at >= since:
                    failed, text = _failed(record)
                    if failed:
                        key = (calls.get(record.get("call_id"), record.get("tool")), signature(text))
                        entry = recurring.setdefault(key, {"n": 0, "runs": set(), "last": ""})
                        entry["n"] += 1
                        entry["runs"].add(run)
                        entry["last"] = max(entry["last"], at)
        for stage, event in outcome.items():
            fixes.append({"bundle": 1 + bundled[stage], "fixed": event == "fixed", "tokens": tokens[stage],
                          "cut": cut[stage] > 0})

    def pct(values: list[int], q: float) -> int:
        values = sorted(values)
        return values[min(len(values) - 1, int(q * len(values)))] if values else 0

    families = sorted(
        ({"family": label, **counts, "out_p50": pct(sizes[label], .5), "out_p90": pct(sizes[label], .9)}
         for label, counts in replies.items()),
        key=lambda row: -row.get("cut", 0),
    )
    bundles = []
    for label, test in (("1", lambda b: b == 1), ("2-3", lambda b: 2 <= b <= 3), ("4+", lambda b: b >= 4)):
        rows = [f for f in fixes if test(f["bundle"])]
        if rows:
            bundles.append({"bundle": label, "stages": len(rows),
                            "fixed_share": round(sum(r["fixed"] for r in rows) / len(rows), 3),
                            "median_tokens": statistics.median(r["tokens"] for r in rows),
                            "cut_share": round(sum(r["cut"] for r in rows) / len(rows), 3)})
    failures = sorted(
        ({"tool": tool, "signature": sig, "n": e["n"], "runs": len(e["runs"]), "last": e["last"][:16]}
         for (tool, sig), e in recurring.items()),
        key=lambda row: (-row["runs"], -row["n"]),
    )[:25]
    return {"since": since, "runs": len(paths), "families": families, "bundles": bundles, "failures": failures}


def main(argv: list[str]) -> int:
    since = argv[1] if len(argv) > 1 else (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%d")
    paths = sorted(glob.glob("/app/data/transcripts/*.jsonl"))
    report = analyse(paths, since)
    print(f"{report['runs']} transcripts; replies and failures since {since}\n")
    print(f"{'family':24} {'replies':>7} {'cut':>5} {'text':>5} {'loop':>5} {'allR':>5} {'p50':>6} {'p90':>6}")
    for row in report["families"]:
        if row.get("replies", 0) >= 5:
            print(f"{row['family'][:24]:24} {row['replies']:>7} {row.get('cut', 0):>5} {row.get('cut_with_text', 0):>5} "
                  f"{row.get('looping', 0):>5} {row.get('all_reasoning', 0):>5} {row['out_p50']:>6} {row['out_p90']:>6}")
    print("\nfix outcome by defects shown to one fixer (all runs):")
    for row in report["bundles"]:
        print(f"  {row['bundle']:>3}: {row['stages']:>4} stages, fixed {row['fixed_share']:.0%}, "
              f"median {row['median_tokens']:,.0f} output tokens, cut off {row['cut_share']:.0%}")
    print("\nfailures recurring across runs:")
    for row in report["failures"]:
        print(f"  {row['runs']:>3} runs {row['n']:>4}x {str(row['tool'])[:20]:20} {row['signature'][:90]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
