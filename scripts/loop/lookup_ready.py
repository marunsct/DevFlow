"""Whether each outside source the harness looks things up in answers, asked live (plan WL.7). Runs in the worker.

    scripts/loop/loop.sh lookups          (also printed by `loop.sh ready`, above its verdict)

Measured 2026-11-20: the private search's general engines had refused every query for weeks and nothing noticed -
the container's health check tests only that it is up. Each source here is asked one fixed, generic question with the
cache bypassed; one line per source says whether it answered, how many results and how long it took. An optional
source with no key, or one at its daily request cap (plan WL.6), says so instead of being asked. Then (KS.6,
`app.tools.source_health`): each engine of the private search that did not answer, Stack Exchange's and GitHub's
allowances left, and the page reader on one page of each kind a lookup reads - a file on a code host, a documentation
page, a question and its answers - in place of example.com, which never failed the way they do. Then (HK.12,
`app.tools.lookup_service`): each source's daily allowance used and this tenant's budget, each rated source's tokens
left, and the shared store's memory beside the queue's (`maxmemory`, its policy, the lookups' keys). A warning, never a
block: `ready`'s last line is the model's verdict alone, and a source that does not answer only means lookups for a
stuck fixer find less. Exits 0 always. No key is ever printed.
"""
from __future__ import annotations

import time

#: A question every source has answers for: generic, no product's words in it.
QUESTION = "TypeError: Cannot read properties of undefined reading map"
#: The library the question is about, for a source that looks up a library's documentation.
LIBRARY = "node"


def _ask(name: str, ask) -> str:
    from app.tools.lookups import without_keys

    started = time.monotonic()
    try:
        found = ask()
    except Exception as exc:  # noqa: BLE001 - a source that cannot be asked is the answer
        return without_keys(f"LOOKUPS {name}: NO ANSWER ({type(exc).__name__}: {str(exc)[:80]}) - lookups find less; "
                            "not a block")
    took = time.monotonic() - started
    if not found:
        return f"LOOKUPS {name}: NO ANSWER (nothing found in {took:.1f}s) - lookups find less; not a block"
    return f"LOOKUPS {name}: answers ({found} result(s) in {took:.1f}s)"


def _source_lines() -> list[str]:
    from app.tools import lookups, web_search

    lines = []
    for source in lookups.ordered_sources():
        why = lookups.state(source)
        if why == "no key":
            lines.append(f"LOOKUPS {source.name}: no key (optional; asked only with one)")
        elif why:
            lines.append(f"LOOKUPS {source.name}: {why} - skipped until tomorrow (UTC); not a block")
        elif source.name == "private search" and not web_search.enabled():
            lines.append(_ask(source.name, lambda: 0))
        else:
            lines.append(_ask(source.name, lambda s=source: len(lookups.ask(s, QUESTION, LIBRARY))))
    return lines


def main() -> int:
    from app.tools import lookup_service, lookup_store, package_registry, source_health

    # Asked live: nothing the shared store keeps is read (plan HK.12), so a source that stopped answering shows here.
    with lookup_store.fresh():
        lines = [
            *_source_lines(),
            _ask("package registry", lambda: 1 if package_registry.look_up("npm", "express").get("version") else 0),
            *source_health.lines(),
            *lookup_service.probe_lines(),
        ]
    for line in lines:
        print(line)
    # How much of the Redis the queue shares the run histories hold (LF.1507), beside the store's memory line.
    from app.server import event_history
    from app.server.redis_client import get_redis_client

    print(event_history.memory_line(get_redis_client()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
