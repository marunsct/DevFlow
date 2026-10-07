"""Each test round's defect queue: which check raised each defect, and how it ended.

Runs INSIDE the worker container, like the other loop scripts:

    docker compose exec -T worker python - <run-id> < scripts/loop/defects.py

or `scripts/loop/loop.sh defects [run-id]`.

Reads the `defect` records the harness writes to the run's transcript
(`app.observability.defect_ledger`): one when a test round queues a defect,
and one for each thing that happens to it after - closed because an earlier
fix resolved it, fixed (with the fixer's own account), left open, reverted
because the fix broke what passed. A queue whose defects repeat one another
shows here as several lines with the same story and different sources.
"""
import collections
import glob
import json
import sys

run = sys.argv[1]
paths = sorted(glob.glob(f"/app/data/transcripts/{run}*.jsonl"))
if not paths:
    print("no transcript yet")
    raise SystemExit(0)

events = []
for line in open(paths[0], errors="replace"):
    try:
        record = json.loads(line)
    except Exception:
        continue
    if record.get("kind") == "defect":
        events.append(record)
if not events:
    print("no defect records in this run's transcript (it predates the ledger, or no round has run)")
    raise SystemExit(0)

# A sprint's defects are numbered within its current remediation cycle, which
# starts again at 0 on a re-planned attempt: a defect raised at an index the
# cycle already holds opens a new cycle.
cycles = collections.defaultdict(list)  # sprint -> [ {index: [events]} ]
for event in events:
    sprint, index = event.get("sprint"), event.get("index")
    sprint_cycles = cycles[sprint]
    if event.get("event") == "raised":
        if not sprint_cycles or index in sprint_cycles[-1]:
            sprint_cycles.append({})
        sprint_cycles[-1][index] = [event]
    elif sprint_cycles and index in sprint_cycles[-1]:
        sprint_cycles[-1][index].append(event)
    else:
        sprint_cycles.append({index: [event]})


def _short(text, limit=110):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


for sprint in sorted(cycles, key=lambda s: (s is None, s)):
    for attempt, defects in enumerate(cycles[sprint], 1):
        by_source = collections.Counter(
            (story[0].get("source") or "?") for story in defects.values() if story[0].get("event") == "raised"
        )
        number = "?" if sprint is None else sprint + 1
        print(f"== sprint {number}, attempt {attempt}: {len(defects)} defect(s) - "
              + ", ".join(f"{count} {source}" for source, count in by_source.most_common()))
        for index in sorted(defects, key=lambda i: (i is None, i)):
            story = defects[index]
            first = story[0]
            print(f"  #{index} round {first.get('round')} [{first.get('source') or '?'}] "
                  f"{first.get('owner') or '-'}: {_short(first.get('description'))}")
            for later in story[1:]:
                print(f"      {later.get('at', '')[11:19]} {later.get('stage')}: {later.get('event')}"
                      + (f" - {_short(later.get('detail'), 160)}" if later.get("detail") else ""))
            if len(story) == 1:
                print("      (nothing recorded after it was raised: still open, or the round ended first)")
