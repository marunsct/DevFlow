"""How much of a run's event history Redis keeps, and for how long (LF.1507).

The history (`run:<id>:history`) is a display feed: the run page's timeline, its wizard, the sprint in progress and
the log view read it. The durable record of what a run did is its transcript and the database. It shares one Redis
with the Celery queue and the lookup store, under `noeviction`: a full Redis refuses writes, the queue's among them.

Measured 2026-11-26 on the owner's machine: of 305 MB used (512 MB limit), 299 MB was 533 run histories of up to
5,000 events each (the largest 5.9 MB), kept for 30 days after their last event whether the run was live or long
finished. 81% of those bytes were agent activity (each model reply, tool call and tool result), which nothing reads
once a run has stopped except the log view's last page; the rest - stage starts, gate answers, errors, the end - is
what the timeline and the wizard are built from.

So, three bounds:

- **While a run is live** each append keeps the latest events under an item cap (`RUN_EVENT_HISTORY_MAX`) and a byte
  cap (`RUN_EVENT_HISTORY_MAX_BYTES`), dropping the oldest first, in one atomic script. The item cap alone let a run
  of large tool results hold several MB.
- **When a run stops** (`EventBus.close`: complete, failed, cancelled or parked for a person) its history is cut to
  what the page needs after a run: every event that is not agent activity, plus the last `FINISHED_ACTIVITY_KEPT`
  agent-activity events for the log view's tail, kept for `RUN_EVENT_FINISHED_TTL_SECONDS` (never longer than it
  already had). A run that is resumed appends again and its history is live again.
- **At worker start** one bounded sweep does the same to the histories of runs that are not live, so the histories
  left before this existed are cut too, and says what it freed.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Callable, Iterable

logger = logging.getLogger(__name__)

#: Most events one run's history keeps while the run is live.
MAX_ITEMS = int(os.environ.get("RUN_EVENT_HISTORY_MAX", "5000"))
#: Most bytes one run's history keeps while the run is live.
MAX_BYTES = int(os.environ.get("RUN_EVENT_HISTORY_MAX_BYTES", str(8 * 1024 * 1024)))
#: How long a live run's history lives after its last event.
LIVE_TTL_SECONDS = int(os.environ.get("RUN_EVENT_TTL_SECONDS", str(30 * 24 * 3600)))
#: How long a stopped run's cut history lives: the timeline and wizard of a finished run read it.
FINISHED_TTL_SECONDS = int(os.environ.get("RUN_EVENT_FINISHED_TTL_SECONDS", str(14 * 24 * 3600)))
#: Agent-activity events a stopped run keeps, the latest ones: the log view's last page.
FINISHED_ACTIVITY_KEPT = int(os.environ.get("RUN_EVENT_FINISHED_ACTIVITY_KEPT", "50"))
#: The event types that are agent activity: the bulk of a history, read only while a run is followed live.
ACTIVITY = ("agent_message", "tool_call", "tool_result")
#: Statuses of a run that is still appending to its history: the sweep leaves these alone.
LIVE_STATUSES = ("created", "queued", "running")
#: Most histories one sweep looks at.
SWEEP_MOST = 5000

PATTERN = "run:*:history"


def history_key(run_id: str) -> str:
    return f"run:{run_id}:history"


def bytes_key(run_id: str) -> str:
    return f"run:{run_id}:history_bytes"


def sequence_key(run_id: str) -> str:
    return f"run:{run_id}:seq"


def _keys(run_id: str) -> list[str]:
    return [history_key(run_id), bytes_key(run_id), sequence_key(run_id)]


# KEYS: history, bytes, sequence. ARGV: payload, most items, most bytes, ttl, channel. Returns the history's length.
# A history written before the byte count existed is measured once, on its first append here.
_APPEND = """
local key, counted = KEYS[1], KEYS[2]
if redis.call('EXISTS', counted) == 0 then
  local total = 0
  for _, v in ipairs(redis.call('LRANGE', key, 0, -1)) do total = total + #v end
  redis.call('SET', counted, total)
