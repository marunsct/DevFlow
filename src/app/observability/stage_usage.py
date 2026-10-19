"""Where a run spent its time and tokens, stage by stage, from its transcript (plan BG.7).

The loop's audit scripts read the same record from inside the worker; the run
page could not. Each stage, in the order it first ran: its wall time (first
record to last), the time spent waiting on model replies, the replies, the
tokens in, cached and out, the replies lost to the output limit with nothing
kept, the reads answered with "you already have this", and the tool calls
that failed or were refused. A stage that ran more than once - a fix stage on
another revision - is one row with its visits summed.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Iterable

#: The tools that read a file.
READS = frozenset({"read_file", "read_repository_file"})

#: A read that gave nothing new: a repeat refused, or a pointer to the project memory.
_NOTHING_NEW = re.compile(
    r"You have already read lines|same bytes|Refusing to read|is in the project memory at the start of this conversation"
)

#: A tool result that is a failure or a refusal.
_FAILED = re.compile(r"^\s*(\[[^\]]*\]\s*)?(\{\"error\"|Error:|Refusing|Not running|Not looking)")


def _when(entry: dict) -> datetime | None:
    try:
        return datetime.fromisoformat(str(entry.get("at")))
    except (TypeError, ValueError):
        return None


def _text(content: Any) -> str:
    return content if isinstance(content, str) else str(content or "")


def _failed(entry: dict) -> bool:
    content = entry.get("content")
    if isinstance(content, dict):
        return bool(content.get("error"))
    if entry.get("raised"):
        return True
    return bool(_FAILED.match(_text(content)))


def _lost(entry: dict) -> bool:
    """A reply cut off at the output limit with no text and no call kept."""
    return (
        str(entry.get("finish_reason") or "") == "length"
        and not str(entry.get("text") or "").strip()
        and not entry.get("tool_calls")
        and not entry.get("invalid_tool_calls")
    )


def stage_usage(entries: Iterable[dict]) -> list[dict[str, Any]]:
    """One row per stage, in the order the stages first ran."""
    rows: dict[str, dict[str, Any]] = {}
    asked_at: dict[str, datetime] = {}
    read_calls: dict[str, str] = {}
    for entry in entries:
        stage = str(entry.get("stage") or "")
        if not stage:
            continue
        row = rows.setdefault(stage, {
            "stage": stage, "first": None, "last": None, "wall_seconds": 0.0, "model_seconds": 0.0,
            "model_calls": 0, "input_tokens": 0, "cached_tokens": 0, "output_tokens": 0,
            "lost_replies": 0, "tool_calls": 0, "tool_failures": 0, "redundant_reads": 0,
        })
        at = _when(entry)
        if at is not None:
            row["first"] = at if row["first"] is None or at < row["first"] else row["first"]
            row["last"] = at if row["last"] is None or at > row["last"] else row["last"]
        kind = entry.get("kind")
        if kind == "model_request" and at is not None:
            asked_at[stage] = at
        elif kind == "model_response":
            row["model_calls"] += 1
            started = asked_at.pop(stage, None)
            if started is not None and at is not None:
                row["model_seconds"] += max(0.0, (at - started).total_seconds())
            usage = entry.get("usage") or {}
            row["input_tokens"] += int(usage.get("input_tokens") or 0)
            row["output_tokens"] += int(usage.get("output_tokens") or 0)
            row["cached_tokens"] += int((usage.get("input_token_details") or {}).get("cache_read") or 0)
            row["lost_replies"] += int(_lost(entry))
        elif kind == "tool_call":
            row["tool_calls"] += 1
            if entry.get("tool") in READS:
                read_calls[str(entry.get("call_id") or "")] = stage
        elif kind == "tool_result":
            row["tool_failures"] += int(_failed(entry))
            if (entry.get("tool") in READS or str(entry.get("call_id") or "") in read_calls) and _NOTHING_NEW.search(
                _text(entry.get("content"))[:600]
            ):
                row["redundant_reads"] += 1
    out = []
    for row in rows.values():
        first, last = row.pop("first"), row.pop("last")
        row["wall_seconds"] = round((last - first).total_seconds(), 1) if first and last else 0.0
        row["model_seconds"] = round(row["model_seconds"], 1)
        out.append(row)
    return out


#: How far back the recent calls go, and at most how many.
RECENT_SECONDS = 3600
MOST_RECENT_CALLS = 300


def recent_calls(entries: Iterable[dict], now: datetime | None = None) -> list[dict[str, Any]]:
    """The model calls of the last hour, oldest first: when, which stage, tokens in and out, seconds (plan BG.15)."""
    calls: list[dict[str, Any]] = []
    asked_at: dict[str, datetime] = {}
    for entry in entries:
        stage = str(entry.get("stage") or "")
        at = _when(entry)
        if at is None:
            continue
        if entry.get("kind") == "model_request":
            asked_at[stage] = at
        elif entry.get("kind") == "model_response":
            started = asked_at.pop(stage, None)
            usage = entry.get("usage") or {}
            calls.append({
                "at": at.isoformat(),
                "stage": stage,
                "input_tokens": int(usage.get("input_tokens") or 0),
                "output_tokens": int(usage.get("output_tokens") or 0),
                "seconds": round(max(0.0, (at - started).total_seconds()), 1) if started else 0.0,
            })
    if not calls:
        return []
    last = now or max(datetime.fromisoformat(call["at"]) for call in calls)
    kept = [call for call in calls if (last - datetime.fromisoformat(call["at"])).total_seconds() <= RECENT_SECONDS]
    return kept[-MOST_RECENT_CALLS:]


__all__ = ["recent_calls", "stage_usage"]
