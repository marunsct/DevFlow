# Second harness review (HR2) - shared brief for every reviewer

Owner request, 2026-11-07 22:3x JST: "a deep review and research on how to improve the harness - each stage, the
harness's steps, and the product. Read the old review and planned items as well, do a comprehensive check, and
append any improvement point to the existing plan. Be as thorough as possible."

You are one of eight read-only reviewers, each on one area. Your report is merged into `docs/harness-review.md`
(the first review, 2026-11-07 morning) as its second part, so **propose only what is new, or what the first review
got wrong**, with evidence.

## The harness

- Repo: `/home/arun/Desktop/langchain` (read `docs/PRODUCT.md` for what it is; the graph is in
  `src/app/graph/workflow.py`, 43 nodes: product_manager, tools_models, stack_selector, specialist_consultation,
  principal_architect, architecture_review, scaffold, acceptance_author, acceptance_review, scrum_master,
  technical_lead, specialist_dispatch/worker/gather, ci_gate, code_review, test_and_triage, defect_remediation,
  defect_fix_worker/gather, security_review, advice_review, review_worker/gather, acceptance_dispute,
  milestone_review, sprint_advance, change_request, escalation(_accept/_retry), release, complete, failed; the
  user_review_* nodes are the approval mode's gates).
- Stack packs: `src/app/stacks/packs/`; stack-specific knowledge lives only there and in `src/app/plugins/seed.py`.
- Switches: `src/app/switches.py` (BUILT_IN, BUNDLES, GROUPS); the register of everything under measurement is
  `docs/measuring.md` (M1-M8).

## What to read first (in this order)

1. `docs/harness-review.md` - the first review: time shares, five cross-cutting findings, §3 per area, the plan
   (Phase 0-3, E), and its progress notes at the end.
2. The first reviewer's notes for your area: `/tmp/claude-1000/-home-arun-Desktop-langchain/d4298d72-a977-42bb-8a37-f5c3120002bc/scratchpad/review/0N-*.md`.
3. `docs/measuring.md` - what is built behind a switch, what is to build, what was measured and closed.
4. `docs/scaffolding-plan.md` (SF items), `docs/work-batching.md` (WB), `docs/single-writer-review.md` (SW/SP).
5. `docs/improvement-plan.md` - the master plan (6,200 lines). Appendix M (line ~5579) indexes every item;
   M.2 (line ~5878) lists every audit fix as an LF row. `grep -n "| LF\.6[5-8][0-9] |"` for today's fixes.
   `docs/review-findings.md` and `docs/research-findings.md` are the older evidence and research logs.

## What changed since the first review (all on 2026-11-07, after 11:00 JST)

Built, always on: LF.665 (a layered setup's guide names no other framework), LF.666 (builders see the setup's
proven entry code and keep it), LF.667/667b/668 (a long failure keeps its raised error; once), LF.669 (fixers after
a broken-start revert are told the streak and the error - 128 such reverts over 37 runs), LF.670 (an empty unit
report is measured again before "no unit tests"), LF.671 (a probe's finding is settled by the probe), LF.672/673
(a setup is proven by its smoke tests; proven code without scratch files), LF.674 (D8), LF.675 (R6: `cd` into the
working directory), LF.676 (a reused measurement still runs the own-start check - falcon 6 shipped 0/9), LF.677
(C7 finish reasons), LF.678 + `loop.sh suite-checks` (Q1: per-check findings recorded and reported), LF.679 (P4: a
finished work order owns no file), LF.680 (F8: stable defect ids; rewrites record `shown`), LF.681 (E1: impact
leaves out spanning runs), LF.682 (a long model call is not an orphan gap), LF.683 (the reasoning tag is read
from the server the run is pinned to - planning replies had run to 42k tokens past a 20k cap), LF.684/685
(SF.0b: library hygiene, nightly replay), SF.0c (`loop.sh stack-misses`), LF.688 (`ship-live` says when a deploy
did not land). Built behind switches, off: M6 `SETUP_SCOPE_GUARD` (LF.686), M7 `MILESTONE_EVIDENCE_GATE` (LF.687,
G3). Measured and closed: G1, G6, P5, R2, R3. Candidate: M8 (rewrite memory 60-70k chars).

Runs today (all mixed-version, learning runs): notes-api-falcon 4-9 = 9/9, 9/9, 0/9 (false acceptance, LF.676),
9/9, 9/9, 9/9; tasks-api 4 = 10/10 (escalated, LF.671), tasks-api 5 = 10/10; notes-api 4 = 9/9. Live now:
web-todo 5 (run-0c34fb58), fullstack-bookmarks-py 8 (run-ffa696e6) - leave them alone.

## Where the data is (read-only)

- Transcripts: `/app/data/transcripts/<run>.jsonl` inside the worker container (`docker exec langchain-worker-1
  python3 -c '...'`). One JSON record a line: `kind` in model_request (blocks, tools, messages), model_response
  (text, tool_calls, usage, finish_reason, reasoning_chars, salvaged), tool_call/tool_result (tool, args,
  content, status), defect (event: raised/shown/fixed/reverted/left open/closed..., defect_id, round, index,
  description, detail), model_error; `stage`, `at` (UTC).
- Workspaces: `/app/data/workspaces/default/workspace-<run>/` - the product, `docs/*.md` (intake, stack,
  specification, sprint plan, stage summaries), `.harness/` (decisions.json, acceptance-result.json,
  acceptance-history.jsonl, check-findings.jsonl, start_breaks.json, stack-pack.json, ci.json, ...).
- Scores: host `data/bench/run-*.json` (benchmark, score, passed, total, tests, completion_gaps, false_acceptance,
  visible_score), `data/bench/mutation/`. KPIs: `data/kpi/ledger.csv` (227 rows; harness_commits, mixed_versions,
  active_minutes, defect_fix_stages, defects_fixed, defects_left_open, fixes_reverted, tool_failure_rate,
  redundant_read_rate, ...), `data/kpi/<run>.json` (per stage).
- Tools: `scripts/loop/loop.sh` audit|defects|effects|patterns|impact|suite-checks|stack-misses|kpi|reads|timing
  <run>. Setup library: `/app/data/proven-setups/` (+ `failed/`). Hidden tests: `benchmarks/<family>/`.
- Never print `.env` values, never start a run, never call the owner's model servers, never write under `src/`,
  `docs/`, `tests/` or the workspaces. WebSearch/WebFetch for research is fine.

## Rules every proposal must meet (the owner's standing rules)

- Evidence first: counts, minutes, scores from the stored data; cite code as `file:line`.
- No duplicates: grep `docs/harness-review.md`, `docs/measuring.md` and `docs/improvement-plan.md` for the idea
  (by keyword and by LF/HR/SF/WB/SW/SP/PX/... id). If an existing item should change shape, say so and why.
- Classify each item: **bug or quality fix** (always on, no switch) or **doubtful** (own switch, default off,
  target KPI, two runs per family on and off). Efficiency changes are always doubtful.
- Each item names a test provable to fail on the old code; a new prompt rule gets the banned-word test (task,
  tasks, to-do, todo, button, click, checkbox).
- Technology-, framework- and product-agnostic: stack facts only in packs or `seed.py`; no run ids in code;
  plan for small and large codebases alike.
- Keep the owner's features: dynamic agent-instruction injection, the parallel/linear toggle, the sprint
  summary, work orders/templates/Sprint Record.
- Prefer execution over text heuristics; prefer asking for deltas over whole artifacts; measure each mechanism.

## Your report

Write `/tmp/claude-1000/-home-arun-Desktop-langchain/d4298d72-a977-42bb-8a37-f5c3120002bc/scratchpad/review2/<NN>-<area>.md`
(your NN and area are in your prompt), at most ~400 lines, with these sections:

1. **What exists** - the stages and code of your area now (file:line), including what today's fixes changed.
2. **Measured** - new numbers (today's 13 runs where possible, the 250+ stored runs otherwise): time, outcomes,
   failure modes, recurring notes totalled across runs with their cause.
3. **The first review's items in this area** - each: built / open / wrong-or-reshape, with evidence.
4. **Research** - how leading products and 2025-2026 papers do it (search; cite with dates), what fits here.
5. **New items** - `HR2.<area>.<n>`: evidence, the change, the test, bug-or-switch, KPI, size (S/M/L), risk.
6. **Priority order** with the expected effect in minutes or score, and which items to build first.

Be thorough: read the stage's prompts and the code paths, not only the notes; look for mechanisms that are built
but never fire (`loop.sh effects`), checks whose precision nobody measured, places where a whole artifact is
re-asked, and waste the audits would not see in ten-minute windows. Finish within about 90 minutes.
