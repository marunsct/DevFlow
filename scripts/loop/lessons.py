"""Lessons: propose this run's from what the harness recorded, or list the proposals (plans RL.1, RL.3).

Runs INSIDE the worker, where the transcripts and the lessons store live:

    docker compose exec -T worker python - distil <run> < scripts/loop/lessons.py
    docker compose exec -T worker python - list < scripts/loop/lessons.py

or `loop.sh lessons [distil <run>]`. Distilling does nothing unless
`LESSON_DISTILLER` is on; listing always shows the proposals awaiting the owner.
`evidence` reads every transcript into the lessons on record and names those no
transcript backs.
"""
from __future__ import annotations

import glob
import sys
from pathlib import Path

from app.plugins import lessons
from app.plugins.lesson_distiller import check_the_evidence, distil


def main(argv: list[str]) -> int:
    if len(argv) > 2 and argv[1] == "distil":
        run = argv[2]
        transcripts = sorted(glob.glob(f"/app/data/transcripts/{run}*.jsonl"))
        roots = sorted(glob.glob(f"/app/data/workspaces/*/workspace-{run}"))
        if not transcripts or not roots:
            print(f"no transcript or workspace for {run}")
            return 1
        done = distil(transcripts[0], roots[0])
        print(f"{len(done)} lesson(s) proposed or refreshed" if done else "nothing proposed (or LESSON_DISTILLER is off)")
        return 0
    if len(argv) > 1 and argv[1] == "evidence":
        pairs = []
        for transcript in sorted(glob.glob("/app/data/transcripts/*.jsonl")):
            roots = glob.glob(f"/app/data/workspaces/*/workspace-{Path(transcript).stem}")
            if roots:
                pairs.append((transcript, roots[0]))
        without = check_the_evidence(pairs)
        for lesson in lessons.load():
            print(f"  {lesson['id']} {lesson['status']} [{lesson['stack']}] {lesson['evidence_runs']} run(s): {lesson['trigger']}")
        print(f"{len(pairs)} run(s) read; no evidence for: {', '.join(item['id'] for item in without) or 'none'}")
        return 0
    waiting = [lesson for lesson in lessons.load() if lesson.get("status") == "proposed"]
    print(f"{len(waiting)} lesson(s) awaiting the owner")
    for lesson in waiting:
        print(f"  {lesson['id']} [{lesson['stack']}] when {lesson['trigger']}: {lesson['rule']}")
    for lesson in lessons.load():
        if lesson.get("recurred_runs"):
            print(f"  {lesson['id']} approved, its trigger recurred on {lesson['recurred_runs']} run(s) since")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
