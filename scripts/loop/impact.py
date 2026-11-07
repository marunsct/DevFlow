"""Whether each harness change made the runs after it better or worse, read from the KPI ledger.

    python scripts/loop/impact.py [data/kpi/ledger.csv] [N]

For each of the last N changes (commits whose subject names an LF item, default 12) the runs that
finished on that change or later are set against the runs that finished before it. Families differ
in size, so every run after the change is measured against the median of its own family before it,
and the report gives the median of those ratios. A KPI that got worse by more than a quarter, or a
hidden score that fell, is flagged. Reports only; it never changes anything.
"""
from __future__ import annotations

import csv
import re
import statistics
import subprocess
import sys
from pathlib import Path

#: (column, more is worse). Hidden score and fix rate are better when higher.
KPIS = (
    ("hidden_score", False),
    ("fix_rate", False),
    ("active_minutes", True),
    ("defect_fix_stages", True),
    ("defects_left_open", True),
    ("test_rounds", True),
    ("output_tokens", True),
    ("tool_failure_rate", True),
    ("model_errors", True),
    # The product's own quality beside the hidden score (HR2.E.5): the locked suite's mutation score and the
    # family's quality set; both existed in the ledger and were in no comparison.
    ("mutation_score", False),
    ("quality_score", False),
    ("replies_lost_to_length", True),
)
WORSE_BY = 1.25
#: Runs after a change before a KPI other than the hidden score may be called worse; one run is a watch. Measured:
#: seven changes in a row were each "worse" from the one run after them, whose wall held a nine-hour pause.
LEAST_RUNS_AFTER = 2
BEFORE_RUNS = 12


def _number(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def value(row, kpi):
    if kpi == "fix_rate":
        stages = _number(row.get("defect_fix_stages"))
        fixed = _number(row.get("defects_fixed"))
        return None if not stages or fixed is None else fixed / stages
    return _number(row.get(kpi))


def finished_on(row, position):
    """The place in history of the last harness version a run ran on, or None when it is unknown."""
    places = [position[c] for c in (row.get("harness_commits") or "").split() if c in position]
    return max(places) if places else None


def started_on(row, position):
    """The place in history of the first harness version a run ran on, or None when it is unknown."""
    places = [position[c] for c in (row.get("harness_commits") or "").split() if c in position]
    return min(places) if places else None


def compare(rows, at, position):
    """Each KPI's median ratio, after the change at place `at`, to its family's median before it.

    A run counts after the change only if it started on it or later, and before it only if it finished before it:
    a run the change was deployed into part-way is neither (harness review E1). Measured: a run was filed by the
    last version it ran on, so a run that ran three hours on the old code and ten minutes on the new counted as
    the change's - most of the ledger's rows are mixed.
    """
    placed = [(started_on(r, position), finished_on(r, position), r) for r in rows]
    before = [r for _, last, r in placed if last is not None and last < at][-BEFORE_RUNS:]
    after = [r for first, _, r in placed if first is not None and first >= at]
    spanning = sum(1 for first, last, _ in placed if first is not None and last is not None and first < at <= last)
    report = {"before": len(before), "after": len(after), "spanning": spanning, "kpis": {}}
    for kpi, worse_when_higher in KPIS:
        ratios = []
        for run in after:
            mine = value(run, kpi)
            theirs = [v for v in (value(r, kpi) for r in before if r.get("benchmark") == run.get("benchmark"))
                      if v is not None]
            if mine is None or not theirs:
                continue
            base = statistics.median(theirs)
            if base == 0:
                ratios.append(1.0 if mine == 0 else (WORSE_BY * 2 if worse_when_higher else 1.0))
            else:
                ratios.append(mine / base)
        if not ratios:
            continue
        ratio = statistics.median(ratios)
        if kpi == "hidden_score":
            worse, watch = min(ratios) < 1.0, False
        else:
            beyond = ratio > WORSE_BY if worse_when_higher else ratio < 1 / WORSE_BY
            worse, watch = beyond and len(ratios) >= LEAST_RUNS_AFTER, beyond and len(ratios) < LEAST_RUNS_AFTER
        report["kpis"][kpi] = {"ratio": round(ratio, 2), "runs": len(ratios), "worse": worse, "watch": watch}
    return report


def changes(limit):
    """(place, sha, subject) of the last `limit` commits naming an LF item, oldest first, and every commit's place."""
    shas = subprocess.run(["git", "rev-list", "--reverse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.split()
    position = {sha: n for n, sha in enumerate(shas)}
    log = subprocess.run(["git", "log", "--format=%H %s", "-n", "400"], capture_output=True, text=True,
                         check=True).stdout.splitlines()
    named = [(position[s], s, subj) for s, _, subj in (line.partition(" ") for line in log)
             if s in position and re.search(r"\(LF\.\d+", subj) and not subj.startswith("STATE")]
    return sorted(named)[-limit:], position


def main(argv):
    ledger = Path(argv[1]) if len(argv) > 1 else Path("data/kpi/ledger.csv")
    limit = int(argv[2]) if len(argv) > 2 else 12
    rows = list(csv.DictReader(ledger.open()))
    found, position = changes(limit)
    flagged = 0
    for at, sha, subject in found:
        report = compare(rows, at, position)
        item = re.search(r"LF\.\d+(?:, LF\.\d+)*", subject)
        name = item.group(0) if item else sha[:8]
        parts = []
        for kpi, seen in report["kpis"].items():
            mark = " WORSE" if seen["worse"] else (" watch" if seen.get("watch") else "")
            flagged += bool(seen["worse"])
            parts.append(f"{kpi} x{seen['ratio']}{mark}")
        print(f"{name:<18} {sha[:8]} runs before {report['before']:>2} after {report['after']:>2} spanning {report.get('spanning', 0):>2}: "
              + (", ".join(parts) or "no run after it yet"))
    print(f"impact: {flagged} KPI(s) worse after a change" if flagged else "impact: nothing worse after any change")


if __name__ == "__main__":
    main(sys.argv)
