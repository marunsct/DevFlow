"""One store for what every run's lookups share: answers, counts, holds and robots.txt (plan KS.5, LF.1304).

The first slice of HK.12, a lookup service fit for many runs and tenants. Measured before it
(`reports/research/2026-11-25-open-source-web-search.md`, gap 8): the answer cache was one file per query on the
machine's own disk, so a second worker or machine asked the same question again; the daily count of each source was
read, changed and written back with no lock, so concurrent runs under-counted and could pass a source's cap; two runs
asking the same question at once both went outward; a source's hold after a refusal was a file on one host; and
robots.txt was kept per transport, so every process asked each site again.

**The store is Redis** - the one the deployment already runs for its queue and events (`REDIS_URL`). Chosen over a
Postgres table with the report's reasoning: each need is one of Redis's own atomic operations - an increment checked
against a cap in one script, a lock that is a key set only if absent and that lapses by itself, entries that expire
on their own - with no schema to migrate and no database connection held per request; and the fallback the report asks
for is the files kept today. When `REDIS_URL` is unset or the store does not answer, every operation falls back to
`DATA_DIR/lookups` on this machine (files, a lock per process and a file lock), so a lookup never fails a stage; the
store is tried again after `RETRY_SECONDS`.

What it holds:

- **Answers** (`remembered`): keyed by kind and query, kept for the days the caller gives (an answer seven days,
  "nothing found" one day - `lookups.KEPT_DAYS`, `lookups.NOTHING_FOUND_DAYS`). An answer is shared between tenants
  only when its query is public: the one outbound gate (`app.tools.outbound`, plan HK.5) given the asking run's
  workspace would send it unchanged. A query the gate would still change - one holding a tenant's own words - is kept
  for that tenant alone. A key is a hash of the query and never names who asked.
- **Single-flight**: the first asker of a query takes a short lease on it; concurrent askers of the same query wait for
  its answer and read it instead of asking outward too.
- **Counts and caps** (`reserve`): one request to a source is counted against the source's daily cap and the tenant's
  daily budget in one atomic step, so no number of concurrent runs passes either.
- **Holds** (`hold_of`, `changed_hold`): a source's breaker state (`source_breaker`), changed atomically.
- **robots.txt** (`shared_robots`): what a site answered, kept a day (RFC 9309) for every process and machine.
- **A frozen snapshot** (`LOOKUPS_FROZEN=<label>`): the answers a Measure batch reads. The first read of a query under
  a label copies the answer the store holds then - or the one it asks for - into the snapshot, where it never goes
  stale; every later read under that label, by either arm of a pair or a rerun, gets that same answer.

`LOOKUPS_STORE_PREFIX` names the deployment's keys (default `lookups`), so two deployments may share one Redis.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import logging
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Iterator

logger = logging.getLogger(__name__)

#: The kinds of answer kept.
LOOKUP = "lookup"
ROBOTS = "robots"

#: Seconds the store is left alone after it did not answer; the files on this machine serve meanwhile.
RETRY_SECONDS = 30.0
#: Seconds the first asker of a query holds it; its answer is awaited no longer than this.
LEASE_SECONDS = 120.0
#: Seconds a robots.txt answer is kept (RFC 9309 section 2.4: no more than a day).
ROBOTS_SECONDS = 24 * 3600
#: Days an answer kept in a frozen snapshot lives (a Measure batch is days, not months).
FROZEN_DAYS = 90
#: Characters of one shared value at most: a larger one is not shared, so the queue's memory is never crowded.
MOST_SHARED = 256 * 1024
#: Requests a day one tenant's runs may send to the lookup sources together; `LOOKUP_TENANT_DAILY_CAP` sets it. About
#: the sum of the sources' own keyless caps, so a single tenant meets a source's cap first.
TENANT_DAILY_CAP = 5_000
#: The tenant of a run outside any tenant's folder, and of a call outside a run.
NO_TENANT = "shared"

_LOCK = threading.Lock()
_CLIENTS: dict[str, Any] = {}
_DOWN_UNTIL: dict[str, float] = {}
_FLIGHTS: dict[str, threading.Lock] = {}
#: This process's turn at the files on this machine (the file lock is each process's turn).
_FILES = threading.Lock()

# One request counted against the source's cap and the tenant's budget at once: 0 sent, 1 the source's cap reached,
# 2 the tenant's budget spent.
_RESERVE = """
local source = tonumber(redis.call('HGET', KEYS[1], ARGV[1]) or '0')
if source >= tonumber(ARGV[3]) then return 1 end
local tenant = tonumber(redis.call('HGET', KEYS[2], ARGV[2]) or '0')
if tenant >= tonumber(ARGV[4]) then return 2 end
redis.call('HINCRBY', KEYS[1], ARGV[1], 1)
redis.call('HINCRBY', KEYS[2], ARGV[2], 1)
redis.call('EXPIRE', KEYS[1], ARGV[5])
redis.call('EXPIRE', KEYS[2], ARGV[5])
return 0
"""
# A lease given back only by the asker that holds it.
_RELEASE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end
return 0
"""


