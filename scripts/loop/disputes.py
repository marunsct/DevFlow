"""How each run's suite disputes ended, totalled per family and joined to the hidden score (harness review HR2.Q.4).

    scripts/loop/loop.sh disputes

Two legs. Inside the worker (`python3 - <workspaces dir>`) it prints one JSON line per run from each workspace's
`.harness/dispute-outcomes.jsonl` (written by `app.graph.dispute_outcomes`). On the host (`--join <ledger.csv>`) it
reads those lines from stdin, joins each run's family and hidden score from the ledger, and prints the totals.
Report only; it changes nothing.
"""
from __future__ import annotations

import collections
import csv
import json
import sys
from pathlib import Path

KEYS = ("shown", "called_wrong", "refused", "passed_alone", "service_stopped", "past_the_cap", "missing", "reopened_tests")


def per_run(workspaces: Path) -> list[dict]:
    rows = []
    for workspace in sorted(workspaces.glob("workspace-run-*")):
        path = workspace / ".harness" / "dispute-outcomes.jsonl"
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        totals = collections.Counter()
        disputes = 0
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            disputes += 1
            for key in KEYS:
                totals[key] += len(row.get(key) or [])
        rows.append({"run": workspace.name.removeprefix("workspace-"), "disputes": disputes, **{k: totals[k] for k in KEYS}})
    return rows


def joined(rows: list[dict], ledger: Path) -> str:
    scores: dict[str, tuple[str, str]] = {}
    try:
        with ledger.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                scores[row.get("run", "")] = (row.get("benchmark") or "?", row.get("hidden_score") or "")
    except OSError:
        pass
    out = ["run                                       family                disputes " + " ".join(k[:8] for k in KEYS) + " hidden"]
    families: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for row in rows:
        family, hidden = scores.get(row["run"], ("?", ""))
        families[family]["runs"] += 1
        for key in ("disputes", *KEYS):
            families[family][key] += row[key]
        out.append(f"{row['run']:<42}{family:<22}{row['disputes']:>8} " + " ".join(f"{row[k]:>8}" for k in KEYS) + f" {hidden}")
    out.append("")
    out.append("per family: " + "; ".join(
        f"{family} {c['runs']} run(s), {c['disputes']} dispute(s), {c['called_wrong']} called wrong, "
        f"{c['refused']} refused, {c['passed_alone']} passed alone, {c['reopened_tests']} reopened"
        for family, c in sorted(families.items())
    ) if families else "no dispute recorded yet (recorded from LF.699 on)")
    return "\n".join(out)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--join":
        print(joined([json.loads(line) for line in sys.stdin if line.strip()], Path(sys.argv[2])))
    else:
        for row in per_run(Path(sys.argv[1] if len(sys.argv) > 1 else "/app/data/workspaces/default")):
            print(json.dumps(row))
