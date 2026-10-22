"""How far the harness's own "done" can be trusted, across every scored run.

    python scripts/bench/report.py [data/bench]

Reads the results `score.py` wrote and prints, per benchmark: runs scored,
runs the harness finished, runs whose product passed every hidden test, and
false acceptances - runs the harness finished whose product fails hidden
tests. A pass rate alone hides that last number, and it is the one that says
whether a finished run can be handed over unread. Results scored before the
harness verdict was recorded show its status as unknown.

Beside the hidden score, the owner's own rating of the delivered product (plan
EV.1): the mean of the runs rated, from each run's KPI row (`data/kpi/<run>.json`),
and how many were rated. Tests say whether it works; the rating says whether it
is any good.
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
        "brief_mismatch": 0, "ratings": [],
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
        if isinstance(result.get("owner_rating"), (int, float)) and not isinstance(result.get("owner_rating"), bool):
            row["ratings"].append(float(result["owner_rating"]))
    for row in table.values():
        scores, ratings = row.pop("scores"), row.pop("ratings")
        row["rated"] = len(ratings)
        row["mean_rating"] = round(sum(ratings) / len(ratings), 2) if ratings else None
        row["mean_score"] = round(sum(scores) / len(scores), 3) if scores else 0.0
        row["false_acceptance_rate"] = (
            round(row["false_acceptances"] / row["finished"], 3) if row["finished"] else None
        )
    return dict(table)


def _rating(run: str, kpi_directory: Path) -> int | None:
    """The owner's rating in the run's KPI row, or None."""
    try:
        rating = json.loads((kpi_directory / f"{run}.json").read_text()).get("owner_rating")
    except (OSError, ValueError, AttributeError):
        return None
    return rating if isinstance(rating, int) and not isinstance(rating, bool) and 1 <= rating <= 5 else None


def main(directory: Path, kpi_directory: Path = Path("data/kpi")) -> int:
    results = []
    for path in sorted(directory.glob("*.json")):
        try:
            results.append({**json.loads(path.read_text()), "owner_rating": _rating(path.stem, kpi_directory)})
        except (OSError, ValueError):
            print(f"skipped unreadable {path.name}", file=sys.stderr)
    if not results:
        print(f"no scored runs in {directory}")
        return 0
    print(f"{'benchmark':22} {'scored':>6} {'finished':>8} {'perfect':>7} {'false acc.':>10} {'rate':>6} {'mean':>6} {'unknown':>7} {'mismatch':>8} {'rating':>8}")
    for name, row in sorted(summarise(results).items()):
        rate = "-" if row["false_acceptance_rate"] is None else f"{row['false_acceptance_rate']:.0%}"
        rating = "-" if row["mean_rating"] is None else f"{row['mean_rating']:.1f} ({row['rated']})"
        print(
            f"{name:22} {row['scored']:>6} {row['finished']:>8} {row['perfect']:>7} "
            f"{row['false_acceptances']:>10} {rate:>6} {row['mean_score']:>6.0%} {row['unknown']:>7} {row['brief_mismatch']:>8} {rating:>8}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "data/bench")))
