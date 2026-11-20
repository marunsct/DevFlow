"""Whether each outside source the harness looks things up in answers, asked live (plan WL.7). Runs in the worker.

    scripts/loop/loop.sh lookups          (also printed by `loop.sh ready`, above its verdict)

Measured 2026-11-20: the private search's general engines had refused every query for weeks and nothing noticed -
the container's health check tests only that it is up. Each source here is asked one fixed, generic question with the
cache bypassed; one line per source says whether it answered, how many results and how long it took. A warning, never a
block: `ready`'s last line is the model's verdict alone, and a source that does not answer only means lookups for a
stuck fixer find less. Exits 0 always.
"""
from __future__ import annotations

import time

#: A question every source has answers for: generic, no product's words in it.
QUESTION = "TypeError: Cannot read properties of undefined reading map"


def _ask(name: str, ask) -> str:
    started = time.monotonic()
    try:
        found = ask()
    except Exception as exc:  # noqa: BLE001 - a source that cannot be asked is the answer
        return f"LOOKUPS {name}: NO ANSWER ({type(exc).__name__}: {str(exc)[:80]}) - lookups find less; not a block"
    took = time.monotonic() - started
    if not found:
        return f"LOOKUPS {name}: NO ANSWER (nothing found in {took:.1f}s) - lookups find less; not a block"
    return f"LOOKUPS {name}: answers ({found} result(s) in {took:.1f}s)"


def main() -> int:
    from app.tools import lookups, package_registry, web_search

    lines = [
        _ask("stack exchange", lambda: len(lookups.stack_exchange(QUESTION, lookups._get))),  # noqa: SLF001
        _ask("github issues", lambda: len(lookups.github_issues(QUESTION, lookups._get))),  # noqa: SLF001
        _ask("private search", lambda: len((web_search.search(QUESTION).get("results") or []))
             if web_search.enabled() else 0),
        _ask("package registry", lambda: 1 if package_registry.look_up("npm", "express").get("version") else 0),
    ]
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
