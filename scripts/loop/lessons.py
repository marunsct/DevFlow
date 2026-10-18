"""Mistakes the agents make again and again, by language: candidates for guidance.

Every run's audit lists its own failed tool calls; nothing looked across runs.
A refusal that recurs in run after run on one language is a lesson the agents
are never told - and the place to tell them is `app/plugins/seed.py`, under
that language, where the plugin middleware injects it into every stage of a
run on that stack (the rule: stack-specific guidance lives there or in a pack,
never in the workflow).

This reads every stored transcript in the worker, groups failed tool calls by
tool and message shape (quoted names become X, numbers N - as `audit_live.py`
does), joins each run to the languages its workspace was pinned to, and lists
the shapes seen in at least `MIN_RUNS` runs, per language, most widespread
first, with one example and whether `seed.py` already has an entry for that
language. It proposes; a person or an agent writes the guidance, with a test,
as for any prompt rule.

    scripts/loop/loop.sh lessons [min-runs]

The lesson store (plan item AI, `app.plugins.lessons`): only a lesson the owner
approved reaches a prompt.

    lessons.py list
    lessons.py propose <stack> "<trigger>" "<rule>" <runs> [harness|operator]
    lessons.py approve <id>      lessons.py reject <id>
"""
import collections
import glob
import json
import re
import sys
from pathlib import Path

def _the_store_command(argv: list[str]) -> bool:
    """Run a lesson-store command and say so; False when `argv` is not one."""
    if not argv or argv[0] not in ("list", "propose", "approve", "reject"):
        return False
    from app.plugins import lessons as store

    command, rest = argv[0], argv[1:]
    if command == "list":
        for lesson in store.load():
            print(f"{lesson['id']:6} {lesson['status']:9} [{lesson['stack']}] in {lesson['evidence_runs']} runs, "
                  f"{lesson['source']}: {lesson['rule']}\n         answers: {lesson['trigger']}")
    elif command == "propose":
        lesson = store.propose(rest[0], rest[1], rest[2], int(rest[3]), source=rest[4] if len(rest) > 4 else "harness")
        print(f"{lesson['id']} {lesson['status']}: {lesson['rule']}")
    else:
        lesson = store.decide(rest[0], command == "approve")
        print(f"{lesson['id']} {lesson['status']}")
    return True


if _the_store_command(sys.argv[1:]):
    raise SystemExit(0)

MIN_RUNS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
FAIL = re.compile(r"^\s*(\[[^\]]*\]\s*)?(\{\"error\"|Error:|Refusing|Not running|Not looking)")

try:
    from app.plugins.seed import SEED_INSTRUCTIONS
    from app.tools.sandbox import STACK_MARKER
except Exception:  # noqa: BLE001 - outside the worker
    SEED_INSTRUCTIONS, STACK_MARKER = {}, ".project-stack"


def shape(text: str) -> str:
    text = re.sub(r"'[^']*'|\"[^\"]*\"|`[^`]*`", "X", text)
    text = re.sub(r"\d+", "N", text)
    return " ".join(text.split())[:110]


def languages(run: str) -> list[str]:
    for root in glob.glob(f"/app/data/workspaces/*/workspace-{run}"):
        marker = Path(root) / STACK_MARKER
        if marker.is_file():
            return sorted({line.strip() for line in marker.read_text().splitlines() if line.strip()}) or ["unknown"]
    return ["unknown"]


seen_in = collections.defaultdict(set)       # (language, tool, shape) -> runs
examples = {}
for path in sorted(glob.glob("/app/data/transcripts/run-*.jsonl")):
    run = Path(path).stem.split(".")[0]
    pending = {}
    failures = set()
    for line in open(path, errors="replace"):
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if record.get("kind") == "tool_call":
            pending[record.get("call_id")] = (record.get("tool"), json.dumps(record.get("args") or {})[:160])
        elif record.get("kind") == "tool_result":
            raw = record.get("result") or record.get("content") or ""
            text = str(raw.get("error")) if isinstance(raw, dict) and raw.get("error") else raw if isinstance(raw, str) else ""
            if not (isinstance(raw, dict) and raw.get("error")) and not FAIL.match(text):
                continue
            if text.lstrip().startswith("{"):
                try:
                    text = str(json.loads(text).get("error") or text)
                except (ValueError, AttributeError):
                    pass
            tool, args = pending.get(record.get("call_id"), ("?", ""))
            key = (tool or "?", shape(text))
            failures.add(key)
            examples.setdefault(key, (run, args, text[:200]))
    for language in languages(run):
        for tool, head in failures:
            seen_in[(language, tool, head)].add(run)

by_language = collections.defaultdict(list)
for (language, tool, head), runs in seen_in.items():
    if len(runs) >= MIN_RUNS:
        by_language[language].append((len(runs), tool, head))

for language in sorted(by_language):
    print(f"\n=== {language}  (seed.py entry: {'yes' if language in SEED_INSTRUCTIONS else 'NO'})")
    for count, tool, head in sorted(by_language[language], reverse=True)[:12]:
        run, args, content = examples[(tool, head)]
        print(f"  in {count:3} runs  [{tool}] {head}")
        print(f"            e.g. {run[:12]} {args[:110]}")
if not by_language:
    print(f"no failure shape recurs in {MIN_RUNS} or more runs")
