"""One run's KPIs as JSON: the numbers every later change is measured against (Initiative W.4).

The audits print text for a person reading a check. A change claimed to cut
waste needs the same numbers for every run, in one shape, kept side by side -
`loop.sh kpi` writes this script's output to `data/kpi/<run>.json` and a row
of `data/kpi/ledger.csv` (`kpi_ledger.py`), and flags a KPI past 1.5x its
average over the five runs before.

Runs INSIDE the worker, where transcripts live, piped on stdin like
`audit_live.py`:

    docker compose exec -T worker python - <run-id> < scripts/loop/kpi.py

`kpis(records)` is the whole computation, so a test can hand it records.
"""
from __future__ import annotations

import collections
import glob
import json
import re
import sys
from datetime import datetime

FAIL = re.compile(r"^\s*(\[[^\]]*\]\s*)?(\{\"error\"|Error:|Refusing|Not running|Not looking)")
REDUNDANT = ("You have already read lines", "same bytes", "Refusing to read", "These are the same bytes",
             "is in the project memory at the start of this conversation")
READS = ("read_file", "read_repository_file")
INVALID_TOOL = "is not a valid tool"

#: Each guard layer's intervention, by the words it writes into a tool result
#: (Initiative V): how often each one acted on this run, side by side across
#: runs in the ledger. Its marginal value needs an A/B (`kpi_ledger.py compare`).
LAYERS = {
    "layer_memory_pointer": "is in the project memory at the start of this conversation",
    "layer_read_refused": "Refusing to read",
    "layer_read_held_back": "same bytes",
    "layer_edit_reindented": "Matched ignoring indentation",
    "layer_edit_reblanked": "Matched ignoring blank lines",
    "layer_write_unchanged": "already contained exactly this content",
    "layer_write_diagnostic": "IDE DIAGNOSTIC WARNING",
    "layer_command_refused": "is not permitted",
}


def _seconds(value: str) -> float:
    return datetime.fromisoformat(value).timestamp()


def _busy(intervals: list[tuple[float, float]]) -> float:
    total, end = 0.0, None
    for a, b in sorted(intervals):
        if end is None or a > end:
            total += b - a
            end = b
        elif b > end:
            total += b - end
            end = b
    return total


def _share(part: float, whole: float) -> float:
    return round(part / whole, 4) if whole else 0.0