# --- where things are kept ------------------------------------------------------------------------------------------

def _prefix() -> str:
    return re.sub(r"[^\w.-]", "-", os.environ.get("LOOKUPS_STORE_PREFIX", "").strip()) or "lookups"


def _folder() -> Path:
    return Path(os.environ.get("DATA_DIR") or "data") / "lookups"


def _client() -> Any | None:
    """The shared store's client, or None when none is configured or it did not answer a moment ago."""
    url = os.environ.get("REDIS_URL", "").strip()
    if not url or _DOWN_UNTIL.get(url, 0.0) > time.monotonic():
        return None
    with _LOCK:
        client = _CLIENTS.get(url)
        if client is None:
            import redis

            client = redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=1, socket_timeout=3,
                                          health_check_interval=30)
            _CLIENTS[url] = client
    return client


def _shared(operation: Callable[[Any], Any]) -> tuple[bool, Any]:
    """(True, what `operation` gave) on the shared store; (False, None) when there is none or it did not answer."""
    client = _client()
    if client is None:
        return False, None
    try:
        return True, operation(client)
    except Exception as exc:  # noqa: BLE001 - the files on this machine serve until the store answers again
        url = os.environ.get("REDIS_URL", "").strip()
        _DOWN_UNTIL[url] = time.monotonic() + RETRY_SECONDS
        logger.warning("The lookup store did not answer (%s); this machine's files serve for %.0f s",
                       type(exc).__name__, RETRY_SECONDS)
        return False, None


@contextlib.contextmanager
def _local_lock(name: str) -> Iterator[None]:
    """This machine's lock called `name`: every thread and process on it waits its turn."""
    folder = _folder()
    folder.mkdir(parents=True, exist_ok=True)
    with _FILES, open(folder / f".{name}.lock", "a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_json(path: Path, value: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        temporary.write_text(json.dumps(value), encoding="utf-8")
        temporary.replace(path)
    except OSError:
        pass


def _day(now: float | None = None) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() if now is None else now))


# --- whose run, and what is public ----------------------------------------------------------------------------------

def tenant(repo_root: str | Path | None = None) -> str:
    """The tenant whose run this is: the first folder of its workspace under the workspace root
    (`workspaces.tenant_segment`), of `repo_root` or of the run in progress; `NO_TENANT` outside a run."""
    try:
        from app.server.workspaces import workspace_root
        from app.tools import outbound

        root = outbound._workspace(repo_root)  # noqa: SLF001 - the gate's own way to find the run's workspace
        if root is None:
            return NO_TENANT
        parts = Path(root).resolve().relative_to(workspace_root()).parts
        return parts[0] if len(parts) >= 2 else NO_TENANT
    except Exception:  # noqa: BLE001 - not under the workspace root
        return NO_TENANT


