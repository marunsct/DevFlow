"""Which stage re-read which file, and which notice answered it.

Runs INSIDE the worker container, piped in on stdin:

    docker compose exec -T worker python - <run-id> < scripts/loop/redundant_reads.py

or `scripts/loop/loop.sh reads`.

A redundant read is a `read_file` answered with one of the read ladder's
notices ("You have already read lines ...", "same bytes ...") or refused
outright ("Refusing to read ... again"). The ladder is working when these
appear; what is worth a trace is one (stage, file) pair with many of them -
seven re-reads of one file by one stage has twice been a harness message the
model misread, not a model that simply forgot.

Prints: the count of each notice kind, the 15 worst (stage, file) pairs, and
one example of each notice's text.
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

MARKERS = ("You have already read lines", "same bytes", "Refusing to read", "These are the same bytes")
calls = {}
by_pair, kinds, examples = collections.Counter(), collections.Counter(), {}
for line in open(paths[0], errors="replace"):
    try:
        r = json.loads(line)
    except Exception:
        continue
    if r["kind"] == "tool_call":
        calls[r.get("call_id")] = r
    if r["kind"] == "tool_result" and r.get("tool") in ("read_file", "read_repository_file"):
        content = str(r["content"])
        for marker in MARKERS:
            if marker in content[:400]:
                args = calls.get(r.get("call_id"), {}).get("args", {})
                by_pair[(r.get("stage"), args.get("file_path"))] += 1
                kinds[marker] += 1
                examples.setdefault(marker, content[:300])
                break

print(dict(kinds))
for pair, n in by_pair.most_common(15):
    print(n, pair)
for marker, text in examples.items():
    print("---", marker, "\n", text)
