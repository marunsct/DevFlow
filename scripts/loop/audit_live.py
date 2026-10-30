"""Audit one run's transcript while it runs: the numbers for a 15-20 minute check.

Runs INSIDE the worker container, because that is where transcripts live
(`/app/data/transcripts/<run-id>*.jsonl`). It is piped in on stdin, so nothing
has to be copied into the container and a redeploy (which wipes the worker's
`/tmp`) costs nothing:

    docker compose exec -T worker python - <run-id> < scripts/loop/audit_live.py

or simply `scripts/loop/loop.sh audit`.

What it prints, and what each line is for:

- `now in` - the stage that wrote the last record, the tool-call count, and the
  share of tool calls whose result was an error or a refusal.
- `resumed after its worker stopped` - when orphan recovery resumed the run
  (a mid-run deploy, a crash), from the transcript's `resumed` records.
- `duplicate executions` - one tool call id run more than once. A call the
  worker's restart cut off before its result was recorded runs again on the
  resume; those are counted apart, as expected. The rest must be
  0; anything else means a resume replayed a call (a harness bug).
- `redundant reads` - reads answered with a "you already have this" notice or a
  refusal. Healthy runs sit around 8-19%; the digest-less baseline was 20-49%.
- `stage order` - the last 14 stage switches. Parallel mode interleaves
  specialists, so repeated names are normal there.
- `per stage` - where the failures are. A stage above ~15% deserves a trace
  (`loop.sh stage <name>`).
- `failure signatures` - failures grouped by tool and message shape (quoted
  names become 'X', numbers become N), each with one example call.

A failure here is not automatically a harness bug. Many are guards working
(a parse refusal that kept a broken file off disk, a refused repeat). The job
of the audit is to find the ones worth a trace; `scripts/audit_run.py`
separates "refusals that prevented damage" from "failures that cost the run"
for a finished run.
"""
import collections
import glob
import json
import re
import sys

run = sys.argv[1]
paths = sorted(glob.glob(f"/app/data/transcripts/{run}*.jsonl"))
if not paths:
    print("no transcript yet")
    raise SystemExit(0)

# An error result, optionally behind a bracketed guard prefix such as
# "[This `grep` returned exactly what ...]". Matching only at the start of the
# text undercounted failures by half before the prefix was allowed for.
FAIL = re.compile(r"^\s*(\[[^\]]*\]\s*)?(\{\"error\"|Error:|Refusing|Not running|Not looking)")
REDUNDANT = ("You have already read lines", "same bytes", "Refusing to read", "These are the same bytes",
             "is in the project memory at the start of this conversation")
READS = ("read_file", "read_repository_file")

records = []
for line in open(paths[0], errors="replace"):
    try:
        records.append(json.loads(line))
    except Exception:
        continue

calls, by_id = {}, collections.defaultdict(list)
answered, cut_off, resumes = set(), set(), []
per_stage = collections.Counter()
failed = collections.Counter()
signatures = collections.Counter()
examples = {}
reads = redundant = 0
order, last_stage = [], ""
for rec in records:
    stage = rec.get("stage") or ""
    if stage:
        last_stage = stage
        if not order or order[-1] != stage:
            order.append(stage)
    kind = rec.get("kind")
    if kind == "resumed":
        resumes.append(rec.get("at", "")[11:16])
    if kind == "tool_call":
        if rec.get("call_id") in calls and rec.get("call_id") not in answered:
            # Run again with no result recorded for the first time: the worker
            # stopped mid-call (a deploy, a crash) and the resumed stage ran it
            # again. Expected - only a replay of a finished call is a bug.
            cut_off.add(rec.get("call_id"))
        calls[rec.get("call_id")] = rec
        by_id[rec.get("call_id")].append(stage)
        per_stage[stage] += 1
        if rec.get("tool") in READS:
            reads += 1
    elif kind == "tool_result":
        answered.add(rec.get("call_id"))
        call = calls.get(rec.get("call_id")) or {}
        raw = rec.get("result") or rec.get("content") or ""
        text = json.dumps(raw) if not isinstance(raw, str) else raw
        if call.get("tool") in READS and any(m in text[:600] for m in REDUNDANT):
            redundant += 1
        is_error = isinstance(raw, dict) and raw.get("error")
        if is_error or FAIL.match(text if isinstance(raw, str) else ""):
            failed[call.get("stage") or stage] += 1
            head = str(raw.get("error") if isinstance(raw, dict) else raw)
            head = re.sub(r"'[^']*'", "'X'", head)
            head = re.sub(r"\d+", "N", head)[:90]
            key = (call.get("tool"), head)
            signatures[key] += 1
            examples.setdefault(key, (call.get("stage"), json.dumps(call.get("args") or {})[:100]))

extra = sum(len(v) - 1 for key, v in by_id.items() if key not in cut_off)
restarted = sum(len(v) - 1 for key, v in by_id.items() if key in cut_off)
total_calls = sum(per_stage.values())
total_failed = sum(failed.values())
print(f"now in: {last_stage}   records={len(records)}  tool calls={total_calls}  "
      f"failed={total_failed} ({100 * total_failed / max(1, total_calls):.1f}%)")
print(f"duplicate executions (one call_id run twice): {extra}"
      + (f"   [+{restarted} re-run after a restart cut the first off - expected]" if restarted else ""))
if resumes:
    print(f"resumed after its worker stopped (deploys, crashes), UTC: {', '.join(resumes)}")
print(f"redundant reads: {redundant} of {reads} reads "
      f"({100 * redundant / max(1, reads):.0f}%)   [healthy: 8-19%; before the digest: 20-49%]")
print("stage order: " + " -> ".join(order[-14:]))
try:
    from app.observability import cache_report

    for cache_line in cache_report.lines(records)[:2]:
        print(cache_line)
except Exception:  # the cache lines are an addition; the audit does not depend on them
    pass

print("\nper stage (worst failure count first):")
print(f"  {'stage':<26}{'calls':>6}{'failed':>8}{'rate':>7}")
for stage in sorted(per_stage, key=lambda s: (-failed[s], -per_stage[s]))[:12]:
    print(f"  {stage:<26}{per_stage[stage]:>6}{failed[stage]:>8}"
          f"{100 * failed[stage] / max(1, per_stage[stage]):>6.0f}%")

if signatures:
    print("\nfailure signatures:")
    for (tool, head), n in signatures.most_common(8):
        stage, args = examples[(tool, head)]
        print(f"  x{n:<3} [{tool}] e.g. {stage}")
        print(f"        {args}")
        print(f"        -> {head}")
