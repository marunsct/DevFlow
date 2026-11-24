"""The lookup service fit for many runs and tenants: what every source asked from outside shares (plan HK.12, LF.1308).

KS.5 (LF.1304, `lookup_store`) built one store for every run, machine and tenant: the stuck lookups' answers, the
daily caps, the breakers' holds, robots.txt and the frozen snapshots. Left after it, each measured in the code:

- **Rates were per day only.** GitHub's issue search allows 10 requests a minute (30 with a token), its core API 60 an
  hour, crates.io one a second; a burst of runs passed each well inside the day's cap and was refused by the source,
  which then held it for every run. Each source now has a token bucket (`RATES`), shared by every run and machine and
  taken in one atomic step (`lookup_store.take`); a request waits for a token up to `MOST_WAIT` seconds, else it is
  not sent and the lookup says why.
- **The registries' and the documentation's caches were per process** (`package_registry._CACHE`, `docs._CACHE`,
  `release_fit`'s release lists): every worker asked each registry again, and a worker kept a "latest" release for
  its whole life. Their answers for public package names and public documentation now live in the shared store, each
  with its lifetime (`LATEST_DAYS`, `VERSION_DAYS`, `DOCUMENT_DAYS`); the process cache keeps only what may not be
  shared - a stub's answers, the product's own names, a run whose lookups are "off", a value too large for the store.
- **A page read was read again by every run.** A public page read is kept `PAGE_DAYS` (a versioned address, such as
  a release tag or a commit-pinned file, `VERSIONED_PAGE_DAYS`); an address holding the tenant's own words is kept for
  that tenant alone.
- **The stuck lookup's once-per-run record was a module dictionary** (`stuck_lookup._DONE`): lost on a deploy or a
  worker restart, never shared by two workers of one run, and never emptied. It is now the run's own record in the
  store (`once_per_run`), kept `RUN_DAYS`.
- **A paid search's results were kept like any other.** A paid provider's terms may forbid storing its results (Brave
  restricts it); a paid source is asked only after every free official source (`free_first`), and an answer holding
  its results is never kept unless `LOOKUP_PAID_RESULTS_KEPT` names it (`may_keep`, default none).

A run whose Internet lookups choice is "off" neither reads nor writes the store (`lookup_store.shares`). Every value
in the store has a lifetime, and nothing is written there while the queue's Redis is half full (`lookup_store._room`).
`probe_lines` gives `loop.sh lookups` each source's allowance, its bucket and the store's memory.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Hashable, Iterable
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

#: (requests, per seconds) each source may be sent, its burst the same number: the sources' own published limits, with
#: room left. A source not named has no rate beyond its daily cap.
RATES: dict[str, tuple[int, float]] = {
    "stack exchange": (10, 1.0),        # Stack Exchange drops an address sending more than 30 a second
    "github issues": (10, 60.0),        # GitHub's search API: 10 a minute without a token
    "github": (60, 3_600.0),            # GitHub's core API: 60 an hour without a token
    "github files": (60, 60.0),         # the raw file host states none; one a second is polite
    "context7": (60, 60.0),
    "brave": (1, 1.0),                  # Brave's free plan: one a second
    "tavily": (1, 1.0),
    "crates.io": (1, 1.0),              # crates.io's crawler policy: one request a second
}
#: The rates with the source's key set: GitHub allows 30 searches a minute and 5,000 core requests an hour with a token.
KEYED_RATES: dict[str, tuple[int, float]] = {"github issues": (30, 60.0), "github": (5_000, 3_600.0)}
#: The variable holding the key that raises a source's rate.
_KEY_OF: dict[str, str] = {"github issues": "GITHUB_TOKEN", "github": "GITHUB_TOKEN"}
#: The registry hosts with a rate of their own, and the source name their bucket has.
REGISTRY_HOSTS: dict[str, str] = {"crates.io": "crates.io"}
#: Seconds a request waits for its source's token before it is not sent (`LOOKUP_MOST_WAIT`).
MOST_WAIT = 10.0

#: Days a registry's answer about a package's current release is kept: HK.12's "latest", one hour.
LATEST_DAYS = 1 / 24
#: Days what one release of a package states (the runtime it needs, whether it was withdrawn) is kept: it never
#: changes, but every value in the store has a lifetime.
VERSION_DAYS = 30
#: Days a documentation page an official index names is kept; a missing one `MISSING_DAYS`.
DOCUMENT_DAYS = 1
MISSING_DAYS = 1 / 24
#: Days a read page is kept; one at a versioned address `VERSIONED_PAGE_DAYS` (KS.5's lifetimes).
PAGE_DAYS = 1 / 24
VERSIONED_PAGE_DAYS = 7
#: Days a run's own once-only record is kept: longer than any run.
RUN_DAYS = 7
#: Characters of one value kept in the store; a larger one stays in the asking process's cache.
MOST_VALUE = 192 * 1024

#: A versioned address: a release tag, a commit, a file pinned to a commit, or a path naming a full version.
_VERSIONED = re.compile(r"/releases/tag/[^/]+|/(?:blob|tree|commit|raw)/[0-9a-f]{7,40}(?:/|$)|/v?\d+\.\d+\.\d+(?:/|$)")


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


# --- rates ----------------------------------------------------------------------------------------------------------

def _credential(variable: str) -> str:
    from app.tools import lookups

    return lookups.credential(variable)


def rate_of(source: str) -> tuple[int, float] | None:
    """(requests, per seconds) `source` may be sent - `LOOKUP_RATES` (`name=N/s`, `N/m` or `N/h`, comma-separated; 0
    for none) for it, else its default, higher with its key - or None when it has no rate."""
    for part in os.environ.get("LOOKUP_RATES", "").split(","):
        asked, _, value = part.partition("=")
        if asked.strip().lower() != source:
            continue
        found = re.fullmatch(r"\s*(\d+)\s*/\s*([smh])\s*", value)
        if found:
            n = int(found.group(1))
            return (n, {"s": 1.0, "m": 60.0, "h": 3_600.0}[found.group(2)]) if n else None
    if source in KEYED_RATES and _KEY_OF.get(source) and _credential(_KEY_OF[source]):
        return KEYED_RATES[source]
    return RATES.get(source)


def most_wait() -> float:
    try:
        return max(0.0, float(os.environ.get("LOOKUP_MOST_WAIT", "") or MOST_WAIT))
    except ValueError:
        return MOST_WAIT


def wait_for_a_token(source: str, wait: float | None = None) -> str:
    """"" once a request to `source` may be sent under its rate - a token taken, after waiting up to `wait` seconds
    (`most_wait`) - else why it may not. Every run and machine of the deployment draws on one bucket per source."""
    from app.tools import lookup_store

    rate = rate_of(source)
    if rate is None:
        return ""
    wait = most_wait() if wait is None else wait
    deadline = time.monotonic() + wait
    while True:
        needed = lookup_store.take(source, *rate)
        if needed <= 0:
            return ""
        if time.monotonic() + needed > deadline:
            return f"{source}: rate of {rate[0]} requests a {_per(rate[1])} reached"
        time.sleep(needed)


def _per(seconds: float) -> str:
    return {1.0: "second", 60.0: "minute", 3_600.0: "hour"}.get(float(seconds), f"{seconds:g} seconds")


def registry_rate(url: str) -> None:
    """Wait for the token of the registry `url` is on, when that registry has a rate (`REGISTRY_HOSTS`); raises
    `RuntimeError` when none comes in time, so the caller says the registry could not be read."""
    host = (urlsplit(str(url or "")).hostname or "").lower()
    source = REGISTRY_HOSTS.get(host)
    if source:
        why = wait_for_a_token(source)
        if why:
            raise RuntimeError(why)


# --- kept values ----------------------------------------------------------------------------------------------------

def kept_public(kind: str, key: str, ask: Callable[[], Any], *, days: Callable[[Any], float | None],
                memo: dict[Hashable, Any] | None, memo_key: Hashable, shared: bool = True, scope: str = "shared",
                most: int = MOST_VALUE) -> Any:
    """The value for `key`: from the shared store when `shared` and the run may share (`lookup_store.shares`) - asked
    once however many runs ask, kept `days(value)` days (None: not kept) - else from `memo`, the asking process's own
    cache, as before the store. A value larger than `most` characters stays in `memo` alone."""
    from app.tools import lookup_store

    if memo is not None and memo_key in memo:
        return memo[memo_key]
    if shared and lookup_store.shares():
        value, was_kept = lookup_store.kept(kind, key, ask, days=days, scope=scope, most=most)
        if not was_kept and memo is not None and days(value) is not None and _larger_than(value, most):
            memo[memo_key] = value
        return value
    value = ask()
    if memo is not None and days(value) is not None:
        memo[memo_key] = value
    return value


def _larger_than(value: Any, most: int) -> bool:
    import json

    try:
        return len(json.dumps(value)) > most
    except (TypeError, ValueError):
        return True


def own_name(ecosystem: str, name: str, repo_root: str | Path | None = None) -> bool:
    """Whether `name` is the product's own (the outbound gate's rule, `outbound.refused_name`, asked without a
    record): its registry answer is never shared."""
    try:
        from app.tools import outbound

        root = outbound._workspace(repo_root)  # noqa: SLF001 - the gate's own way to find the run's workspace
        if root is None:
            return False
        own = {s for n in outbound._words_of(root)[0] for s in outbound._spellings(n)}  # noqa: SLF001
        asked = str(name or "").strip().lower()
        pieces = {asked, *(p for p in re.split(r"[/:]", asked.lstrip("@")) if p)}
        return bool(own & {s for piece in pieces for s in outbound._spellings(piece) | {piece}})  # noqa: SLF001
    except Exception:  # noqa: BLE001 - unknown is not public
        return True


def registry_answer(ecosystem: str, name: str, here: str, ask: Callable[[], dict[str, Any]], *,
                    memo: dict[Hashable, Any], memo_key: Hashable, shared: bool) -> dict[str, Any]:
    """A registry's answer about `name`'s current release, for this toolchain (`here`): shared for a public package
    name and kept `LATEST_DAYS`; an error is never kept."""
    return kept_public("registry", f"{ecosystem}\n{name}\n{here}", ask,
                       days=lambda found: LATEST_DAYS if isinstance(found, dict) and "error" not in found else None,
                       memo=memo, memo_key=memo_key, shared=shared and not own_name(ecosystem, name))


def releases_kept(ecosystem: str, name: str, ask: Callable[[], list[list[Any]] | None], *,
                  memo: dict[Hashable, Any], memo_key: Hashable, shared: bool) -> list[list[Any]] | None:
    """Every release a registry lists for `name` (None when it could not be read, never kept), kept `LATEST_DAYS`."""
    return kept_public("releases", f"{ecosystem}\n{name}", ask,
                       days=lambda found: LATEST_DAYS if found is not None else None,
                       memo=memo, memo_key=memo_key, shared=shared and not own_name(ecosystem, name))


def release_kept(ecosystem: str, name: str, version: str, ask: Callable[[], Any], *,
                 memo: dict[Hashable, Any], memo_key: Hashable, shared: bool) -> Any:
    """What one release of `name` states, kept `VERSION_DAYS`: a published release does not change."""
    return kept_public("release", f"{ecosystem}\n{name}\n{version}", ask, days=lambda _: VERSION_DAYS,
                       memo=memo, memo_key=memo_key, shared=shared and not own_name(ecosystem, name))


def document_kept(url: str, ask: Callable[[], tuple[int, str, str]], *,
                  memo: dict[Hashable, Any]) -> tuple[int, str, str]:
    """A documentation page an official index names, (status, text, content type): kept `DOCUMENT_DAYS`, a missing one
    `MISSING_DAYS`, any other answer not at all."""
    def days(found: Any) -> float | None:
        status = int(found[0]) if found else 0
        return DOCUMENT_DAYS if status == 200 else MISSING_DAYS if status in (404, 410) else None

    found = kept_public("document", url, lambda: list(ask()), days=days, memo=memo, memo_key=url)
    return int(found[0]), str(found[1]), str(found[2])


def page_scope(url: str, repo_root: str | Path | None = None) -> str:
    """"shared" for a page any tenant may be given; the tenant's own scope when the address holds its words."""
    from app.tools import lookup_store, outbound

    try:
        _, removed = outbound.without_private_words(url, outbound.private_words(repo_root),
                                                    outbound.public_names(repo_root))
    except Exception:  # noqa: BLE001 - unknown is not public
        removed = 1
    return "shared" if not removed else f"tenant-{lookup_store.tenant(repo_root)}"