def kpis(records: list[dict]) -> dict:
    """The run's KPIs from its transcript records."""
    times = [_seconds(r["at"]) for r in records if r.get("at")]
    calls: dict[str, dict] = {}
    seen_calls: collections.Counter = collections.Counter()
    opened: dict[str, float] = {}
    model_iv: list[tuple[float, float]] = []
    tokens = collections.Counter()
    count = collections.Counter()
    defects = collections.Counter()
    stages: list[str] = []
    offered: dict[str, set] = {}
    for r in records:
        stage, kind = r.get("stage") or "", r.get("kind")
        if stage and (not stages or stages[-1] != stage):
            stages.append(stage)
        if kind == "model_request":
            opened[stage] = _seconds(r["at"])
            # A tool withheld: this request offers fewer tools than the stage's
            # last. Its notice is in a correction message, not a tool result.
            tools = r.get("tools")
            tools = set(tools) if isinstance(tools, list) else set(re.findall(r"'([^']+)'", str(tools or "")))
            if stage in offered and tools and tools < offered[stage]:
                count["layer_tool_withheld"] += 1
            if tools:
                offered[stage] = tools
        elif kind == "model_response":
            count["model_calls"] += 1
            if stage in opened:
                model_iv.append((opened.pop(stage), _seconds(r["at"])))
            usage = r.get("usage") or {}
            tokens["input"] += usage.get("input_tokens") or 0
            tokens["output"] += usage.get("output_tokens") or 0
            tokens["cached"] += (usage.get("input_token_details") or {}).get("cache_read") or 0
            # Lost to reasoning, by the reply's shape: the server reports no
            # reasoning tokens, but a reply cut at its length with no call in it
            # is one.
            if r.get("finish_reason") == "length" and not r.get("tool_calls"):
                count["replies_lost_to_length"] += 1
        elif kind == "model_error":
            count["model_errors"] += 1
        elif kind == "resumed":
            count["resumes"] += 1
        elif kind == "tool_call":
            count["tool_calls"] += 1
            calls[r.get("call_id")] = r
            if r.get("tool") in READS:
                count["reads"] += 1
            # Keyed by the stage visit, so a later visit asking again is not a repeat.
            r = {**r, "_visit": len(stages)}
            calls[r.get("call_id")] = r
        elif kind == "tool_result":
            call = calls.get(r.get("call_id")) or {}
            raw = r.get("result") or r.get("content") or ""
            text = raw if isinstance(raw, str) else json.dumps(raw)
            if (isinstance(raw, dict) and raw.get("error")) or (isinstance(raw, str) and FAIL.match(raw)):
                count["tool_failures"] += 1
            if call.get("tool") in READS and any(m in text[:600] for m in REDUNDANT):
                count["redundant_reads"] += 1
            if INVALID_TOOL in text[:400]:
                count["unknown_tool_names"] += 1
            for layer, marker in LAYERS.items():
                if marker in text[:1500]:
                    count[layer] += 1
            # A repeat is the same call answered the same way in one visit:
            # re-asking what was already answered (`scripts/audit_run.py`).
            # Refusals and notices are the guards working, counted above.
            if call and not text.lstrip().startswith(("Refusing", "Error: Refusing")) and not any(
                m in text[:600] for m in REDUNDANT
            ):
                seen_calls[(call["_visit"], call.get("tool"), json.dumps(call.get("args") or {}, sort_keys=True), text)] += 1
        elif kind == "defect":
            defects[str(r.get("event") or "")] += 1
    wall = (max(times) - min(times)) if times else 0.0
    model_busy = _busy(model_iv)
    return {
        "wall_minutes": round(wall / 60, 1),
        "model_busy_share": _share(model_busy, wall),
        "model_calls": count["model_calls"],
        "model_errors": count["model_errors"],
        "resumes": count["resumes"],
        "input_tokens": tokens["input"],
        "output_tokens": tokens["output"],
        "prefill_decode_ratio": round(tokens["input"] / tokens["output"], 1) if tokens["output"] else 0.0,
        "cached_token_share": _share(tokens["cached"], tokens["input"]),
        "replies_lost_to_length": count["replies_lost_to_length"],
        "tool_calls": count["tool_calls"],
        "tool_failure_rate": _share(count["tool_failures"], count["tool_calls"]),
        "redundant_read_rate": _share(count["redundant_reads"], count["reads"]),
        "identical_call_rate": _share(sum(n - 1 for n in seen_calls.values()), count["tool_calls"]),
        "unknown_tool_name_rate": _share(count["unknown_tool_names"], count["tool_calls"]),
        "test_rounds": sum(1 for s in stages if s.startswith("test_round")),
        "defect_fix_stages": len({s for s in stages if s.startswith("defect_fix")}),
        "lead_plans": sum(1 for s in stages if s == "technical_lead"),
        "defects_raised": defects["raised"],
        "defects_fixed": defects["fixed"],
        "defects_left_open": defects["left open"],
        "fixes_reverted": defects["reverted"],
        "closed_without_a_fixer": defects["closed without a fixer"],
        **{layer: count[layer] for layer in [*LAYERS, "layer_tool_withheld"]},
    }


def main(run: str) -> int:
    paths = sorted(glob.glob(f"/app/data/transcripts/{run}*.jsonl"))
    if not paths:
        print(json.dumps({"run": run, "error": "no transcript"}))
        return 1
    records = []
    for line in open(paths[0], errors="replace"):
        try:
            records.append(json.loads(line))
        except ValueError:
            continue
    print(json.dumps({"run": run, **kpis(records)}))
    return 0


if __name__ == "__main__" and len(sys.argv) > 1:
    raise SystemExit(main(sys.argv[1]))
