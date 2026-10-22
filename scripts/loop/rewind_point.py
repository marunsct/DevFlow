"""The checkpoint to rewind a run to, from its rewind points.

Reads `GET /api/runs/<id>/rewind-points` as JSON on stdin; prints the
`checkpoint_id` of the stage named, and the point on stderr.

    curl .../rewind-points | python3 rewind_point.py test_and_triage [2026-10-19T22:20]

The stage is a graph stage as the points name it (`principal_architect`,
`acceptance_author`, `technical_lead`, `test_and_triage`, ...). With a time,
the last entry of that stage at or before it - the moment before a bug; without
one, its latest entry. Exits 1, listing the points, when none matches.
"""
from __future__ import annotations

import json
import sys


def the_point(points: list[dict], stage: str, before: str = "") -> dict | None:
    matching = [p for p in points if str(p.get("stage")) == stage]
    if before:
        matching = [p for p in matching if str(p.get("at", ""))[: len(before)] <= before]
    return matching[-1] if matching else None


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    stage, before = argv[1], argv[2] if len(argv) > 2 else ""
    points = (json.load(sys.stdin) or {}).get("points") or []
    point = the_point(points, stage, before)
    if point is None:
        print(f"no rewind point for {stage!r}{' at or before ' + before if before else ''}; the run's points:", file=sys.stderr)
        for p in points:
            print(f"  {p.get('at', '')[:19]}  {p.get('stage')}  (sprint {p.get('sprint')})", file=sys.stderr)
        return 1
    print(f"rewinding to {point.get('stage')} entered at {str(point.get('at', ''))[:19]} UTC "
          f"(sprint {point.get('sprint')})", file=sys.stderr)
    print(point["checkpoint_id"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