def page_days(url: str) -> float:
    """Days a read of `url` is kept: `VERSIONED_PAGE_DAYS` for a versioned address, else `PAGE_DAYS`."""
    return VERSIONED_PAGE_DAYS if _VERSIONED.search(urlsplit(str(url or "")).path) else PAGE_DAYS


def page_kept(url: str, ask: Callable[[], tuple[str, str, str]]) -> tuple[str, str, str]:
    """A page read, (final address, text, why not): a read that succeeded kept `page_days`, shared when public."""
    found = kept_public("page", url, lambda: list(ask()),
                        days=lambda got: page_days(url) if got and not got[2] and got[1] else None,
                        memo=None, memo_key=url, scope=page_scope(url))
    return str(found[0]), str(found[1]), str(found[2])


# --- a run's own records --------------------------------------------------------------------------------------------

def _the_run(repo_root: str | Path | None) -> str:
    try:
        from app.models.model_pin import current_run_id

        run = current_run_id()
    except Exception:  # noqa: BLE001 - outside a run
        run = ""
    return run or str(Path(repo_root).resolve() if repo_root else "")


def once_per_run(kind: str, repo_root: str | Path | None, key: str, ask: Callable[[], Any]) -> tuple[Any, bool]:
    """(what `ask` gave for `key` in this run, whether it was given before): asked once per run whatever process,
    worker or restart of the run asks again, the record the run's own (`RUN_DAYS`), never shared or frozen."""
    from app.tools import lookup_store

    return lookup_store.kept(kind, key, ask, days=RUN_DAYS, scope=f"run-{_hash(_the_run(repo_root))}", frozen=False)


