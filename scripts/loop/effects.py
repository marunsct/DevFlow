"""What each fix and switch did in one run, read from the run's own records (owner, 2026-10-22: review how effective our changes are).

    docker compose exec -T worker python - <run> < scripts/loop/effects.py

or `loop.sh effects [run]`. Read-only. For every change with a signal it leaves
in the transcript or the workspace, one line: how often it fired, and what it
saved or cost where that can be counted. A line reading "not reached" is a
change the run has not given a chance to act yet.
"""
from __future__ import annotations

import collections
import glob
import json
import re
import sys
from collections import Counter
from pathlib import Path

#: (label, where the signal lives, the text that marks it).
#: "request" - a model request's messages; "result" - a tool result;
#: "decision" - the decision log; "ledger" - a defect record's detail; "fix order" - a fix round's order record.
SIGNALS: list[tuple[str, str, str]] = [
    ("LF.191 approved lessons shown", "request", "LESSONS FROM EARLIER RUNS"),
    ("LF.188 a file given twice (should stay 0)", "request", "as they stood when this stage started"),
    ("IN.1 assumed answers handed to the architect", "request", "Open questions, answered"),
    ("CM.1 shared facts in a request", "request", "The facts this work is built and judged under"),
    ("PH.1 where things stand", "request", "Where things stand"),
    ("LF.203 the lead told why a release was held", "request", "Why the release was held back"),
    ("LF.186 where dependencies go", "request", "Declare every"),
    ("AY.1 a defect localised by one cheap call before its rewrite", "request", "You find where in a codebase a failure is caused"),
    ("AY.3 a write followed by the defect's tests - passing", "result", "they pass now. Your defect is fixed"),
    ("AY.3 a write followed by the defect's tests - still failing", "result", "after the write: they still fail"),
    ("PX.2/LF.197 a withheld tool refused", "result", "is withheld at this point of the stage"),
    ("LF.174 a re-run refused, nothing changed", "result", "nothing has been written since"),
    ("LF.202 a criterion moved to where its test can pass", "decision", "where a test of it can first pass"),
    ("AY.4 a defect left open at its call cap", "ledger", "model calls across its attempts"),
    ("LF.185 unstable criterion held as a dispute", "ledger", "pass when they run alone"),
    ("LF.1244 the latest round's defects fixed ahead of those carried over", "fix order",
     "Defects the latest test round raised fixed ahead of those carried over"),
    ("LF.1271 a fix that broke what worked was repaired forward and kept", "ledger",
     "repaired forward and kept, measured again"),
    ("LF.1271 a fix reverted after its forward repair failed", "ledger", "reverted after a forward repair failed"),
    ("LF.1272 a fix kept as progress: its tests moved forward", "ledger", "moved forward:"),
    ("LF.1299 a work order not finished sent back to its builder before the test round", "ledger",
     "Sent back to its builder before the test round"),
    ("LF.1299 a round's not-built defect sent to its builder, not a fixer", "ledger",
     "Not built: sent to the builder of its work order"),
    # Its words are `app.analysis.stand_in_tests.HEADING`.
    ("LF.1312 a unit test's stand-in shown hiding a rule the product keeps", "request",
     "--- A stand-in hides the rule this unit test expects ---"),
    # Its words are `app.analysis.shared_store_tests.HEADING`.
    ("LF.1316 unit tests shown sharing one store, with the records that leaked", "request",
     "--- These unit tests share stored data ---"),
]


def _text(value) -> str:
    return value if isinstance(value, str) else json.dumps(value, default=str)


def _lost(record: dict, usage: dict) -> bool:
    """A reply cut off at the cap with nothing in it - `run_kpis`' rule; by size alone only when its end is not recorded.

    By size alone a long reply that answered was lost: one architect's
    specification came back whole, as its tool call, at 33,613 tokens.
    """
    finish = record.get("finish_reason")
    if finish:
        answered = bool(str(record.get("text") or "").strip()) or record.get("tool_calls") not in (None, "", "[]", [])
        return finish == "length" and not answered
    return int(usage.get("output_tokens") or 0) >= 32_000


