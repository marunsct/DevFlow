"""How far the harness's own "done" can be trusted, across every scored run.

    python scripts/bench/report.py [data/bench]

Reads the results `score.py` wrote and prints, per benchmark: runs scored,
runs the harness finished, runs whose product passed every hidden test, and
false acceptances - runs the harness finished whose product fails hidden
tests. A pass rate alone hides that last number, and it is the one that says
whether a finished run can be handed over unread. Results scored before the
harness verdict was recorded show its status as unknown.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path


def summarise(results: list[dict]) -> dict[str, dict]:
    """Per benchmark: scored, finished, perfect, false acceptances, and the mean score."""
    table: dict[str, dict] = defaultdict(lambda: {
        "scored": 0, "finished": 0, "perfect": 0, "false_acceptances": 0, "unknown": 0, "scores": [],
        "brief_mismatch": 0,
    })
    for result in results:
        row = table[str(result.get("benchmark") or "?")]
        if result.get("brief_mismatch"):
            # Scored against a suite written for another brief: it measures
            # the pairing, so it is counted apart and in nothing else.
            row["brief_mismatch"] += 1
            continue
        status = (result.get("harness") or {}).get("status", "unknown")
        row["scored"] += 1
        row["scores"].append(float(result.get("score") or 0.0))
        row["perfect"] += float(result.get("score") or 0.0) >= 1.0
        row["finished"] += status == "completed"
        row["unknown"] += status == "unknown"
        row["false_acceptances"] += bool(result.get("false_acceptance"))
    for row in table.values():
        scores = row.pop("scores")
        row["mean_score"] = round(sum(scores) / len(scores), 3) if scores else 0.0
        row["false_acceptance_rate"] = (
            round(row["false_acceptances"] / row["finished"], 3) if row["finished"] else None
        )
    return dict(table)


def main(directory: Path) -> int:
    results = []
    for path in sorted(directory.glob("*.json")):
        try:
            results.append(json.loads(path.read_text()))
        except (OSError, ValueError):
            print(f"skipped unreadable {path.name}", file=sys.stderr)
    if not results:
        print(f"no scored runs in {directory}")
        return 0
    print(f"{'benchmark':22} {'scored':>6} {'finished':>8} {'perfect':>7} {'false acc.':>10} {'rate':>6} {'mean':>6} {'unknown':>7} {'mismatch':>8}")
    for name, row in sorted(summarise(results).items()):
        rate = "-" if row["false_acceptance_rate"] is None else f"{row['false_acceptance_rate']:.0%}"
        print(
            f"{name:22} {row['scored']:>6} {row['finished']:>8} {row['perfect']:>7} "
            f"{row['false_acceptances']:>10} {rate:>6} {row['mean_score']:>6.0%} {row['unknown']:>7} {row['brief_mismatch']:>8}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "data/bench")))
