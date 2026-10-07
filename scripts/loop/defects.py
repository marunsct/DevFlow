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

# A sprint's defects are numbered within its current remediation cycle: the
# numbers only grow within a cycle and start again at 0 on a re-planned
# attempt, so a defect raised at a number no higher than one the cycle already
# holds opens a new cycle. An event about a defect raised before the ledger
# began (a run deployed onto mid-way) joins the current cycle.
cycles = collections.defaultdict(list)  # sprint -> [ {index: [events]} ]
for event in events:
    sprint, index = event.get("sprint"), event.get("index")
    sprint_cycles = cycles[sprint]
    if event.get("event") == "raised":
        held = [i for i in (sprint_cycles[-1] if sprint_cycles else {}) if isinstance(i, int)]
        if not sprint_cycles or (isinstance(index, int) and held and index <= max(held)):
            sprint_cycles.append({})
        sprint_cycles[-1][index] = [event]
    else:
        if not sprint_cycles:
            sprint_cycles.append({})
        sprint_cycles[-1].setdefault(index, []).append(event)


def _short(text, limit=110):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


for sprint in sorted(cycles, key=lambda s: (s is None, s)):
    for attempt, defects in enumerate(cycles[sprint], 1):
        by_source = collections.Counter(
            (story[0].get("source") or "?") if story[0].get("event") == "raised" else "raised before the ledger"
            for story in defects.values()
        )
        number = "?" if sprint is None else sprint + 1
        print(f"== sprint {number}, attempt {attempt}: {len(defects)} defect(s) - "
              + ", ".join(f"{count} {source}" for source, count in by_source.most_common()))
        for index in sorted(defects, key=lambda i: (not isinstance(i, int), i if isinstance(i, int) else 0)):
            story = defects[index]
            first = story[0]
            raised = first.get("event") == "raised"
            source = (first.get("source") or "?") if raised else "raised before the ledger"
            print(f"  #{index} round {first.get('round')} [{source}] "
                  f"{first.get('owner') or '-'}: {_short(first.get('description'))}")
            for later in story[1:] if raised else story:
                print(f"      {later.get('at', '')[11:19]} {later.get('stage')}: {later.get('event')}"
                      + (f" - {_short(later.get('detail'), 160)}" if later.get("detail") else ""))
            if raised and len(story) == 1:
                print("      (nothing recorded after it was raised: still open, or the round ended first)")