# --- paid sources ---------------------------------------------------------------------------------------------------

def paid_sources() -> frozenset[str]:
    """The sources asked only with a paid key: the general-web search providers."""
    from app.tools import lookups

    return frozenset(s.name for s in lookups.SOURCES if s.needs_key and s.general_web)


def results_kept_of() -> frozenset[str]:
    """The paid sources whose terms allow their results to be stored (`LOOKUP_PAID_RESULTS_KEPT`, default none)."""
    return frozenset(n.strip().lower() for n in os.environ.get("LOOKUP_PAID_RESULTS_KEPT", "").split(",") if n.strip())


def free_first(sources: Iterable[Any]) -> list[Any]:
    """`sources` in their order with every paid one after every free one, whatever `LOOKUP_ORDER` or a caller named."""
    listed, paid = list(sources), paid_sources()
    return [s for s in listed if s.name not in paid] + [s for s in listed if s.name in paid]


def may_keep(answer: dict[str, Any]) -> bool:
    """Whether a lookup's answer may be kept: not when it holds a paid source's results whose terms are not known to
    allow storing them."""
    given = answer.get("by_source") or {}
    allowed = results_kept_of()
    return not any(isinstance(given.get(name), int) and given[name] > 0 and name not in allowed
                   for name in paid_sources())


