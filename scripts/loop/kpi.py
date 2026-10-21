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

import glob
import json
import sys

# The computation lives in the application now, so the run page answers the
# same numbers (plan UI-S6); this script reads a transcript file and prints them.
from app.observability.run_kpis import (  # noqa: F401 - re-exported for the tests and older callers
    FAIL,
    HEAD_CHARS,
    INVALID_TOOL,
    LAYERS,
    ORPHAN_GAP_SECONDS,
    READS,
    REDUNDANT,
    TAIL_CHARS,
    kpis,
)


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
    from app.observability.run_kpis import per_accepted_criterion

    print(json.dumps({"run": run, **per_accepted_criterion(kpis(records), accepted_criteria(run)), **owner_rating(run)}))
    return 0


def accepted_criteria(run: str) -> int | None:
    """How many criteria the run's last acceptance result passes, or None when it has none (plan MF.3)."""
    paths = glob.glob(f"/app/data/workspaces/*/workspace-{run}/.harness/acceptance-result.json")
    try:
        result = json.load(open(paths[0])) if paths else None
    except (OSError, ValueError):
        return None
    if not isinstance(result, dict) or not result.get("ran"):
        return None
    return sum(1 for c in (result.get("criteria") or {}).values() if (c or {}).get("status") == "passed")



def owner_rating(run: str, root: str = "/app/data") -> dict:
    """The owner's rating of the delivered run, 1-5 and a line, for its KPI row (plan EV.1); empty when unrated."""
    try:
        rating = json.load(open(f"{root}/ratings/{run}.json"))
    except (OSError, ValueError):
        return {"owner_rating": "", "owner_note": ""}
    return {"owner_rating": rating.get("score", ""), "owner_note": " ".join(str(rating.get("note") or "").split())[:200]}

if __name__ == "__main__" and len(sys.argv) > 1:
    raise SystemExit(main(sys.argv[1]))
