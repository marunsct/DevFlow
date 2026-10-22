"""What a stage was told, and what it answered.

Runs INSIDE the worker container:

    docker compose exec -T worker python - <run-id> <stage> [visit] [--full] [--system] < scripts/loop/asked.py

or `scripts/loop/loop.sh asked <run-id> <stage> [visit] [--full] [--system]`.

A stage visited more than once (the lead re-planning, a review sent back)
has its visits listed; the last is shown unless `visit` (1-based) names one.
Each message of the opening request is printed (cut at 3000 characters
unless `--full`; the system prompt only with `--system`), then the calls the
stage made, then its final answer - the structured response it returned.
"""
import glob
import json
import sys

args = [a for a in sys.argv[1:] if not a.startswith("--")]
flags = {a for a in sys.argv[1:] if a.startswith("--")}
if len(args) < 2:
    print("usage: asked <run-id> <stage> [visit] [--full] [--system]")
    raise SystemExit(2)
run, stage = args[0], args[1]
wanted = int(args[2]) if len(args) > 2 and args[2].isdigit() else None
limit = None if "--full" in flags else 3000

paths = sorted(glob.glob(f"/app/data/transcripts/{run}*.jsonl"))
if not paths:
    print("no transcript yet")
    raise SystemExit(0)

visits, current, previous = [], None, None
for line in open(paths[0], errors="replace"):
    try:
        record = json.loads(line)
    except Exception:
        continue
    here = record.get("stage")
    if here == stage and previous != stage:
        current = []
        visits.append(current)
    if here == stage and current is not None:
        current.append(record)
    if here:
        previous = here
if not visits:
    print(f"no stage named {stage!r} in this run")
    raise SystemExit(0)

print(f"{stage}: {len(visits)} visit(s) - "
      + ", ".join(f"{i}) {v[0].get('at', '')[11:19]} ({len(v)} records)" for i, v in enumerate(visits, 1)))
chosen = visits[(wanted or len(visits)) - 1]
print(f"--- visit {(wanted or len(visits))} ---")


def _text(content):
    return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)


def _cut(text):
    return text if limit is None or len(text) <= limit else text[:limit] + f"\n[... {len(text) - limit} more characters; --full shows them]"


requests = [r for r in chosen if r.get("kind") == "model_request"]
if requests:
    print("\n=== told ===")
    for message in requests[0].get("messages") or []:
        role = message.get("role")
        if role == "system" and "--system" not in flags:
            print(f"[system prompt: {len(_text(message.get('content')))} characters; --system shows it]")
            continue
        print(f"\n[{role}]\n{_cut(_text(message.get('content')))}")

calls = [r for r in chosen if r.get("kind") == "tool_call"]
if calls:
    print(f"\n=== {len(calls)} tool call(s) ===")
    for call in calls:
        print(f"  {call.get('at', '')[11:19]} {call.get('tool')} {json.dumps(call.get('args'), ensure_ascii=False)[:160]}")

answers = [
    (r, tc) for r in chosen if r.get("kind") == "model_response"
    for tc in (r.get("tool_calls") or []) if tc.get("name") and tc.get("name")[0].isupper()
]
print("\n=== answered ===")
if answers:
    record, call = answers[-1]
    print(f"{record.get('at', '')[11:19]} {call.get('name')}:")
    print(_cut(json.dumps(call.get("args"), indent=2, ensure_ascii=False)))
else:
    texts = [r.get("text") for r in chosen if r.get("kind") == "model_response" and r.get("text")]
    print(_cut(texts[-1]) if texts else "(no final answer recorded in this visit)")