def _item_lines(item: str, module: str, lines_of) -> list[str]:
    """One item's report lines from its module, never fatal to the rest of the report (LF.1575).

    `loop.sh effects` pipes this script into the worker, whose deployed code may be older than the repository: a
    module it does not have is one line naming the item as not in the deployed code, and any other error in the item
    is one line naming it and the error.
    """
    import importlib

    try:
        return list(lines_of(importlib.import_module(module)))
    except ModuleNotFoundError as error:
        if error.name and (module == error.name or module.startswith(error.name + ".")):
            return [f"     -  {item}: not in the deployed code ({module})"]
        return [f"     !  {item}: its lines failed ({type(error).__name__}: {error})"]
    except Exception as error:  # noqa: BLE001 - one item's error is named, the report goes on
        return [f"     !  {item}: its lines failed ({type(error).__name__}: {error})"]


def effects(records: list[dict], decisions: str = "") -> list[str]:
    """The report's lines for these transcript records and this decision log."""
    counts: Counter = Counter()
    lost = lost_minutes = 0.0
    defects: Counter = Counter()
    salvaged: Counter = Counter()
    for record in records:
        if not isinstance(record, dict):
            continue
        kind = record.get("kind")
        if kind == "model_request":
            text = _text(record.get("messages"))
            for label, where, needle in SIGNALS:
                if where == "request" and needle in text:
                    counts[label] += 1
        elif kind == "tool_result":
            text = _text(record.get("content") or record.get("result") or record.get("output"))
            for label, where, needle in SIGNALS:
                if where == "result" and needle in text:
                    counts[label] += 1
        elif kind == "model_response":
            usage = record.get("usage") if isinstance(record.get("usage"), dict) else {}
            if record.get("salvaged"):
                # RS.1: its usage counts the cut-off reply too, so it is past
                # the cap, but it was answered (`app.models.reply_salvage`).
                salvaged[str(record["salvaged"])] += 1
            elif _lost(record, usage):
                lost += 1
        elif kind == "fix_order":
            text = _text(record.get("message"))
            for label, where, needle in SIGNALS:
                if where == "fix order" and needle in text:
                    counts[label] += 1
        elif kind == "defect":
            defects[str(record.get("event") or "")] += 1
            detail = _text(record.get("detail"))
            for label, where, needle in SIGNALS:
                if where == "ledger" and needle in detail:
                    counts[label] += 1
    for label, where, needle in SIGNALS:
        if where == "decision":
            counts[label] += decisions.count(needle)
    lines = [f"  {counts[label]:>4}  {label}" if counts[label] else f"     -  {label}: not reached"
             for label, _, _ in SIGNALS]
    lines.append(f"  {int(lost):>4}  replies lost to the output cap (the cost the reasoning work targets)")
    lines.append(f"  {salvaged['reasoning']:>4}  RS.1 replies cut off while reasoning, answered from their reasoning")
    lines.append(f"  {salvaged['continuation']:>4}  RS.1 replies cut off part way through their text, continued")
    if defects:
        lines.append("  defects: " + ", ".join(f"{event} {n}" for event, n in sorted(defects.items())))
    lines.extend(budget_lines(records))
    lines.extend(outbound_lines(records))
    # Each item's lines come from its own module, imported here and guarded on its own (LF.1575): the script runs in
    # the worker, whose deployed code may lack a module the repository already has.
    items = (
        # LF.1310: a testing stage's refused product change kept as its blocker, and the refusals each testing stage had.
        ("LF.1310", "app.tools.testing_blockers", lambda m: m.effects_lines(records)),
        # LF.1548: writes refused in another work order's file, and the hand-offs to its owner.
        ("LF.1548", "app.tools.foreign_file_handoffs", lambda m: m.effects_lines(records)),
        # PA.3 and PA.8: the product built before the testing work order, and errors in another's file kept as blockers.
        ("PA.3", "app.graph.built_before_testing", lambda m: m.effects_lines(records)),
        ("PA.8", "app.graph.its_own_to_fix", lambda m: m.effects_lines(records)),
        # HK.4, KS.6 and FX.11: whether a lookup note's defect was closed by the next fix, each lookup source's answer
        # rate, and for every fixer shown, whether its error was looked up or which gate stopped it.
        ("HK.4/KS.6/FX.11", "app.observability.lookup_notes",
         lambda m: [*m.outcome_lines(records), *m.source_lines(records), *m.gate_lines(records)]),
    )
    for item, module, lines_of in items:
        lines.extend(_item_lines(item, module, lines_of))
    lines.extend(review_reading_lines(records))
    items = (
        # KG.1: what the code graph named for each request that asked it, empty shares by language, and how fixers
        # were localised.
        ("KG.1", "app.analysis.project_graph", lambda m: m.effects_lines(records)),
        # KG.5-KG.8: what the code graph's answers changed where they were given - reads, repeat reads, opening
        # tokens, calls from a search to a write, notes at a write followed by an edit of a file named.
        ("KG.5", "app.agents.definitions_before_files", lambda m: m.effects_lines(records)),
        ("KG.6", "app.agents.graph_in_search_answers", lambda m: m.effects_lines(records)),
        ("KG.7", "app.tools.uses_named_at_the_write", lambda m: m.effects_lines(records)),
        ("KG.8", "app.agents.reviews_hold_the_change", lambda m: m.effects_lines(records)),
        # PF.2-PF.4: stuck defects' candidates held to the regression set, writes checked with the tests reaching
        # their files first, and reading stages opened on the lines chosen for them.
        ("PF.2", "app.graph.candidate_fixes_when_stuck", lambda m: m.effects_lines(records)),
        ("PF.3", "app.graph.tests_reached_first", lambda m: m.effects_lines(records)),
        ("PF.4", "app.agents.ranges_chosen_first", lambda m: m.effects_lines(records)),
        # PA.15: first fixes of a failing unit test sent to the product by their failure; PA.4: suites past their
        # author's room written a file at a time.
        ("PA.15", "app.analysis.unit_failure_side", lambda m: m.effects_lines(records)),
        ("PA.4", "app.graph.suite_by_file", lambda m: m.effects_lines(records)),
        # TR.2 and TR.6: reads while reading was withheld, refused by class against run; writes at the call budget.
        ("TR.2/TR.6", "app.agents.withheld_records", lambda m: m.effects_lines(records)),
        # LF.1543: the broken batches of fixes, by how each was settled; the fixers that wrote nothing kept out of
        # blame.
        ("LF.1543", "app.graph.batch_attribution", lambda m: m.effects_lines(records)),
        # TR.7 and TR.8: a writer's request's tool schema and the seldom-used tools it carried; lookups offered and
        # called.
        ("TR.7/TR.8", "app.agents.role_tool_lists", lambda m: m.effects_lines(records)),
        # LF.1570: narrow reads widened to the room, and reads and input tokens per review and per fixer visit.
        ("LF.1570", "app.agents.read_windows", lambda m: m.effects_lines(records)),
        # IK.3: stage visits held to a reasoning budget, and the replies still cut off while reasoning.
        ("IK.3", "app.models.reasoning_budget", lambda m: m.effects_lines(records)),
        # LF.1524: fast delivery's design findings held as product-breaking, those not held, and the revisions they
        # took.
        ("LF.1524", "app.graph.fast_design_gate", lambda m: m.effects_lines(decisions)),
        # LF.1547: rewrites after a revert told what broke, repeats stopped, doubtful schema findings set aside.
        ("LF.1547", "app.graph.what_a_revert_broke", lambda m: m.effects_lines(records)),
        # Beside what fired: a switch that was on, had its chance and did nothing (`CHANCES`); and the switches whose
        # acting the records cannot show at all: each needs a signal of its own before it can be judged.
        ("switch chances", "app.observability.switch_firing",
         lambda m: [*m.chance_lines(records, decisions), *[line for line in [m.no_signal_line(records)] if line]]),
    )
    for item, module, lines_of in items:
        lines.extend(_item_lines(item, module, lines_of))
    return lines


