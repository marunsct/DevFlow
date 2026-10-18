"""Keep one run's KPIs beside the runs before it, and say which got worse (Initiative W.4).

    python scripts/loop/kpi_ledger.py data/kpi/<run>.json [data/kpi/ledger.csv]

Appends the run's row to the ledger (a run already there is replaced) and
prints each KPI more than 1.5x its average over the five runs before it.
Higher is worse for every KPI flagged here; the ones where higher is better
(cached-token share, model busy share, defects fixed) and plain sizes (wall
time, tokens, calls) are kept in the ledger but never flagged.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

#: Rates and counts where more is worse.
WORSE_WHEN_HIGHER = (
    "tool_failure_rate",
    "redundant_read_rate",
    "identical_call_rate",
    "unknown_tool_name_rate",
    "replies_lost_to_length",
    "model_errors",
    "fixes_reverted",
    "defects_left_open",
    "prefill_decode_ratio",
)
WINDOW = 5
FACTOR = 1.5


def regressions(earlier: list[dict], row: dict) -> list[str]:
    """Each KPI of `row` past FACTOR x its mean over the last WINDOW rows of `earlier`."""
    flagged = []
    recent = earlier[-WINDOW:]
    for key in WORSE_WHEN_HIGHER:
        values = [float(r[key]) for r in recent if str(r.get(key, "")).strip() not in ("", "None")]
        if not values or key not in row:
            continue
        mean = sum(values) / len(values)
        now = float(row[key])
        if mean > 0 and now > FACTOR * mean:
            flagged.append(f"{key}: {now:g} against a {len(values)}-run mean of {mean:.3g}")
    return flagged


def append(ledger: Path, row: dict) -> list[dict]:
    """The ledger's rows before this run's, after writing this run's in."""
    rows: list[dict] = []
    if ledger.exists():
        with ledger.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
    earlier = [r for r in rows if r.get("run") != row.get("run")]
    columns = list(dict.fromkeys([*row, *(k for r in earlier for k in r)]))
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, restval="")
        writer.writeheader()
        writer.writerows([*earlier, row])
    return earlier


def compare(a: dict, b: dict) -> list[str]:
    """Each numeric KPI of run `a` beside run `b`, with the change (Initiative U.3)."""
    out = []
    for key in sorted(set(a) | set(b)):
        try:
            x, y = float(a.get(key, "nan")), float(b.get(key, "nan"))
        except (TypeError, ValueError):
            continue
        change = "" if x != x or y != y or x == 0 else f" ({(y - x) / abs(x):+.0%})"
        out.append(f"{key:<28} {x:>14g} {y:>14g}{change}")
    return out


def main(path: str, ledger: str = "data/kpi/ledger.csv") -> int:
    row = json.loads(Path(path).read_text())
    earlier = append(Path(ledger), row)
    flagged = regressions(earlier, row)
    for line in flagged:
        print("REGRESSION " + line)
    if not flagged:
        print(f"no KPI past {FACTOR}x its {WINDOW}-run mean ({len(earlier)} earlier run(s) in {ledger})")
    return 0


if __name__ == "__main__" and len(sys.argv) > 1:
    if sys.argv[1] == "compare" and len(sys.argv) == 4:
        # python kpi_ledger.py compare data/kpi/<A>.json data/kpi/<B>.json
        print("\n".join(compare(*(json.loads(Path(f).read_text()) for f in sys.argv[2:4]))))
        raise SystemExit(0)
    raise SystemExit(main(*sys.argv[1:3]))
