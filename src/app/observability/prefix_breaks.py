"""Why a model call's prompt did not reuse the previous call's cached prefix, read from the transcript (plan PX.1).

llama-server reuses its KV cache only for a byte-identical prefix. Every
`model_request` record already carries the tools offered, the size of each
block of the request (`blocks`: system, tool schemas, environment contract,
project memory, specification, request, conversation, workspace) and how many
earlier messages it resent unchanged (`carried`); every `model_response`
carries `cache_read`. Comparing each call with the previous call of the same
stage names the first part that changed, so the prefix-cache work (PX.2-PX.7)
is ordered by measured cost. Read-only: it changes no request.

Reasons, in the order a request is laid out:
- `tools_changed` - a different tool list (tools are rendered into the system prompt);
- `system_changed` - the system message changed size (steering notes, a thinking toggle);
- `opening_changed` - the opening messages changed (memory order, snapshot clock, request);
- `history_rewritten` - an earlier stored message was not resent as it was
  (argument truncation, reasoning carry, cut-reply shortening, compaction);
- `evicted` - the prefix was unchanged and still nothing was read from the cache;
- `stable` - nothing before the new messages changed.
"""

from __future__ import annotations

import ast
import collections
from typing import Any, Iterable

#: The request blocks in the order they reach the model, after the system message.
OPENING_BLOCKS = ("environment_contract", "project_memory", "specification", "request")
REASONS = ("tools_changed", "system_changed", "opening_changed", "history_rewritten", "evicted", "stable")


def _as(value: Any, kind: type) -> Any:
    if isinstance(value, kind):
        return value
    try:
        parsed = ast.literal_eval(str(value))
        return parsed if isinstance(parsed, kind) else kind()
    except (ValueError, SyntaxError):
        return kind()


def _messages(record: dict[str, Any]) -> int:
    messages = record.get("messages")
    if isinstance(messages, list):
        return len(messages)
    try:
        return int(str(messages).split()[0])
    except (ValueError, IndexError):
        return 0


def reason(previous: dict[str, Any], current: dict[str, Any], cache_read: int | None) -> str:
    """The first part of `current`'s request that differs from `previous`'s, or `evicted` / `stable`."""
    before, now = _as(previous.get("blocks"), dict), _as(current.get("blocks"), dict)
    if _as(previous.get("tools"), list) != _as(current.get("tools"), list) or before.get("tool_schemas") != now.get("tool_schemas"):
        return "tools_changed"
    if before.get("system") != now.get("system"):
        return "system_changed"
    if any(before.get(block) != now.get(block) for block in OPENING_BLOCKS):
        return "opening_changed"
    try:
        carried = int(str(current.get("carried") or 0))
        carried_before = int(str(previous.get("carried") or 0))
    except ValueError:
        carried, carried_before = 0, 0
    # Each call ends in a volatile tail (the workspace digest) the next call
    # does not resend, so the history grows by its new messages less that
    # tail; one that resends no more of it than the call before was rewritten
    # somewhere at or before the earlier call's last carried message.
    if _messages(previous) and carried <= carried_before:
        return "history_rewritten"
    if cache_read == 0:
        return "evicted"
    return "stable"


def breaks(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Counts of each reason and the uncached input tokens behind each, over a run's calls."""
    asked: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    last: dict[str, dict[str, Any]] = {}
    counts: collections.Counter = collections.Counter()
    uncached: collections.Counter = collections.Counter()
    for record in records:
        stage, kind = str(record.get("stage") or ""), record.get("kind")
        if kind == "model_request":
            asked[stage].append(record)
        elif kind == "model_response" and asked.get(stage):
            request = asked[stage].pop(0)
            usage = _as(record.get("usage"), dict)
            details = usage.get("input_token_details") or {}
            read = details.get("cache_read") if isinstance(details, dict) else None
            read = int(read) if isinstance(read, (int, float)) else None
            why = reason(last[stage], request, read) if stage in last else "first_of_the_stage"
            last[stage] = request
            counts[why] += 1
            uncached[why] += max(0, int(usage.get("input_tokens") or 0) - int(read or 0))
    return {"calls_by_reason": dict(counts), "uncached_tokens_by_reason": dict(uncached)}


__all__ = ["OPENING_BLOCKS", "REASONS", "breaks", "reason"]