def outbound_lines(records: list[dict]) -> list[str]:
    """LF.1291 (HK.5): what left the machine through the one outbound gate (`app.tools.outbound`, records `outbound`):
    queries sent by way of each channel, how many had the product's words taken out, and names not sent at all."""
    sent = [r for r in records if isinstance(r, dict) and r.get("kind") == "outbound"]
    if not sent:
        return ["     -  LF.1291 outbound queries through the one gate: not reached"]
    refused = [r for r in sent if r.get("refused")]
    left = [r for r in sent if not r.get("refused")]
    by_channel = Counter(str(r.get("channel") or "?") for r in left)
    cleaned = sum(1 for r in left if int(r.get("removed") or 0) > 0)
    return [f"  {len(left):>4}  LF.1291 outbound queries through the one gate ("
            + ", ".join(f"{channel} {n}" for channel, n in by_channel.most_common())
            + f"); {cleaned} with the product's words taken out; {len(refused)} not sent (the product's own name)"]


def budget_lines(records: list[dict]) -> list[str]:
    """LF.1274: how many opening requests were checked against their input budget, how many were past it and cut, by
    how much, and which sections were cut or left out most (`app.agents.request_budget`, records `request_budget`);
    and, apart, the stages whose memory would have been cut with `REQUEST_BUDGET_FOR_EVERY_STAGE` on (`applied`
    false: sent as built)."""
    checked = [r for r in records if isinstance(r, dict) and r.get("kind") == "request_budget"]
    label = "LF.1274 opening requests past their input budget, cut to it"
    if not checked:
        return [f"     -  {label}: not reached"]
    past = [r for r in checked if int(r.get("sent") or 0) < int(r.get("built") or 0)]
    cut = [r for r in past if r.get("applied") is not False]
    would = [r for r in past if r.get("applied") is False]

    def median(values: list[int]) -> int:
        ordered = sorted(values)
        return ordered[len(ordered) // 2]

    def described(group: list[dict]) -> str:
        named: Counter = Counter(str(n).split(" (")[0].split(" as its outline")[0]
                                 for r in group for n in [*(r.get("cut") or []), *(r.get("left_out") or [])])
        kinds = Counter(re.sub(r"_\d+(?:_\d+)*$", "", str(r.get("stage") or "")) for r in group)
        return (f"built median {median([int(r.get('built') or 0) for r in group]):,} -> sent "
                f"{median([int(r.get('sent') or 0) for r in group]):,} characters, target "
                f"{median([int(r.get('target') or 0) for r in group]):,}; "
                + ", ".join(f"{kind} {n}" for kind, n in kinds.most_common(4))
                + ("; most cut: " + ", ".join(f"{name} {n}" for name, n in named.most_common(3)) if named else ""))

    lines = [f"  {len(cut):>4}  {label} ({len(checked)} checked" + (f"; {described(cut)})" if cut else
                                                                     ", none cut)")]
    if would:
        lines.append(f"  {len(would):>4}  LF.1274 stage memories past the budget, sent as built "
                     f"(REQUEST_BUDGET_FOR_EVERY_STAGE off; would be {described(would)})")
    return lines


#: The stages whose memory holds what they read (`review_files.REVIEW_STAGES`, `READING_STAGES` and
#: `WRITING_STAGES`), by the start of their stage names: the reviews (LF.1284), the technical lead, the suite's review
#: and the test rounds (LF.1286), the suite's author and the builders (LF.1288).
_REVIEW_STAGE = re.compile(r"^(?:security_review|advice_review|code_review|milestone_review|acceptance_review"
                           r"|technical_lead|test_round|acceptance_author|specialist_)")
#: The words a summariser's request opens with - langchain's, and the harness's work note (PA.2, LF.1360): one such
#: request is one summary of the stage.
_SUMMARISER = ("Context Extraction Assistant", "You keep the work note of one stage")


def _arguments(record: dict) -> dict:
    """A tool call's arguments: a transcript records them as a mapping or as its text."""
    args = record.get("args")
    if isinstance(args, str):
        import ast

        try:
            args = ast.literal_eval(args)
        except (ValueError, SyntaxError):
            args = None
    return args if isinstance(args, dict) else {}


def review_reading_lines(records: list[dict]) -> list[str]:
    """LF.1284/LF.1285/LF.1286/LF.1288: per review, reading or writing stage, its summaries and its `read_file` calls
    per distinct file, whole against by range (LF.1287: the memory outlines the files it does not hold, with their
    lines). Measured on one medium run before the files they read were held in the memory: 155 reads of 21 files and
    11 summaries in one security review, 243 reads of 20 files and 21 summaries in a later sprint's technical lead;
    the target is at most 1.2 reads a file and no summary."""
    reads: dict[str, Counter] = collections.defaultdict(Counter)
    ranged: Counter = Counter()
    summaries: Counter = Counter()
    for record in records:
        if not isinstance(record, dict):
            continue
        stage = re.sub(r"_\d+(?:_\d+)*$", "", str(record.get("stage") or ""))
        if not _REVIEW_STAGE.match(stage):
            continue
        if stage.startswith("acceptance_author"):
            stage = "acceptance_author"  # one author a batch of criteria, named after it
        if record.get("kind") == "tool_call" and record.get("tool") == "read_file":
            args = _arguments(record)
            path = str(args.get("file_path") or args.get("path") or "").strip().lstrip("/")
            if path:
                reads[stage][path] += 1
                if args.get("offset") not in (None, "", 0) or args.get("limit") not in (None, ""):
                    ranged[stage] += 1
        elif record.get("kind") == "model_request" and any(said in _text(record.get("messages")) for said in _SUMMARISER):
            summaries[stage] += 1
    label = "LF.1284/LF.1286 reading stages: summaries, and reads per distinct file (target <= 1.2, no summary)"
    stages = sorted(set(reads) | set(summaries))
    if not stages:
        return [f"     -  {label}: not reached"]
    lines = [f"        {label}:"]
    for stage in stages:
        total, distinct = sum(reads[stage].values()), len(reads[stage])
        per_file = f"{total / distinct:.1f}" if distinct else "0"
        lines.append(f"  {summaries[stage]:>4}  {stage}: summaries; {total} reads of {distinct} files, "
                     f"{per_file} a file; {total - ranged[stage]} whole, {ranged[stage]} by range")
    return lines


def order_probe_line(probed: dict) -> str:
    """What the order probe recorded (`ORDER_PROBE`), to read beside the unstable disputes the signals above count."""
    return (f"  {len(probed.get('unstable') or []):>4}  tests failing only when their file runs alone "
            f"({probed.get('files_run', 0)} files probed, {probed.get('files_without_a_report', 0)} without a report)")


def draft_lines(records: list[dict]) -> list[str]:
    """How the run's drafted files ended (HR2.P.5): first-pass and content-refusal acceptances, repairs kept, left to the loop."""
    drafts = [r for r in records if r.get("kind") == "draft"]
    if not drafts:
        return []
    files = {str(r.get("path")) for r in drafts}
    first = sum(1 for r in drafts if r.get("attempt") == "first" and r.get("outcome") == "accepted")
    refusal = sum(1 for r in drafts if r.get("attempt") == "content-refusal" and r.get("outcome") == "accepted")
    repairs = [r for r in drafts if str(r.get("attempt", "")).startswith("repair-")]
    kept = sum(1 for r in repairs if r.get("outcome") == "accepted")
    left = [str(r.get("outcome", ""))[len("left to the loop: "):] for r in drafts
            if str(r.get("outcome", "")).startswith("left to the loop")]
    why = collections.Counter(reason.split(":")[0][:60] for reason in left)
    return [f"drafts: {len(files)} file(s), {first} accepted at the first pass, {refusal} after a content refusal; "
            f"{len(repairs)} repair pass(es), {kept} kept; {len(left)} left to the loop"
            + (" (" + ", ".join(f"{n} {reason}" for reason, n in why.most_common(3)) + ")" if left else "")]


def setup_lines(records: list[dict], scope: dict | None = None) -> list[str]:
    """Each setup proof (replayed or written, level reached, set aside) and what a setup stage wrote beyond its files (HR2.SS.4)."""
    out = []
    for r in (r for r in records if r.get("kind") == "setup"):
        out.append(f"setup {r.get('source')}: {'proven' if r.get('ok') in (True, 'True') else 'not proven'} "
                   f"(reached {r.get('level') or 'none'})" + (f", set aside {r['set_aside']}" if r.get("set_aside") else "")
                   + ("" if r.get("ok") in (True, "True") else f": {str(r.get('problem') or '')[:160]}"))
    asked = set((scope or {}).get("files") or [])
    project = str((scope or {}).get("project") or "")
    if asked:
        beyond: dict[str, int] = {}
        for r in records:
            if not str(r.get("stage", "")).startswith("stack_setup") or r.get("kind") != "tool_call" \
                    or r.get("tool") != "write_artifact":
                continue
            args = r.get("args") or {}
            path = str(args.get("relative_path") or "")
            inside = path[len(project) + 1:] if project and path.startswith(project + "/") else path
            if path and path not in asked and inside not in asked:
                beyond[path] = len(str(args.get("content") or "").splitlines())
        out.append(f"setup scope: {len(asked)} framework file(s) asked; {len(beyond)} other file(s) written "
                   f"({sum(beyond.values())} lines; the declaration, smoke tests and manifests are among them)" + (": " + ", ".join(sorted(beyond)[:6]) if beyond else ""))
    return out


def contract_probe_lines(stored: dict) -> list[str]:
    """One line per probe of the locked contract: lines considered, asked, probed, and the skip reasons counted (HR2.Q.9)."""
    out = []
    for kind, record in sorted(stored.items()):
        reasons = collections.Counter(str(s.get("reason", "")) for s in record.get("skipped") or [])
        why = "; ".join(f"{n} {reason}" for reason, n in reasons.most_common(4))
        out.append(f"contract probe {kind}: {record.get('considered', 0)} lines, {record.get('asked', 0)} asked, "
                   f"{record.get('probed', 0)} probed" + (f"; skipped: {why}" if why else "")
                   + (f"; {record['outcome']}" if record.get("outcome") else ""))
    return out


def main(run: str) -> None:
    paths = sorted(glob.glob(f"/app/data/transcripts/{run}*.jsonl"))
    if not paths:
        print("no transcript yet")
        return
    records = []
    for line in open(paths[0], errors="replace"):
        try:
            records.append(json.loads(line))
        except ValueError:
            continue
    decisions = ""
    for log in glob.glob(f"/app/data/workspaces/*/workspace-{run}*/docs/decision_log.md"):
        decisions = Path(log).read_text(encoding="utf-8", errors="replace")
    print(f"effects of the changes in {run} ({len(records)} records)")
    print("\n".join(effects(records, decisions)))
    for line in draft_lines(records):
        print(line)
    scope = None
    for found in glob.glob(f"/app/data/workspaces/*/workspace-{run}*/.harness/setup-scope.json"):
        try:
            scope = json.loads(Path(found).read_text(encoding="utf-8"))
        except ValueError:
            pass
    for line in setup_lines(records, scope):
        print(line)
    for probed in glob.glob(f"/app/data/workspaces/*/workspace-{run}*/.harness/order_probe.json"):
        print(order_probe_line(json.loads(Path(probed).read_text(encoding="utf-8"))))
    for probed in glob.glob(f"/app/data/workspaces/*/workspace-{run}*/.harness/contract-probe.json"):
        print("\n".join(contract_probe_lines(json.loads(Path(probed).read_text(encoding="utf-8")))))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
