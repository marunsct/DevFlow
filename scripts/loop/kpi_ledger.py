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
#: The least a KPI must reach to be flagged, so a rate moving from 0.1% to 0.2%
#: is not a regression and a count going from 0 to 3 is (Initiative AN).
FLOOR = {
    "tool_failure_rate": 0.02, "redundant_read_rate": 0.02, "identical_call_rate": 0.02,
    "unknown_tool_name_rate": 0.01, "replies_lost_to_length": 1, "model_errors": 1,
    "fixes_reverted": 1, "defects_left_open": 1, "prefill_decode_ratio": 1.0,
    "lost_reply_output_share": 0.02, "invalid_tool_call_rate": 0.01,
}
WORSE_WHEN_HIGHER = (*WORSE_WHEN_HIGHER, "lost_reply_output_share", "invalid_tool_call_rate")


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
        if now >= FLOOR.get(key, 0) and now > FACTOR * mean:
            flagged.append(f"{key}: {now:g} against a {len(values)}-run mean of {mean:.3g}")
    return flagged


def append(ledger: Path, row: dict) -> list[dict]:
    """The ledger's rows before this run's, after writing this run's in."""
    rows: list[dict] = []
    if ledger.exists():
        with ledger.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
    # Scalars only: the per-stage block stays in the run's own JSON.
    row = {k: v for k, v in row.items() if not isinstance(v, (list, dict))}
    earlier = [r for r in rows if r.get("run") != row.get("run")]
    columns = list(dict.fromkeys([*row, *(k for r in earlier for k in r)]))
    ledger.parent.mkdir(parents=True, exist_ok=True)
    # Written beside the ledger and moved over it, so a worker that dies
    # mid-write leaves the old ledger and not half of a new one.
    temporary = ledger.with_name(ledger.name + ".tmp")
    with temporary.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, restval="")
        writer.writeheader()
        writer.writerows([*earlier, row])
    temporary.replace(ledger)
    # Compared with runs of the same benchmark only: a bench and a real brief
    # have different shapes, and a mixed window flags nothing useful.
    kind = str(row.get("benchmark") or "")
    return [r for r in earlier if str(r.get("benchmark") or "") == kind]


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


#: Runs each arm needs before two harness versions are compared (plan MF.5, Part 20's two-run rule).
MINIMUM_RUNS_PER_ARM = 2


def _numbers(rows: list[dict], key: str) -> list[float]:
    values = []
    for r in rows:
        try:
            value = float(r.get(key, "nan"))
        except (TypeError, ValueError):
            continue
        if value == value:
            values.append(value)
    return values


def the_arm(rows: list[dict], commit: str, benchmark: str = "") -> list[dict]:
    """The ledger's runs on exactly one harness commit, a mixed run left out (plans MF.1, MF.5)."""
    return [
        r for r in rows
        if str(r.get("harness_commits") or "").split() == [commit]
        and str(r.get("mixed_versions") or "False") != "True"
        and (not benchmark or str(r.get("benchmark") or "") == benchmark)
    ]


def compare_arms(a: list[dict], b: list[dict], minimum: int = MINIMUM_RUNS_PER_ARM) -> list[str]:
    """Each numeric KPI's mean and spread (min-max) on two arms of runs; refused below `minimum` runs an arm."""
    if len(a) < minimum or len(b) < minimum:
        return [f"not compared: {len(a)} and {len(b)} run(s); each arm needs at least {minimum}"]
    out = [f"{'kpi':<34} {'arm A (n=' + str(len(a)) + ')':>24} {'arm B (n=' + str(len(b)) + ')':>24}"]
    for key in sorted({k for r in [*a, *b] for k in r}):
        x, y = _numbers(a, key), _numbers(b, key)
        if len(x) < minimum or len(y) < minimum:
            continue
        mx, my = sum(x) / len(x), sum(y) / len(y)
        change = "" if mx == 0 else f" ({(my - mx) / abs(mx):+.0%})"
        out.append(f"{key:<34} {mx:>12.4g} [{min(x):g}-{max(x):g}] {my:>12.4g} [{min(y):g}-{max(y):g}]{change}")
    return out


def main(path: str, ledger: str = "data/kpi/ledger.csv", benchmark: str = "") -> int:
    row = json.loads(Path(path).read_text())
    if benchmark:
        row["benchmark"] = benchmark
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
    if sys.argv[1] == "arms" and len(sys.argv) >= 5:
        # python kpi_ledger.py arms data/kpi/ledger.csv <commit-a> <commit-b> [benchmark]
        with open(sys.argv[2], newline="") as handle:
            rows = list(csv.DictReader(handle))
        kind = sys.argv[5] if len(sys.argv) > 5 else ""
        print("\n".join(compare_arms(the_arm(rows, sys.argv[3], kind), the_arm(rows, sys.argv[4], kind))))
        raise SystemExit(0)
    raise SystemExit(main(*sys.argv[1:4]))
