"""The prompt-cache share and the prefix breaks of one run, from its transcript, in a few lines.

Runs INSIDE the worker container, where the transcripts are (`/app/data/transcripts/<run-id>*.jsonl`), piped in on
stdin like `audit_live.py`:

    docker compose exec -T worker python - <run-id> < scripts/loop/cache_status.py

`loop.sh status` runs it after the run's row. The numbers are `app.observability.cache_report`'s: the share of
input tokens the server read from its cache, the breaks of the prefix by reason with the uncached tokens behind
each, and the stages with the most uncached input. Prints nothing when the run has no transcript yet.
"""
import glob
import json
import sys

from app.observability import cache_report

run = sys.argv[1] if len(sys.argv) > 1 else ""
paths = sorted(glob.glob(f"/app/data/transcripts/{run}*.jsonl")) if run else []
records = []
for path in paths[:1]:
    for line in open(path, errors="replace"):
        try:
            records.append(json.loads(line))
        except Exception:
            continue
for line in cache_report.lines(records):
    print(line)
