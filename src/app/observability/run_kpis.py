"""One run's KPIs from its transcript records: the numbers every later change is measured against (Initiative W.4).

Moved here from `scripts/loop/kpi.py` unchanged, so the API can answer a run's
KPIs for the run page (plan UI-S6) and the loop's script keeps producing the
same numbers for `data/kpi/` and the ledger: it imports this module.
`kpis(records)` is the whole computation.
"""
from __future__ import annotations

import collections
import json
import re
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


#: How much of a tool result's start and end is searched for a guard's words. The
#: harness appends its notes after the content, so the start alone misses them
#: (Initiative AN).
HEAD_CHARS = 600
TAIL_CHARS = 900

#: A gap between two records longer than this is a worker stopped between them
#: (a deploy, a crash), not work.
ORPHAN_GAP_SECONDS = 600


def _ends(text: str) -> str:
    """The start and the end of a tool result: where a guard's words are."""
    return text if len(text) <= HEAD_CHARS + TAIL_CHARS else text[:HEAD_CHARS] + "\n" + text[-TAIL_CHARS:]


#: What each stage's block carries.
STAGE_COUNTERS = ("calls", "input", "cached", "output", "identical_calls", "redundant_reads", "lost_replies", "tool_failures")


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


def live_branch(records: list[dict]) -> list[dict]:
    """The records of the run as it stands: the work each rewind discarded left out.

    A rewind (`loop.sh rewind`, owner 2026-10-20) takes a run back to the start
    of a stage and runs it on from there; the transcript keeps what the
    abandoned branch did. Measured whole, a rewound run counts that work twice.
    Each `rewound` record names the moment it went back to: what was recorded
    between that moment and the rewind is left out.
    """
    cuts = [(_seconds(r["point_at"]), _seconds(r["at"])) for r in records
            if r.get("kind") == "rewound" and r.get("point_at") and r.get("at")]
    if not cuts:
        return records
    return [
        r for r in records
        if r.get("kind") == "rewound" or not r.get("at")
        or not any(start <= _seconds(r["at"]) < end for start, end in cuts)
    ]


def discarded_seconds(records: list[dict]) -> float:
    """How much of the run's span the rewinds discarded: from each point gone back to, to the rewind.

    The records left (`live_branch`) still span that time - the first is before
    it, the last after - so a wall clock read off them counted the abandoned
    branch's hours as the run's own. Overlapping rewinds are counted once.
    """
    cuts = sorted((_seconds(r["point_at"]), _seconds(r["at"])) for r in records
                  if r.get("kind") == "rewound" and r.get("point_at") and r.get("at"))
    total, reach = 0.0, float("-inf")
    for start, end in cuts:
        start = max(start, reach)
        if end > start:
            total += end - start
        reach = max(reach, end)
    return total



def _calls_shown_lessons(records: list[dict]) -> int:
    """Model requests whose messages carried the lessons block (`plugins.lessons.FRAME`)."""
    try:
        from app.plugins.lessons import FRAME
    except Exception:  # noqa: BLE001
        return 0
    return sum(1 for r in records if r.get("kind") == "model_request" and FRAME in json.dumps(r.get("messages") or ""))

def _the_prefix_breaks(records: list[dict]) -> dict:
    """Why calls missed the cached prefix, and the uncached input tokens behind each reason (plan PX.1)."""
    from app.observability.prefix_breaks import REASONS, breaks

    found = breaks(records)
    return {
        **{f"prefix_break_{why}": found["calls_by_reason"].get(why, 0) for why in REASONS},
        **{f"uncached_tokens_{why}": found["uncached_tokens_by_reason"].get(why, 0) for why in REASONS},
    }


def _the_screenshot_rubric(records: list[dict]) -> float | None:
    """The page's checklist score at release (plan EV.2), or None."""
    from app.acceptance.screenshot_rubric import from_records

    return from_records(records)