def public(query: str, repo_root: str | Path | None = None) -> bool:
    """Whether `query` may be shared between tenants: the one outbound gate, given the asking run's workspace, would
    send it as it is - none of the tenant's own words, paths, addresses or tokens in it."""
    from app.tools import outbound

    try:
        sent, removed = outbound.prepared(query, repo_root=repo_root)
    except Exception:  # noqa: BLE001 - unknown is not public
        return False
    return removed == 0 and " ".join(sent.split()) == " ".join(str(query or "").split())


def _scope(query: str, repo_root: str | Path | None) -> str:
    return "shared" if public(query, repo_root) else f"tenant-{tenant(repo_root)}"


def _id(kind: str, query: str) -> str:
    return hashlib.sha256(f"{kind}\n{query}".encode("utf-8")).hexdigest()[:32]


def frozen_label() -> str:
    """The frozen snapshot a Measure batch reads (`LOOKUPS_FROZEN`), or "" for the live store."""
    return re.sub(r"[^\w.-]", "-", os.environ.get("LOOKUPS_FROZEN", "").strip())


# --- answers --------------------------------------------------------------------------------------------------------

def _key(where: str, scope: str, kind: str, query: str) -> str:
    return f"{_prefix()}:{where}:{scope}:{kind}:{_id(kind, query)}"


def _path(where: str, scope: str, kind: str, query: str) -> Path:
    return _folder() / where / scope / kind / f"{_id(kind, query)}.json"


def _fresh(entry: Any) -> Any:
    """The answer an entry holds while it is fresh; a frozen one (no days) never goes stale."""
    if not isinstance(entry, dict) or "answer" not in entry:
        return None
    days = entry.get("days")
    if days is not None and time.time() - float(entry.get("at") or 0) > float(days) * 86_400:
        return None
    return entry["answer"]


def _get(where: str, scope: str, kind: str, query: str) -> Any:
    done, raw = _shared(lambda client: client.get(_key(where, scope, kind, query)))
    if done:
        try:
            return _fresh(json.loads(raw)) if raw else None
        except ValueError:
            return None
    return _fresh(_read_json(_path(where, scope, kind, query)))


def _put(where: str, scope: str, kind: str, query: str, answer: Any, days: float | None) -> None:
    entry = {"at": time.time(), "days": days, "answer": answer}
    text = json.dumps(entry)
    lives = int((FROZEN_DAYS if days is None else days) * 86_400) + 3_600
    if len(text) <= MOST_SHARED:
        done, _ = _shared(lambda client: client.set(_key(where, scope, kind, query), text, ex=lives))
        if done:
            return
    _write_json(_path(where, scope, kind, query), entry)


def _kept(scope: str, kind: str, query: str) -> Any:
    """The answer kept for `query`: under a frozen label the snapshot's, which the live answer seeds; else the live."""
    label = frozen_label()
    if not label:
        return _get("live", scope, kind, query)
    where = f"frozen-{label}"
    found = _get(where, scope, kind, query)
    if found is None:
        found = _get("live", scope, kind, query)
        if found is not None:
            _put(where, scope, kind, query, found, None)
    return found


def _keep(scope: str, kind: str, query: str, answer: Any, days: float) -> None:
    _put("live", scope, kind, query, answer, days)
    if frozen_label():
        _put(f"frozen-{frozen_label()}", scope, kind, query, answer, None)


@contextlib.contextmanager
def _first_asker(scope: str, kind: str, query: str) -> Iterator[Callable[[], Any]]:
    """Wait until this caller is the only one asking `query`, or until another asker's answer is kept; yields a
    function giving that kept answer (None when this caller must ask)."""
    flight = _key("flight", scope, kind, query)
    token = uuid.uuid4().hex
    deadline = time.monotonic() + LEASE_SECONDS
    step = 0.02
    while True:
        found = _kept(scope, kind, query)
        if found is not None:
            yield lambda: found
            return
        done, taken = _shared(lambda client: client.set(flight, token, nx=True, px=int(LEASE_SECONDS * 1000)))
        if not done:
            break
        if taken:
            try:
                found = _kept(scope, kind, query)
                yield lambda: found
            finally:
                _shared(lambda client: client.eval(_RELEASE, 1, flight, token))
            return
        if time.monotonic() > deadline:
            yield lambda: None
            return
        time.sleep(step)
        step = min(0.25, step * 1.5)
    # No shared store: one asker of a query at a time in this process.
    with _LOCK:
        lock = _FLIGHTS.setdefault(flight, threading.Lock())
    got = lock.acquire(timeout=LEASE_SECONDS)
    try:
        found = _kept(scope, kind, query)
        yield lambda: found
    finally:
        if got:
            lock.release()