# --- the probe ------------------------------------------------------------------------------------------------------

def _mb(n: int) -> str:
    return f"{n / (1024 * 1024):.0f} MB"


def probe_lines() -> list[str]:
    """`loop.sh lookups`' lines on what the deployment has left: each source's daily allowance and this tenant's
    budget, each rated source's bucket, and the shared store's memory beside the queue's. Never raises."""
    lines: list[str] = []
    try:
        from app.tools import lookup_store, lookups

        today = lookup_store.requests_today()
        for source in lookups.SOURCES:
            cap, sent = lookups.daily_cap(source), today.get(source.name, 0)
            lines.append(f"LOOKUPS allowance {source.name}: {sent} of {cap} requests today ({max(0, cap - sent)} left)")
        budget, spent = lookup_store.tenant_daily_cap(), lookup_store.tenant_requests_today()
        lines.append(f"LOOKUPS allowance this tenant: {spent} of {budget} requests today")
        for name in [*RATES, *(n for n in KEYED_RATES if n not in RATES)]:
            rate = rate_of(name)
            if rate is not None:
                left = lookup_store.tokens_left(name, *rate)
                lines.append(f"LOOKUPS rate {name}: {left:.0f} of {rate[0]} tokens (refilled {rate[0]} a "
                             f"{_per(rate[1])})")
        memory = lookup_store.memory()
        if not memory:
            lines.append("LOOKUPS store: none answers - this machine's files serve; not a block")
        else:
            share, keys = lookup_store.memory_share(), lookup_store.kept_keys()
            most = memory["most"]
            full = bool(most) and memory["used"] >= share * most
            lines.append(f"LOOKUPS store memory: {_mb(memory['used'])} used of "
                         f"{_mb(most) if most else 'no limit'} ({memory['policy'] or 'no policy'}); lookups write "
                         f"below {share:.0%}; {keys} lookup keys"
                         + (" - FULL for lookups: values go to this machine's files; not a block" if full else ""))
    except Exception as exc:  # noqa: BLE001 - a probe line never stops the probe
        lines.append(f"LOOKUPS allowances: could not be read ({type(exc).__name__})")
    return lines


__all__ = ["KEYED_RATES", "LATEST_DAYS", "MOST_WAIT", "PAGE_DAYS", "RATES", "REGISTRY_HOSTS", "RUN_DAYS",
           "VERSIONED_PAGE_DAYS", "VERSION_DAYS", "document_kept", "free_first", "kept_public", "may_keep",
           "most_wait", "once_per_run", "own_name", "page_days", "page_kept", "page_scope", "paid_sources",
           "probe_lines", "rate_of", "registry_answer", "registry_rate", "release_kept", "releases_kept",
           "results_kept_of", "wait_for_a_token"]