def kpis(records: list[dict]) -> dict:
    """The run's KPIs from its transcript records, as the run stands (see `live_branch`)."""
    rewinds = sum(1 for r in records if r.get("kind") == "rewound")
    discarded = discarded_seconds(records)
    records = live_branch(records)
    times = [_seconds(r["at"]) for r in records if r.get("at")]
    calls: dict[str, dict] = {}
    seen_calls: collections.Counter = collections.Counter()
    opened: dict[str, list[float]] = {}
    model_iv: list[tuple[float, float]] = []
    tokens = collections.Counter()
    count = collections.Counter()
    defects = collections.Counter()
    stages: list[str] = []
    per_stage: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    offered: dict[str, set] = {}
    extra = collections.Counter()
    # What requests carried, by block (Initiative BF), and whether a request's
    # tools differ from the stage's previous one - a changed tool list moves the
    # prompt's prefix, and the server has to read it again.
    blocks = collections.Counter()
    tools_changed: dict[str, bool] = {}
    calls_by_tool: collections.Counter = collections.Counter()
    failed_by_tool: collections.Counter = collections.Counter()
    for r in records:
        stage, kind = r.get("stage") or "", r.get("kind")
        if stage and (not stages or stages[-1] != stage):
            stages.append(stage)
        if kind == "model_request":
            # Oldest first: a stage asks several at once (see `run_timing`).
            opened.setdefault(stage, []).append(_seconds(r["at"]))
            # A tool withheld: this request offers fewer tools than the stage's
            # last. Its notice is in a correction message, not a tool result.
            tools = r.get("tools")
            tools = set(tools) if isinstance(tools, list) else set(re.findall(r"'([^']+)'", str(tools or "")))
            if stage in offered and tools and tools < offered[stage]:
                count["layer_tool_withheld"] += 1
            tools_changed[stage] = bool(stage in offered and tools and tools != offered[stage])
            if tools:
                offered[stage] = tools
            for name, size in (r.get("blocks") or {}).items():
                if isinstance(size, (int, float)):
                    blocks[name] += int(size)
        elif kind == "model_response":
            count["model_calls"] += 1
            if opened.get(stage):
                model_iv.append((opened[stage].pop(0), _seconds(r["at"])))
            usage = r.get("usage") or {}
            output = usage.get("output_tokens") or 0
            cached = (usage.get("input_token_details") or {}).get("cache_read") or 0
            tokens["input"] += usage.get("input_tokens") or 0
            tokens["output"] += output
            tokens["cached"] += cached
            row = per_stage[stage]
            row["calls"] += 1
            row["input"] += usage.get("input_tokens") or 0
            row["cached"] += cached
            row["output"] += output
            if tools_changed.pop(stage, False) and cached < 0.5 * (usage.get("input_tokens") or 0):
                count["cache_miss_after_tool_change"] += 1
            # What the server does not report: the reasoning's length, kept by
            # the transcript since 2026-10-18, at about four characters a token.
            extra["reasoning_tokens_estimated"] += min(output, int(r.get("reasoning_chars") or 0) // 4)
            extra["invalid_tool_calls"] += len(r.get("invalid_tool_calls") or [])
            # Lost to reasoning, by the reply's shape: the server reports no
            # reasoning tokens, but a reply cut at its length with no call in it
            # is one.
            if r.get("finish_reason") == "length" and not r.get("tool_calls"):
                count["replies_lost_to_length"] += 1
                extra["output_lost"] += output
                row["lost_replies"] += 1
        elif kind == "model_error":
            count["model_errors"] += 1
        elif kind == "resumed":
            count["resumes"] += 1
        elif kind == "steering_applied":
            count["steering_notes"] += 1
        elif kind in ("server_changed", "server_unreachable"):
            count[kind] += 1
        elif kind == "tool_call":
            count["tool_calls"] += 1
            calls_by_tool[str(r.get("tool") or "?")] += 1
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
            ends = _ends(text)
            if (isinstance(raw, dict) and raw.get("error")) or (isinstance(raw, str) and FAIL.match(raw)):
                count["tool_failures"] += 1
                per_stage[stage]["tool_failures"] += 1
                failed_by_tool[str(call.get("tool") or "?")] += 1
            if call.get("tool") in READS and any(m in ends for m in REDUNDANT):
                count["redundant_reads"] += 1
                per_stage[stage]["redundant_reads"] += 1
            if INVALID_TOOL in ends:
                count["unknown_tool_names"] += 1
            for layer, marker in LAYERS.items():
                if marker in ends:
                    count[layer] += 1
            # A repeat is the same call answered the same way in one visit:
            # re-asking what was already answered (`scripts/audit_run.py`).
            # Refusals and notices are the guards working, counted above.
            if call and not text.lstrip().startswith(("Refusing", "Error: Refusing")) and not any(
                m in ends for m in REDUNDANT
            ):
                key = (call["_visit"], call.get("tool"), json.dumps(call.get("args") or {}, sort_keys=True), text)
                seen_calls[key] += 1
                if seen_calls[key] > 1:
                    per_stage[stage]["identical_calls"] += 1
        elif kind == "defect":
            defects[str(r.get("event") or "")] += 1
    wall = max((max(times) - min(times)) - discarded, 0.0) if times else 0.0
    model_busy = _busy(model_iv)
    ordered = sorted(times)
    gaps = [b - a for a, b in zip(ordered, ordered[1:])]
    # A rewind's own gap is discarded time, already taken off the wall.
    orphan = max(sum(g for g in gaps if g > ORPHAN_GAP_SECONDS) - discarded, 0.0)
    effective_input = tokens["input"] - tokens["cached"]
    from app.observability.provenance import summary as provenance_summary

    # Time spent waiting on a person (plan MF.3): each gate from opened to answered.
    gate_wait, opened_at = 0.0, None
    for r in sorted((r for r in records if r.get("kind") == "gate"), key=lambda r: str(r.get("at") or "")):
        if r.get("event") == "opened":
            opened_at = _seconds(str(r.get("at") or ""))
        elif r.get("event") == "answered" and opened_at is not None:
            gate_wait += max(_seconds(str(r.get("at") or "")) - opened_at, 0.0)
            opened_at = None

    return {
        "gate_wait_minutes": round(gate_wait / 60, 1),
        # What the run ran on (plan MF.1); a mixed run is left out of comparisons.
        **provenance_summary(records),
        "wall_minutes": round(wall / 60, 1),
        "active_minutes": round((wall - orphan) / 60, 1),
        "orphan_gap_minutes": round(orphan / 60, 1),
        "model_busy_share": _share(model_busy, wall),
        "model_calls": count["model_calls"],
        # Model calls shown approved lessons (plan RL.2): uptake, measured.
        "lessons_shown_calls": _calls_shown_lessons(records),
        "screenshot_rubric": _the_screenshot_rubric(records),
        **_the_prefix_breaks(records),
        "model_errors": count["model_errors"],
        "resumes": count["resumes"],
        "rewinds": rewinds,
        "steering_notes": count["steering_notes"],
        "input_tokens": tokens["input"],
        "output_tokens": tokens["output"],
        # What the server had to prefill: the input it did not take from its cache.
        "effective_input_tokens": effective_input,
        "prefill_decode_ratio": round(effective_input / tokens["output"], 1) if tokens["output"] else 0.0,
        "reasoning_tokens_estimated": extra["reasoning_tokens_estimated"],
        "reasoning_share_estimated": _share(extra["reasoning_tokens_estimated"], tokens["output"]),
        "lost_reply_output_share": _share(extra["output_lost"], tokens["output"]),
        "invalid_tool_call_rate": _share(extra["invalid_tool_calls"], count["model_calls"]),
        "cached_token_share": _share(tokens["cached"], tokens["input"]),
        "replies_lost_to_length": count["replies_lost_to_length"],
        "tool_calls": count["tool_calls"],
        "tool_failure_rate": _share(count["tool_failures"], count["tool_calls"]),
        # Each tool's own failure rate, the busiest first (Initiative U.1): a
        # whole-run rate hides that `edit_artifact` fails and `read_file` does not.
        "tool_failure_rate_by_tool": {
            name: _share(failed_by_tool[name], calls)
            for name, calls in sorted(calls_by_tool.items(), key=lambda item: -item[1])
        },
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
        "cache_miss_after_tool_change": count["cache_miss_after_tool_change"],
        "server_changed": count["server_changed"],
        "server_unreachable": count["server_unreachable"],
        # Each block's share of every character the requests carried; absent
        # for a run recorded before requests named their blocks.
        **{f"prompt_block_share_{name}": _share(size, sum(blocks.values())) for name, size in sorted(blocks.items())},
        # One block per stage (a `defect_fix_2_3` is its own), the busiest first.
        "stages": [
            {"name": name, **{key: row[key] for key in STAGE_COUNTERS}}
            for name, row in sorted(per_stage.items(), key=lambda item: -item[1]["calls"])
            if name
        ],
    }


#: KPIs where more is worse, as `scripts/loop/kpi_ledger.py` flags them (it runs
#: on the host without this package, so it keeps the list; a test holds the two
#: equal).
WORSE_WHEN_HIGHER = (
    "tool_failure_rate", "redundant_read_rate", "identical_call_rate", "unknown_tool_name_rate",
    "replies_lost_to_length", "model_errors", "fixes_reverted", "defects_left_open", "prefill_decode_ratio",
    "lost_reply_output_share", "invalid_tool_call_rate",
)
#: How much worse a KPI must be to be flagged, and the least it must reach.
FACTOR = 1.5
FLOOR = {
    "tool_failure_rate": 0.02, "redundant_read_rate": 0.02, "identical_call_rate": 0.02,
    "unknown_tool_name_rate": 0.01, "replies_lost_to_length": 1, "model_errors": 1,
    "fixes_reverted": 1, "defects_left_open": 1, "prefill_decode_ratio": 1.0,
    "lost_reply_output_share": 0.02, "invalid_tool_call_rate": 0.01,
}


def worse(key: str, before: float, after: float) -> bool:
    """Whether `after` is a regression on `before` for this KPI, by the ledger's rule."""
    return key in WORSE_WHEN_HIGHER and after >= FLOOR.get(key, 0) and after > FACTOR * before


def per_accepted_criterion(row: dict, accepted: int | None) -> dict:
    """`row` with the cost of each accepted criterion (plan MF.3); None for both when none was accepted or it is unknown."""
    if accepted is None:
        return {**row, "accepted_criteria": None, "wall_clock_per_accepted_criterion": None,
                "tokens_per_accepted_criterion": None}
    return {
        **row,
        "accepted_criteria": accepted,
        "wall_clock_per_accepted_criterion": round(row.get("wall_minutes", 0) / accepted, 1) if accepted else None,
        "tokens_per_accepted_criterion": round(row.get("output_tokens", 0) / accepted) if accepted else None,
    }
