"""Audit one run's transcript: cost, waste, and what the harness prevented.

    python3 scripts/audit_run.py <path-to-transcript.jsonl> [workspace]

With a workspace path, it also answers the question the transcript cannot: does
the product work? Every run in this harness's history that shipped something
broken shipped it with a green suite - run 0c5aabdb had no HTML at all, run
0afef410 had HTML and JavaScript that never met, run 7e960f06 had a page with
no `<script>` tag - and in each case the transcript looked fine. So the last
section runs the cross-file checks over the workspace and prints what blocks.

Transcripts live at `DATA_DIR/transcripts/<run-id>.jsonl`; from a deployment,
`docker compose exec -T worker cat /app/data/transcripts/<run-id>.jsonl > /tmp/run.jsonl`.

Every number in `docs/harness-hardening-plan.md` §4b came out of this. The
three lines that matter, and what each is for:

- **refusals that prevented damage** - a broken file the harness stopped
  reaching disk. These are the checks working, and they are deliberately not
  counted as failures or as waste. Counting them as waste is the mistake this
  script shipped with: `node --check` refusing an illegal return four times
  before the model fixed it scored as four wasted calls.
- **failures that cost the run** - everything else that came back an error.
  This is the number to drive down.
- **identical repeats in a stage** - byte-identical tool calls, refusals
  excluded. What is left after the notices have done their work.

`SAVED` is the list of message fragments that mark a preventing refusal. A
fragment that stops matching silently moves calls from the first line to the
third, so keep it in step with the messages in `app/tools/repository.py`.
"""
import json, sys, collections, re

SAVED = (
    "Node cannot parse", "Refusing to write", "Refusing to change",
    "already been applied", "exactly as it is", "already contained exactly",
    "is a test, and tests are part of what", "already holds this module",
    "you have already been told that twice",
    # Found missing by sweeping every distinct error across runs 60-67 rather
    # than reading them one at a time, which is how the first three of these
    # went unnoticed:
    "so it is ambiguous which one",   # editing one of N identical passages at random
    "it can execute arbitrary code",  # `node -e`, with a file-based alternative given
    "Moving onto it would delete it", # a move that would silently destroy the target
)

def load(path):
    rows = []
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.strip()
        if line.startswith("{"):
            try: rows.append(json.loads(line))
            except Exception: pass
    return rows

def main(path):
    rows = load(path)
    res = {r.get("call_id"): r for r in rows if r["kind"] == "tool_result"}
    calls = [r for r in rows if r["kind"] == "tool_call"]
    mc = sum(1 for r in rows if r["kind"] == "model_request")

    saved = cost = 0
    shapes = collections.Counter()
    for r in calls:
        c = (res.get(r.get("call_id")) or {}).get("content") or ""
        if '"error"' not in c[:400] and not c.lstrip().startswith("Error:"):
            continue
        if any(mark in c for mark in SAVED):
            saved += 1
        else:
            cost += 1
            shapes[(r.get("tool"), re.sub(r"\d+", "N", c[:110]))] += 1

    segs = []
    for i, r in enumerate(rows):
        if r["kind"] != "model_request": continue
        st = r.get("stage")
        if segs and segs[-1][0] == st: segs[-1][1] += 1; segs[-1][3] = i
        else: segs.append([st, 1, i, i])
    bounds = [(s[0], s[2], (segs[k+1][2] if k+1 < len(segs) else len(rows)))
              for k, s in enumerate(segs)]
    # A repeat whose result was a refusal that prevented damage is not waste of
    # the same kind: the harness stopped something, and it is already counted
    # above. Counting it twice made "repeats" look like pure loss when part of
    # it was `node --check` refusing an illegal return four times before the
    # model fixed it and the fifth write succeeded.
    #
    # A second mistake this tool shipped with, found on run 8d28ee3f: the same
    # command run twice is only waste when it *answered* the same twice. That
    # run's `specialist_ui_ux_0` ran `npm test` four times and was counted as
    # three repeats, but it edited the code between every pair and got four
    # different failures back - a working fix loop, which is the behaviour the
    # harness wants. Keying on the result as well as the call drops those and
    # keeps the real thing: a stage re-asking a question already answered.
    waste = collections.Counter()
    for st, a, b in bounds:
        c = collections.Counter()
        for r in rows[a:b]:
            if r["kind"] != "tool_call": continue
            got = (res.get(r.get("call_id")) or {}).get("content") or ""
            if any(mark in got for mark in SAVED): continue
            c[(r.get("tool"), json.dumps(r.get("args"), sort_keys=True)[:250], got)] += 1
        for (tool, _, _), v in c.items():
            if v > 1: waste[tool] += v - 1

    print(f"model calls {mc} | tool calls {len(calls)}")
    print(f"  refusals that prevented damage: {saved} ({100*saved/max(len(calls),1):.1f}%)")
    print(f"  failures that cost the run:     {cost} ({100*cost/max(len(calls),1):.1f}%)")
    print(f"  identical repeats in a stage:   {sum(waste.values())} "
          f"({100*sum(waste.values())/max(mc,1):.1f}% of model calls) {dict(waste)}")
    print("\nstages:", " -> ".join(f"{s[0]}({s[1]})" for s in segs))
    if shapes:
        print("\ncostly failures:")
        for (t, m), n in shapes.most_common(10):
            print(f"  {n:3d} {t}: {m}")
    notices = [
        ("returned exactly what it returned", "query repeat"),
        ("same bytes this file gave you", "read repeat"),
        ("you already have it", "read withheld"),
        ("already contained exactly this content", "write unchanged"),
        ("you have already been told that twice", "no-op refusal"),
        ("already failed", "ledger command"),
    ]
    print("\nnotices:")
    for phrase, label in notices:
        n = sum(1 for r in rows if r["kind"] == "tool_result" and phrase in (r.get("content") or ""))
        print(f"  {n:4d} {label}")

def the_product(workspace):
    """What the deterministic checks say about the built product.

    Deliberately the last section and deliberately separate: the numbers above
    are about how the run spent its calls, and this is about whether any of it
    produced something that works. A run can score perfectly on both of the
    first two and ship a page that does nothing.
    """
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
    try:
        from app.analysis.integration_checks import summarise_integration
    except Exception as exc:  # noqa: BLE001 - the audit still has value without it
        print(f"\nthe product: could not load the checks ({exc})")
        return
    report = summarise_integration(workspace)
    # On the phrase without its verb: the summary writes "means" for one
    # finding and "mean" for several, so matching the singular reported "no
    # blocking problems" for every workspace that had more than one - silent
    # in exactly the case that matters most.
    blocking = "a feature DOES NOT WORK" in report
    print("\nthe product:")
    print("  BLOCKING problems found" if blocking else "  no blocking cross-file problems")
    for line in report.splitlines():
        if line.startswith("- "):
            print(f"    {line[2:][:150]}")
        elif "problem(s) found" in line or line.startswith("  application:") or line.startswith("               "):
            print(f"  {line.strip()[:150]}")


if len(sys.argv) > 2:
    main(sys.argv[1])
    the_product(sys.argv[2])
else:
    main(sys.argv[1])