end
redis.call('RPUSH', key, ARGV[1])
local total = redis.call('INCRBY', counted, #ARGV[1])
local n = redis.call('LLEN', key)
local most, budget = tonumber(ARGV[2]), tonumber(ARGV[3])
while n > 1 and (n > most or total > budget) do
  local v = redis.call('LPOP', key)
  total = redis.call('DECRBY', counted, #v)
  n = n - 1
end
local ttl = tonumber(ARGV[4])
for i = 1, 3 do redis.call('EXPIRE', KEYS[i], ttl) end
redis.call('PUBLISH', ARGV[5], ARGV[1])
return n
"""

# KEYS: history, bytes, sequence. ARGV: activity kept, ttl, activity types joined by ','.
# Returns {events before, events after, bytes before, bytes after}. The event type is read from the stored JSON by
# pattern, not decoded: both writers put `event_type` before any free text, and a quote inside a value is escaped,
# so the first match is the field itself. An event whose type cannot be read counts as activity.
_CUT = """
local key = KEYS[1]
local items = redis.call('LRANGE', key, 0, -1)
if #items == 0 then return {0, 0, 0, 0} end
local left = redis.call('TTL', key)
local activity = {}
for kind in string.gmatch(ARGV[3], '[^,]+') do activity[kind] = true end
local tail, seen, keep = tonumber(ARGV[1]), 0, {}
local before, after, kept = 0, 0, 0
for i = #items, 1, -1 do
  local v = items[i]
  before = before + #v
  local kind = string.match(v, '"event_type"%s*:%s*"([%w_]+)"')
  if kind and not activity[kind] then
    keep[i] = true
  elseif seen < tail then
    seen = seen + 1
    keep[i] = true
  end
end
redis.call('DEL', key)
local chunk = {}
for i = 1, #items do
  if keep[i] then
    chunk[#chunk + 1] = items[i]
    after = after + #items[i]
    kept = kept + 1
    if #chunk >= 500 then redis.call('RPUSH', key, unpack(chunk)); chunk = {} end
  end
end
if #chunk > 0 then redis.call('RPUSH', key, unpack(chunk)) end
redis.call('SET', KEYS[2], after)
local ttl = tonumber(ARGV[2])
if left > 0 and left < ttl then ttl = left end
for i = 1, 3 do redis.call('EXPIRE', KEYS[i], ttl) end
return {#items, kept, before, after}
"""


def _append_args(run_id: str, payload: str, most: int | None, ttl: int | None) -> tuple[list[str], list[Any]]:
    return _keys(run_id), [payload, MAX_ITEMS if most is None else most, MAX_BYTES,
                           LIVE_TTL_SECONDS if ttl is None else ttl, f"run:{run_id}:events"]


def _cut_args(run_id: str) -> tuple[list[str], list[Any]]:
    return _keys(run_id), [FINISHED_ACTIVITY_KEPT, FINISHED_TTL_SECONDS, ",".join(ACTIVITY)]


def append(client: Any, run_id: str, payload: str, *, most: int | None = None, ttl: int | None = None) -> int:
    """Append one event to a live run's history and publish it, from code with no event loop. Returns the length."""
    keys, args = _append_args(run_id, payload, most, ttl)
    return int(client.register_script(_APPEND)(keys=keys, args=args))


async def append_async(
    client: Any, run_id: str, payload: str, *, most: int | None = None, ttl: int | None = None
) -> int:
    """`append` on the async client."""
    keys, args = _append_args(run_id, payload, most, ttl)
    return int(await client.register_script(_APPEND)(keys=keys, args=args))


def _cut_result(raw: Any) -> dict[str, int]:
    events, kept, before, after = (int(x) for x in raw)
    return {"events": events, "kept": kept, "bytes_before": before, "bytes_after": after}


def cut(client: Any, run_id: str) -> dict[str, int]:
    """Cut a stopped run's history to what is read after a run, and give it the finished TTL."""
    keys, args = _cut_args(run_id)
    return _cut_result(client.register_script(_CUT)(keys=keys, args=args))


async def cut_async(client: Any, run_id: str) -> dict[str, int]:
    """`cut` on the async client."""
    keys, args = _cut_args(run_id)
    return _cut_result(await client.register_script(_CUT)(keys=keys, args=args))


def _run_id(key: str) -> str:
    return key[len("run:"):-len(":history")]


def statuses_from_the_database(run_ids: list[str]) -> dict[str, str]:
    """{run_id: status} for the runs asked for that have a row."""
    from app.server.run_store import RunStore

    with RunStore.shared().get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT run_id, status FROM runs WHERE run_id = ANY(%s)", (list(run_ids),))
            return {str(run_id): str(status) for run_id, status in cur.fetchall()}


def sweep(
    client: Any,
    statuses: Callable[[list[str]], dict[str, str]] = statuses_from_the_database,
    *,
    most: int = SWEEP_MOST,
    pause_seconds: float = 0.0,
) -> dict[str, int]:
    """Cut the history of every run that is not live (`LIVE_STATUSES`), at most `most` of them.

    A history whose run has no row any more is cut too: nothing will append to it. Returns what was looked at, cut
    and freed (bytes of event text), and logs it."""
    keys = []
    for key in client.scan_iter(match=PATTERN, count=500):
        keys.append(str(key))
        if len(keys) >= most:
            break
    found = statuses([_run_id(key) for key in keys]) if keys else {}
    looked, cut_count, freed = len(keys), 0, 0
    for key in keys:
        run_id = _run_id(key)
        if found.get(run_id) in LIVE_STATUSES:
            continue
        result = cut(client, run_id)
        if result["events"]:
            cut_count += 1
            freed += max(0, result["bytes_before"] - result["bytes_after"])
        if pause_seconds:
            time.sleep(pause_seconds)  # the queue shares this Redis: let its calls in between
    logger.info(
        "Run histories: looked at %d, cut %d of stopped runs, freed %.1f MB of event text",
        looked, cut_count, freed / (1024 * 1024),
    )
    return {"looked": looked, "cut": cut_count, "freed_bytes": freed}


def sweep_in_the_background() -> None:
    """The worker-start sweep, on a thread of its own so the worker takes runs at once. Never raises."""

    def _sweep() -> None:
        try:
            from app.server.redis_client import get_redis_client

            sweep(get_redis_client(), pause_seconds=0.02)
        except Exception:  # noqa: BLE001 - histories left whole only cost memory until they expire
            logger.warning("Could not cut the histories of stopped runs", exc_info=True)

    threading.Thread(target=_sweep, name="history-sweep", daemon=True).start()


def held(client: Any, keys: Iterable[str] | None = None) -> dict[str, int]:
    """{"lists", "bytes"}: how many run histories Redis holds and the memory they take."""
    lists, total = 0, 0
    for key in keys if keys is not None else client.scan_iter(match=PATTERN, count=500):
        lists += 1
        total += int(client.memory_usage(key, samples=0) or 0)
    return {"lists": lists, "bytes": total}


def memory_line(client: Any) -> str:
    """`loop.sh ready`'s line on how much of Redis the run histories hold. Never raises."""
    try:
        found = held(client)
        info = client.info("memory")
        used, most = int(info.get("used_memory") or 0), int(info.get("maxmemory") or 0)
        mb = 1024 * 1024
        share = f" ({found['bytes'] / used:.0%} of it)" if used else ""
        return (f"REDIS run histories: {found['lists']} lists holding {found['bytes'] / mb:.0f} MB{share}; "
                f"{used / mb:.0f} MB used of {f'{most / mb:.0f} MB' if most else 'no limit'}")
    except Exception as exc:  # noqa: BLE001 - a probe line never stops the probe
        return f"REDIS run histories: could not be read ({type(exc).__name__})"


__all__ = [
    "ACTIVITY", "FINISHED_ACTIVITY_KEPT", "FINISHED_TTL_SECONDS", "LIVE_STATUSES", "LIVE_TTL_SECONDS", "MAX_BYTES",
    "MAX_ITEMS", "append", "append_async", "bytes_key", "cut", "cut_async", "held", "history_key", "memory_line",
    "sequence_key", "statuses_from_the_database", "sweep", "sweep_in_the_background",
]
