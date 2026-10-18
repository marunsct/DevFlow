"""Where a run's wall-clock time goes: `loop.sh timing [run-id ...]`.

Per phase and per stage family: model time against tool time, model calls,
output tokens and the share that was reasoning, reasoning spirals, and how far
model calls overlapped. Written for the speed review of 2026-10-01 (handover
section 0.9), which found the model busy 98% of a 163-minute run and 91% of
its output reasoning. Run inside the worker, where the transcripts are.
"""
import collections
import glob
import json
import re
import sys
from datetime import datetime


def ts(value):
    return datetime.fromisoformat(value).timestamp()


def union(intervals):
    total, end = 0.0, None
    start = None
    for a, b in sorted(intervals):
        if end is None or a > end:
            if end is not None:
                total += end - start
            start, end = a, b
        else:
            end = max(end, b)
    if end is not None:
        total += end - start
    return total


def family(stage):
    s = re.sub(r"_\d+(_\d+)?$", "", stage or "")
    if s.startswith("specialist_"):
        return "specialists"
    if s in ("test_round", "defect_fix"):
        return s
    return s


PHASE = {
    "product_manager": "1 plan", "tools_models": "1 plan", "stack_selector": "1 plan",
    "principal_architect": "1 plan", "architecture_review": "1 plan", "scrum_master": "1 plan",
    "technical_lead": "2 sprint plan", "specialists": "3 build",
    "test_round": "4 verify", "defect_fix": "4 verify", "security_review": "4 verify",
    "milestone_review": "4 verify",
}


def analyse(prefix):
    paths = glob.glob(f"/app/data/transcripts/{prefix}*.jsonl")
    if not paths:
        print("no transcript for", prefix)
        return
    recs = []
    for line in open(paths[0], errors="replace"):
        try:
            recs.append(json.loads(line))
        except Exception:
            continue
    times = [ts(r["at"]) for r in recs if r.get("at")]
    wall = max(times) - min(times)
    open_req = {}
    model_iv, tool_iv = [], []
    calls = {}
    per = collections.defaultdict(lambda: collections.Counter())
    per_iv = collections.defaultdict(list)
    spirals = 0
    stages_seen = []
    tool_counts, tool_errors = collections.Counter(), collections.Counter()
    for r in recs:
        st, k = r.get("stage") or "", r.get("kind")
        fam = family(st)
        if k == "model_request":
            open_req[st] = ts(r["at"])
        elif k == "model_response" and st in open_req:
            a, b = open_req.pop(st), ts(r["at"])
            model_iv.append((a, b))
            per_iv[fam].append((a, b))
            u = r.get("usage") or {}
            out = u.get("output_tokens") or 0
            rea = (u.get("output_token_details") or {}).get("reasoning") or 0
            per[fam]["calls"] += 1
            per[fam]["out"] += out
            per[fam]["reasoning"] += rea
            per[fam]["in"] += u.get("input_tokens") or 0
            per[fam]["cached"] += (u.get("input_token_details") or {}).get("cache_read") or 0
            per[fam]["model_s"] += b - a
            if r.get("finish_reason") == "length" and not r.get("tool_calls"):
                spirals += 1
                per[fam]["spirals"] += 1
        elif k == "tool_call":
            calls[r.get("call_id")] = (ts(r["at"]), fam, r.get("tool"))
        elif k == "tool_result" and r.get("call_id") in calls:
            a, f, tool = calls.pop(r.get("call_id"))
            b = ts(r["at"])
            said = str(r.get("content") or "")[:40]
            tool_counts[tool] += 1
            if said.startswith("Error") or '"error"' in said:
                tool_errors[tool] += 1
            tool_iv.append((a, b))
            per[f]["tool_s"] += b - a
            per[f]["tools"] += 1
            if tool in ("run_terminal_command", "run_validation"):
                per[f]["cmd_s"] += b - a
        if st and (not stages_seen or stages_seen[-1] != st):
            stages_seen.append(st)
    model_busy = union(model_iv)
    tool_busy = union(tool_iv)
    any_busy = union(model_iv + tool_iv)
    tot = collections.Counter()
    for c in per.values():
        tot.update(c)
    print(f"\n===== {prefix}  wall {wall/60:.0f} min")
    print(f"model busy {model_busy/60:.0f} min ({model_busy/wall:.0%}) | tools busy {tool_busy/60:.0f} min ({tool_busy/wall:.0%}) | neither {max(wall-any_busy,0)/60:.0f} min ({max(wall-any_busy,0)/wall:.0%})")
    print(f"model calls {tot['calls']} | output tokens {tot['out']:,} of which reasoning {tot['reasoning']:,} ({tot['reasoning']/max(tot['out'],1):.0%}) | input tokens {tot['in']:,} | spirals {spirals}")
    # The prefix the server already held: on a prefill-bound server the share
    # of input it did not have to read again (KPI U.2).
    print(f"prompt cache: {tot['cached']:,} of {tot['in']:,} input tokens served from cache ({tot['cached']/max(tot['in'],1):.0%})")
    print("tool errors: " + ", ".join(
        f"{tool} {tool_errors[tool]}/{n} ({tool_errors[tool]/n:.0%})" for tool, n in tool_counts.most_common(8)
    ))
    print(f"tool calls {tot['tools']} | summed model seconds {tot['model_s']/60:.0f} min (parallel overlap {tot['model_s']/max(model_busy,1):.1f}x)")
    if tot["model_s"]:
        print(f"throughput: {tot['out']/tot['model_s']:.0f} output tok/s per call (summed)")
    phases = collections.defaultdict(list)
    for f, iv in per_iv.items():
        phases[PHASE.get(f, "5 other")].extend(iv)
    print("phase          wall(min, model-busy)  calls   out_tok  reasoning%")
    for ph in sorted(phases):
        fams = [f for f in per if PHASE.get(f, "5 other") == ph]
        c = collections.Counter()
        for f in fams:
            c.update(per[f])
        print(f"  {ph:<14} {union(phases[ph])/60:6.0f}            {c['calls']:5}  {c['out']:8,}   {c['reasoning']/max(c['out'],1):.0%}")
    print("stage family       calls  model_min  out_tok   reas%  tools  tool_min  cmd_min  spirals")
    for f, c in sorted(per.items(), key=lambda kv: -kv[1]["model_s"]):
        print(f"  {f:<18} {c['calls']:5}  {c['model_s']/60:8.0f}  {c['out']:8,}  {c['reasoning']/max(c['out'],1):4.0%}  {c['tools']:5}  {c['tool_s']/60:7.1f}  {c['cmd_s']/60:6.1f}  {c['spirals']:3}")
    counts = collections.Counter(family(s) for s in stages_seen)
    arch = sum(1 for s in stages_seen if s == "architecture_review")
    print(f"rework: architecture reviews {arch}, milestone reviews {sum(1 for s in stages_seen if s=='milestone_review')}, "
          f"test rounds {sum(1 for s in stages_seen if s.startswith('test_round'))}, defect-fix stages {len({s for s in stages_seen if s.startswith('defect_fix')})}, "
          f"lead plans {sum(1 for s in stages_seen if s=='technical_lead')}")


for prefix in sys.argv[1:]:
    analyse(prefix)
