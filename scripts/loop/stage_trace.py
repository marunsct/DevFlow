"""Trace one stage of a run: every model reply, tool call and tool result, in order.

Runs INSIDE the worker container, piped in on stdin:

    docker compose exec -T worker python - <run-id> <stage> [HH:MM] < scripts/loop/stage_trace.py

or `scripts/loop/loop.sh stage <stage> [HH:MM]`. The optional `HH:MM` (UTC -
the transcript's clock; JST minus 9 hours) skips everything before it, which
matters because stage names repeat across sprints and revisions.

This is the tool that finds harness bugs. `audit_live.py` says WHERE failures
are; this says WHY. Read the model's own words just before a failed call: they
usually name the harness message it misread ("the workspace listing reflects
the original state", "I'll continue from where I left off") or the instruction
it is following.

Output columns: time, then one of
  REQ  n=<messages> <roles>   a model call and the tail of its message roles
  RESP in=<tokens> out=<tokens> <first 140 chars of the reply>
  CALL <tool> <arguments, truncated>
  RES  <result, truncated>
A RESP with out= near the stage's output budget and no CALL after it is a
reply spent entirely on reasoning; the harness withholds tools for one call
and logs "thinking switched off" when that happens.
"""
import glob
import json
import sys

run, stage = sys.argv[1], sys.argv[2]
since = sys.argv[3] if len(sys.argv) > 3 else ""
paths = sorted(glob.glob(f"/app/data/transcripts/{run}*.jsonl"))
if not paths:
    print("no transcript yet")
    raise SystemExit(0)

for line in open(paths[0], errors="replace"):
    try:
        r = json.loads(line)
    except Exception:
        continue
    if r.get("stage") != stage or r["at"][11:16] < since:
        continue
    at, kind = r["at"][11:19], r["kind"]
    if kind == "model_request":
        msgs = r.get("messages") or []
        roles = "".join((m.get("role") or "?")[0] for m in msgs)
        print(at, "REQ n=%d" % len(msgs), roles[-12:])
    elif kind == "model_response":
        u = r.get("usage") or {}
        text = (r.get("text") or "")[:140].replace("\n", " ")
        print(at, "  RESP in=%s out=%s" % (u.get("input_tokens"), u.get("output_tokens")), text)
    elif kind == "tool_call":
        print(at, "    CALL", r["tool"], json.dumps(r["args"])[:160])
    elif kind == "tool_result":
        print(at, "    RES ", str(r["content"])[:160].replace("\n", " "))