def remembered(kind: str, query: str, ask: Callable[[], dict[str, Any]], *,
               days: Callable[[dict[str, Any]], float | None],
               repo_root: str | Path | None = None) -> tuple[dict[str, Any], bool]:
    """(the answer for `query`, whether it was kept from before): kept when fresh, else asked once however many
    callers ask at the same moment (`ask`), and kept for `days(answer)` days (None: not kept). Shared between tenants
    only when the query is public (`public`)."""
    scope = _scope(query, repo_root)
    with _first_asker(scope, kind, query) as kept:
        found = kept()
        if found is not None:
            return found, True
        answer = ask()
        lasts = days(answer)
        if lasts is not None:
            _keep(scope, kind, query, answer, lasts)
        return answer, False


# --- counts and caps ------------------------------------------------------------------------------------------------

def _counts_key(day: str) -> str:
    return f"{_prefix()}:count:{day}"


def _tenants_key(day: str) -> str:
    return f"{_prefix()}:tenants:{day}"


def _counts_path(day: str) -> Path:
    return _folder() / f"requests-{day}.json"


def _tenants_path(day: str) -> Path:
    return _folder() / f"tenants-{day}.json"


def _numbers(raw: Any) -> dict[str, int]:
    try:
        return {str(k): int(v) for k, v in (raw or {}).items()}
    except (AttributeError, TypeError, ValueError):
        return {}


def requests_today() -> dict[str, int]:
    """Requests sent to each source today (UTC), by every run of the deployment."""
    day = _day()
    done, counts = _shared(lambda client: client.hgetall(_counts_key(day)))
    return _numbers(counts) if done else _numbers(_read_json(_counts_path(day)))


def tenant_requests_today(who: str | None = None) -> int:
    """Requests the tenant `who` (of the run in progress when None) sent to the sources today (UTC)."""
    who, day = who or tenant(), _day()
    done, count = _shared(lambda client: client.hget(_tenants_key(day), who))
    if done:
        return int(count or 0)
    return _numbers(_read_json(_tenants_path(day))).get(who, 0)


def tenant_daily_cap() -> int:
    """Requests a day one tenant's runs may send to the sources together (`LOOKUP_TENANT_DAILY_CAP`)."""
    value = os.environ.get("LOOKUP_TENANT_DAILY_CAP", "").strip()
    return int(value) if value.isdigit() else TENANT_DAILY_CAP


def reserve(source: str, cap: int, who: str | None = None) -> str:
    """"" when one request to `source` may be sent now - then counted against its daily `cap` and the tenant's daily
    budget in one step, so concurrent callers never pass either - else why it may not."""
    who, day, budget = who or tenant(), _day(), tenant_daily_cap()
    done, said = _shared(lambda client: client.eval(_RESERVE, 2, _counts_key(day), _tenants_key(day), source, who,
                                                    int(cap), int(budget), 2 * 86_400))
    if not done:
        with _local_lock("counts"):
            counts, tenants = _numbers(_read_json(_counts_path(day))), _numbers(_read_json(_tenants_path(day)))
            said = 1 if counts.get(source, 0) >= cap else 2 if tenants.get(who, 0) >= budget else 0
            if not said:
                counts[source] = counts.get(source, 0) + 1
                tenants[who] = tenants.get(who, 0) + 1
                _write_json(_counts_path(day), counts)
                _write_json(_tenants_path(day), tenants)
    if int(said or 0) == 1:
        return f"{source}: daily cap of {cap} requests reached"
    if int(said or 0) == 2:
        return f"{source}: this account's daily budget of {budget} lookup requests is spent"
    return ""


