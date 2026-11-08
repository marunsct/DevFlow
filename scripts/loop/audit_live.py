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
# What the ten-minute audit could not see (HR2.O.1): salvaged and capped replies, pause cancellations, the
# prefill:decode ratio of each stage and the memory block it carries.
salvaged, capped, in_tokens, out_tokens, memory_chars = (collections.Counter(), collections.Counter(),
                                                        collections.Counter(), collections.Counter(), {})
cancelled = 0
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
    elif kind == "model_response":
        if rec.get("salvaged"):
            salvaged[stage] += 1
        if rec.get("finish_reason") == "length":
            capped[stage] += 1
        usage = rec.get("usage") or {}
        in_tokens[stage] += int(usage.get("input_tokens") or 0)
        out_tokens[stage] += int(usage.get("output_tokens") or 0)
    elif kind == "model_request":
        memory = (rec.get("blocks") or {}).get("project_memory")
        if isinstance(memory, (int, float)):
            memory_chars[stage] = int(memory)
    elif kind == "model_error" and "RunCancelled" in str(rec.get("error") or ""):
        cancelled += 1
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
# A rate over few reads says nothing: measured over an evening, 3 of 69 read as 39% and was chased twice, while the
# one real case was 14 redundant reads by one stuck stage. Each redundant read is answered without its content.
_FEW = 10
print(f"redundant reads: {redundant} of {reads} reads ({100 * redundant / max(1, reads):.0f}%)   "
      + (f"[fewer than {_FEW}: noise, not waste]" if redundant < _FEW
         else "[10 or more: look at which stage with `loop.sh reads`; healthy 8-19% of reads]"))
if salvaged or capped:
    by_stage = ", ".join(f"{st}: {n}" for st, n in salvaged.most_common(4))
    print(f"salvaged replies: {sum(salvaged.values())} ({by_stage or 'none'}); replies cut at the cap: {sum(capped.values())}")
paused_minutes = 0.0
try:
    from app.server.run_store import RunStore

    run_id = next((r.get("run_id") for r in records if r.get("run_id")), "")
    paused_minutes = round(RunStore().paused_seconds([run_id]).get(run_id, 0.0) / 60, 1) if run_id else 0.0
except Exception:  # the pause line is an addition
    pass
if cancelled or paused_minutes:
    print(f"pauses: {cancelled} call(s) cancelled by a pause; {paused_minutes} min paused (taken off active_minutes since LF.690)")
if last_stage and out_tokens[last_stage]:
    ratio = in_tokens[last_stage] / max(1, out_tokens[last_stage])
    memory = memory_chars.get(last_stage, 0)
    flag = "   <- prefill-heavy: the stage reads far more than it writes" if ratio > 60 or memory > 80_000 else ""
    print(f"prefill:decode in {last_stage}: {ratio:.0f}:1 ({in_tokens[last_stage]:,} in / {out_tokens[last_stage]:,} out); "
          f"memory block {memory // 1000}k chars{flag}")
print("stage order: " + " -> ".join(order[-14:]))


def design_line(stages: list) -> str:
    """The whole design phase in one line: the last 14 switches drop it once a run is past it (measured: a run's
    escalation was reported as none because the stage order no longer reached back to it)."""
    reviews = sum(1 for s in stages if s == "architecture_review")
    if not reviews:
        return ""
    escalated = "escalation" in stages[:stages.index(next((s for s in stages if s.startswith("acceptance_author")), stages[-1]))] \
        if any(s.startswith("acceptance_author") for s in stages) else "escalation" in stages
    return f"design: {reviews} architecture review(s), " + ("escalated" if escalated else "no escalation")


if design_line(order):
    print(design_line(order))
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
