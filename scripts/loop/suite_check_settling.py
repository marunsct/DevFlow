"""How often each harness check of the acceptance suite was right, across every stored run (harness review Q1).

    scripts/loop/loop.sh suite-checks   (runs this inside the worker)

Reads every workspace's `.harness/check-findings.jsonl` (written by `app.acceptance.check_findings`). A finding is
**settled** when the same check's same finding (its fingerprint) is not raised again in a later review round of
that run - the writers changed the test and the check agreed - and **repeated** when it comes back. A check whose
findings keep coming back is either right and ignored or wrong; either way it is costing rounds, and below about
0.8 settled it is a candidate to demote to a note. Report only; it changes nothing.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

DEMOTE_BELOW = 0.8
LEAST_FINDINGS = 5


def findings_of(workspace: Path) -> list[dict]:
    path = workspace / ".harness" / "check-findings.jsonl"
    rows = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    except OSError:
        pass
    return rows


def settle(rows: list[dict]) -> list[tuple[str, bool]]:
    """(check, settled) for each finding: settled when no later round of the run raised it again."""
    out = []
    for row in rows:
        later = any(other["check"] == row["check"] and other["fingerprint"] == row["fingerprint"]
                    and int(other.get("round", 0)) > int(row.get("round", 0)) for other in rows)
        out.append((str(row.get("check")), not later))
    return out


filters: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)


def report(workspaces: Path) -> dict[str, dict]:
    totals: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for workspace in sorted(workspaces.glob("workspace-run-*")):
        every = findings_of(workspace)
        # A review filter's work (HR2.G.1) is counted apart: dropped, demoted, and verdicts relabelled.
        for row in every:
            if row.get("kind") == "filtered":
                counts = filters[str(row.get("check"))]
                counts["dropped" if row.get("severity_after") == "dropped" else "moved"] += 1
                counts["relabelled" if row.get("verdict_before") != row.get("verdict_after") else "same verdict"] += 1
        rows = [row for row in every if row.get("kind") != "filtered"]
        if not rows:
            continue
        for check, settled in settle(rows):
            totals[check]["findings"] += 1
            totals[check]["settled" if settled else "repeated"] += 1
        for check in {str(r.get("check")) for r in rows}:
            totals[check]["runs"] += 1
    return {check: dict(counts) for check, counts in totals.items()}


def main(argv: list[str]) -> int:
    where = Path(argv[1]) if len(argv) > 1 else Path("/app/data/workspaces/default")
    found = report(where)
    if not found and not filters:
        print("check precision: no run has recorded a check finding yet")
        return 0
    for check, counts in sorted(found.items(), key=lambda item: -item[1].get("findings", 0)):
        share = counts.get("settled", 0) / counts["findings"]
        verdict = ("DEMOTE CANDIDATE" if share < DEMOTE_BELOW and counts["findings"] >= LEAST_FINDINGS
                   else "too few to judge" if counts["findings"] < LEAST_FINDINGS else "holds")
        print(f"{check:<48} findings {counts['findings']:>4} runs {counts.get('runs', 0):>3} "
              f"settled {share:.2f}  {verdict}")
    for check, counts in sorted(filters.items()):
        print(f"{check:<48} filtered: {counts.get('dropped', 0)} dropped, {counts.get('moved', 0)} moved, "
              f"{counts.get('relabelled', 0)} verdict line(s) relabelled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
