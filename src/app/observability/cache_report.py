"""How much of a run's prompt the server read from its cache, and where the rest came from, in a few lines.

The share and the break reasons were already computed after a run (`run_kpis`: `cached_token_share`,
`prefix_break_<reason>`), so the one number that decides prefill time on a local model - the share of prompt tokens
served from the server's cache - was read from a finished run's row, not at a check while it ran. Measured on one
model that reports cached tokens: 71% of prompt tokens were served from cache, and a stage whose calls kept their
prefix was prefilled once. This reads the same transcript records `loop.sh status` and the audit already read:
the run's share, the breaks that cost the most uncached tokens, and the stages with the most uncached input. A
server that reports no cached tokens at all is said to, instead of printing 0%, which reads as a cache that never
hits. Read-only: it changes no request.
"""

from __future__ import annotations

import collections
from typing import Any, Iterable

from app.observability.prefix_breaks import classified

#: The reasons that are a break of the prefix; the others (`stable`, a conversation's or a stage's first call) are not.
BREAKS = ("tools_changed", "system_changed", "opening_changed", "history_rewritten", "evicted")
#: Stages listed, at most.
MOST_STAGES = 6


def _tokens(count: int) -> str:
    return f"{count / 1_000_000:.1f}M" if count >= 1_000_000 else f"{count / 1_000:.0f}k" if count >= 1_000 else str(count)


def summary(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """The run's input tokens, those read from the cache, the breaks by reason and the stages' uncached input."""
    total = cached = reported = calls = 0
    why_calls: collections.Counter = collections.Counter()
    why_uncached: collections.Counter = collections.Counter()
    stages: dict[str, dict[str, Any]] = {}
    for call in classified(records):
        calls += 1
        total += call["input_tokens"]
        cached += int(call["cache_read"] or 0)
        reported += call["cache_read"] is not None
        row = stages.setdefault(call["stage"], {"calls": 0, "input": 0, "cached": 0, "uncached": 0,
                                                "breaks": collections.Counter()})
        row["calls"] += 1
        row["input"] += call["input_tokens"]
        row["cached"] += int(call["cache_read"] or 0)
        row["uncached"] += call["uncached"]
        if call["why"] in BREAKS:
            why_calls[call["why"]] += 1
            why_uncached[call["why"]] += call["uncached"]
            row["breaks"][call["why"]] += 1
    return {"calls": calls, "input": total, "cached": cached, "reported": reported, "breaks": dict(why_calls),
            "uncached_by_break": dict(why_uncached), "stages": stages}


def lines(records: Iterable[dict[str, Any]]) -> list[str]:
    """The report as printed lines: [] for a run with no answered call."""
    found = summary(records)
    if not found["calls"]:
        return []
    if not found["reported"]:
        out = [f"prompt cache: the server reported no cached tokens over {found['calls']} calls (share unknown)"]
    else:
        share = found["cached"] / max(1, found["input"])
        out = [f"prompt cache: {share:.0%} of {_tokens(found['input'])} input tokens served from cache"]
    broken = sorted(found["breaks"], key=lambda why: -found["uncached_by_break"][why])
    out.append("prefix breaks: " + (", ".join(
        f"{why} x{found['breaks'][why]} ({_tokens(found['uncached_by_break'][why])} uncached)" for why in broken
    ) if broken else "none"))
    worst = sorted(found["stages"].items(), key=lambda item: -item[1]["uncached"])[:MOST_STAGES]
    if found["reported"] and worst:
        out.append(f"  {'stage':<26}{'calls':>6}{'cached':>8}{'uncached':>10}  first break")
        for stage, row in worst:
            first = row["breaks"].most_common(1)
            out.append(f"  {stage[:25]:<26}{row['calls']:>6}{row['cached'] / max(1, row['input']):>8.0%}"
                       f"{_tokens(row['uncached']):>10}  " + (f"{first[0][0]} x{first[0][1]}" if first else "-"))
    return out


__all__ = ["BREAKS", "MOST_STAGES", "lines", "summary"]
