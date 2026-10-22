"""Each failing acceptance test of a run: its criterion, its error, and the page it failed on.

Runs INSIDE the worker container:

    docker compose exec -T worker python - <run-id> [--full] < scripts/loop/failures.py

or `scripts/loop/loop.sh failures [run-id] [--full]`.

Reads the harness's last run of the locked suite
(`.harness/acceptance-result.json` in the run's workspace). For each failing
test it prints the first error line, the call log's first lines, and the page
as the product showed it when the test failed - the evidence a stale locator,
a missing `page.goto` or a real product bug is told apart by. `--full` prints
each failure whole.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

args = [a for a in sys.argv[1:] if not a.startswith("--")]
full = "--full" in sys.argv
run = args[0]
path = Path(f"/app/data/workspaces/default/workspace-{run}/.harness/acceptance-result.json")
if not path.is_file():
    print(f"no acceptance result for {run} yet")
    raise SystemExit(0)
result = json.loads(path.read_text())
measured = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).strftime("%H:%M:%S UTC")
print(f"ran: {result.get('ran')}  passed {result.get('passed')}  failed {result.get('failed')}  "
      f"skipped {result.get('skipped')}  (measured {measured})")
if result.get("runtime_problems"):
    print("the page itself reported:", "; ".join(map(str, result["runtime_problems"]))[:400])

failing = 0
for cid, criterion in (result.get("criteria") or {}).items():
    for test in criterion.get("tests") or []:
        if test.get("outcome") == "passed":
            continue
        failing += 1
        message = str(test.get("message") or "")
        print(f"\n=== {cid} {criterion.get('status')}: {test.get('name')}")
        print(f"criterion: {criterion.get('text')}")
        if full:
            print(message)
            continue
        error, _, page = message.partition("What the page showed when this failed:")
        lines = [line for line in error.splitlines() if line.strip() and "─" not in line]
        start = next((i for i, line in enumerate(lines) if "Error" in line), 0)
        print("\n".join(lines[start:start + 9]))
        if page.strip():
            print("page when it failed:")
            print("\n".join(page.strip().splitlines()[:30]))
if not failing:
    print("\nno failing tests")
