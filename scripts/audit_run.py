"""Audit one run's transcript: cost, waste, and what the harness prevented.

    python3 scripts/audit_run.py <path-to-transcript.jsonl> [workspace] [brief]

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
import json, sys, collections, re, os

# The markers live in `app.observability.transcript_metrics`, which is the
# reduction the harness itself runs. Two copies drifted once already: this
# list was missing every sandbox refusal, so six of run b0db10b1's eight
# "costly failures" were guards working, and the number this script exists
# to drive down rose whenever one fired.
from app.observability.transcript_metrics import PREVENTED_DAMAGE as SAVED

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
    # Each notice can be worded more than one way, and matching only one of
    # them reports zero for a notice that fired forty-two times. Measured on
    # run-cac07d52: the read-repeat notice has a span form ("You have already
    # read lines 31-50 of this file") and a bytes form ("the same bytes this
    # file gave you"), and only the second was counted - so every audit in
    # this session under-reported read repeats, including the ones used to
    # decide what to work on.
    #
    # Keep these in step with the messages in `app/agents/workspace_backend.py`,
    # `app/agents/repeated_queries.py` and `app/tools/sandbox.py`. A phrase
    # that stops matching moves a notice silently to zero, which reads as
    # "this never fires" rather than "the audit cannot see it".
    notices = [
        (("returned exactly what it returned",), "query repeat"),
        (("same bytes this file gave you", "already read lines"), "read repeat"),
        (("you already have it",), "read withheld"),
        (("already contained exactly this content",), "write unchanged"),
        (("you have already been told that twice",), "no-op refusal"),
        (("already failed", "has already run", "already been refused",
          "already timed out"), "ledger command"),
    ]
    print("\nnotices:")
    for phrases, label in notices:
        n = sum(
            1
            for r in rows
            if r["kind"] == "tool_result"
            and any(p in (r.get("content") or "") for p in phrases)
        )
        print(f"  {n:4d} {label}")

def _the_stack_this_run_chose(workspace):
    """The stack, rebuilt from the document the workflow rendered from it.

    Several checks take the stack and are inert without it - the one that
    catches an HTTP server in a product whose own storage is `localStorage`
    is the sharpest of them. `summarise_integration(workspace)` with no stack
    silently skips them, so this script's verdict was milder than the
    reviewer's on exactly the findings that block.

    Found on run-ed05e20e: the audit reported 3 cross-file problems and the
    reviewer saw 4, the extra one being a `server.mjs` the product has no use
    for. Returns None when the document cannot be read, which is the old
    behaviour.
    """
    import re as _re

    try:
        from app.agents.tools_models import TechnologyStack

        text = open(
            os.path.join(workspace, "docs", "technology_stack.md"), encoding="utf-8"
        ).read()
    except Exception:  # noqa: BLE001 - an audit must never fail on a missing doc
        return None

    def field(label, default=""):
        # The renderer puts the label on one line and the value on the next.
        m = _re.search(rf"^\*\*{label}:\*\*\s*\n(.+)$", text, _re.M)
        return (m.group(1).strip() if m else default) or default

    language = ""
    heading = _re.search(r"^#### (.+)$", text, _re.M)
    if heading:
        language = heading.group(1).strip()
    try:
        return TechnologyStack(
            language=language or "unknown",
            framework=field("Framework", "unknown"),
            database=field("Database", "none"),
            testing_framework=field("Testing framework", "node --test"),
        )
    except Exception:  # noqa: BLE001 - a stack that will not validate is no stack
        return None


def _the_brief_this_run_was_given(workspace):
    """The operator's brief, from the path the audit was given, or "".

    `summarise_integration` takes it because two of its checks compare the
    product against the operator's own words rather than the run's
    restatement of them - see `_actions_the_brief_requires`. This script
    passed no brief at all, so those two checks were silently inert here
    while they were live at the gate, and the audit could report a clean
    product that the milestone reviewer would have blocked.

    Deliberately not `docs/product_intake.md`. That is the run's restatement,
    and reading it would reproduce the exact failure the checks exist to
    catch.
    """
    path = _BRIEF_PATH[0]
    if not path:
        return ""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError as exc:
        print(f"  could not read the brief at {path}: {exc}")
        return ""


#: Set from the command line, because the workspace does not contain the
#: brief - the run was started from a file outside it.
_BRIEF_PATH = [""]


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
    brief = _the_brief_this_run_was_given(workspace)
    report = summarise_integration(workspace, _the_stack_this_run_chose(workspace), brief)
    if not brief:
        print(
            "\n  NOTE: no brief given, so the two checks that compare the product "
            "against the operator's own brief did not run. Pass the brief as a "
            "third argument. Without it this report reads the run's own "
            "documents, which is exactly what a run that redefines a "
            "requirement out of existence has already edited."
        )
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


# Guarded, as `server/manage.py` guards its own entry point. Without this,
# importing the module runs it against whatever `sys.argv` happens to hold: a
# test that read `SAVED` from here died with
# `IsADirectoryError: Is a directory: 'tests/'` because pytest's first argument
# became the transcript path.
if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__.strip().splitlines()[2].strip())
    main(sys.argv[1])
    if len(sys.argv) > 3:
        _BRIEF_PATH[0] = sys.argv[3]
    if len(sys.argv) > 2:
        the_product(sys.argv[2])
