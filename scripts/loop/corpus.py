"""Harvest one run's reader inputs into the corpus (plan RC.1). Runs INSIDE the worker, where transcripts live:

    docker compose exec -T worker python - <run-id> < scripts/loop/corpus.py
"""
from __future__ import annotations

import glob
import json
import sys

from app.observability.reader_corpus import harvest, sizes


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
    print(json.dumps({"run": run, "added": harvest(records), "sizes": sizes()}))
    return 0


if __name__ == "__main__" and len(sys.argv) > 1:
    raise SystemExit(main(sys.argv[1]))