def count(source: str, sent: int = 1, who: str | None = None) -> None:
    """Count `sent` requests made to `source` without asking first (a source with its own transport)."""
    who, day = who or tenant(), _day()

    def add(client: Any) -> None:
        pipe = client.pipeline()
        pipe.hincrby(_counts_key(day), source, sent)
        pipe.hincrby(_tenants_key(day), who, sent)
        pipe.expire(_counts_key(day), 2 * 86_400)
        pipe.expire(_tenants_key(day), 2 * 86_400)
        pipe.execute()

    done, _ = _shared(add)
    if not done:
        with _local_lock("counts"):
            for path, name in ((_counts_path(day), source), (_tenants_path(day), who)):
                numbers = _numbers(_read_json(path))
                numbers[name] = numbers.get(name, 0) + sent
                _write_json(path, numbers)


# --- holds ----------------------------------------------------------------------------------------------------------

def _hold_key(source: str) -> str:
    return f"{_prefix()}:hold:{source}"


def _holds_path() -> Path:
    return _folder() / "holds.json"


def hold_of(source: str) -> dict[str, float]:
    """What the breaker keeps of `source`: until when it is held and its refusals in a row ({} for nothing)."""
    done, raw = _shared(lambda client: client.get(_hold_key(source)))
    if done:
        try:
            entry = json.loads(raw) if raw else {}
        except ValueError:
            entry = {}
    else:
        holds = _read_json(_holds_path())
        entry = holds.get(source) if isinstance(holds, dict) else {}
    return entry if isinstance(entry, dict) else {}


def changed_hold(source: str, change: Callable[[dict[str, float]], dict[str, float] | None]) -> dict[str, float]:
    """`source`'s hold changed by `change` (given what is kept, it gives the new entry, or None to leave it) in one
    step no other process interleaves with; the entry kept after."""
    key = _hold_key(source)

    def atomically(client: Any) -> dict[str, float]:
        import redis

        with client.pipeline() as pipe:
            while True:
                try:
                    pipe.watch(key)
                    raw = pipe.get(key)
                    entry = json.loads(raw) if raw else {}
                    new = change(entry if isinstance(entry, dict) else {})
                    if new is None:
                        pipe.unwatch()
                        return entry
                    lives = max(60, int(float(new.get("until") or 0) - time.time())) + 86_400
                    pipe.multi()
                    pipe.set(key, json.dumps(new), ex=lives)
                    pipe.execute()
                    return new
                except redis.WatchError:
                    continue

    done, entry = _shared(atomically)
    if done:
        return entry
    with _local_lock("holds"):
        holds = _read_json(_holds_path())
        holds = holds if isinstance(holds, dict) else {}
        old = holds.get(source) if isinstance(holds.get(source), dict) else {}
        new = change(dict(old))
        if new is None:
            return old
        holds[source] = new
        _write_json(_holds_path(), holds)
        return new


# --- robots.txt -----------------------------------------------------------------------------------------------------

def shared_robots(get: Callable[[str], "tuple[int, str] | None"]) -> Callable[[str], "tuple[int, str] | None"]:
    """`get` (a robots.txt address -> (status, text) or None) with what each site answered kept `ROBOTS_SECONDS` for
    every process and machine: a site's robots.txt is public. An unreachable one (None, 5xx) is not kept."""

    def kept_or_asked(address: str) -> "tuple[int, str] | None":
        found = _get("live", "shared", ROBOTS, address)
        if isinstance(found, list) and len(found) == 2:
            return int(found[0]), str(found[1])
        answer = get(address)
        if answer is not None and answer[0] < 500:
            _put("live", "shared", ROBOTS, address, [int(answer[0]), str(answer[1])], ROBOTS_SECONDS / 86_400)
        return answer

    return kept_or_asked


__all__ = ["LOOKUP", "NO_TENANT", "ROBOTS", "TENANT_DAILY_CAP", "changed_hold", "count", "frozen_label", "hold_of",
           "public", "remembered", "requests_today", "reserve", "shared_robots", "tenant", "tenant_daily_cap",
           "tenant_requests_today"]
