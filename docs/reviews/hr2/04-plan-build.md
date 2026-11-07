# HR2.P - Planning and building (scrum master, technical lead, drafting, builders, guards, ownership, memory)

Reviewer 04, 2026-11-07/08. Read-only. Data: the 14 finished transcripts dated 11-07 (JST runs 1-13 plus the
4fa87240 run that finished 01:39 UTC), the 123 finished runs since 11-01, and all 534 stored transcripts; code as of
`2c8e911b`. Scripts used are in `scratchpad/review2/measure04.py`, `m2.py`-`m7.py` (run inside the worker).

## 1. What exists

- **Scrum master** `workflow.py:9725-9945`: one model call for a `SprintPlanOutput`, then deterministic
  corrections (keep the better of two plans; fold setup sprints; cap the sprint count; assign every criterion;
  move criteria to where their tests can pass; ask once more for unassigned measures and for work built ahead).
  The harness's own plan on `StageGaveNoAnswer`.
- **Technical lead** `workflow.py:9947-10380`: fast delivery first tries the harness's plan
  (`planned_work.work_orders_from_the_specification`, `planned_work.py:58-115`: one work order per role from the
  specification's file plan, `BUILT_SHARE` guard); otherwise a model call. Then, in order: paths inside the project,
  `cd` dropped, test cases from criteria, named tests given to testing, a testing work order added
  (`work_orders.py:140-250`), **readiness** (`readiness_problems`, `work_orders.py:778-893`, 9 rules), up to
  `_max_structured_retries()` resends with `readiness_feedback` ("return the whole plan again", `:895-903`) and the
  plan sent back verbatim as JSON; the better of the attempts dispatched with "Not ready when dispatched" notes;
  **after** readiness: `with_the_harness_s_files_left_out` (`:406-440`), refused commands noted, borrowed files
  noted, `_record_the_owners` (`workflow.py:1164-1188`, LF.679: a done work order owns nothing).
- **Drafting** `drafting.py:462-560`: one 9k-token call per file (code first, then tests shown the drafted code), a
  content refusal re-drafts once (`CONTENT_REFUSALS`), then `_repaired_where_the_compiler_says` (`:380-411`, 2
  passes). A work order drafted whole is done; the rest go to the agent loop. Outcomes go to the log only - the
  transcript has no record of which draft was rejected, repaired or left to the loop.
- **Dispatch/worker/gather** `workflow.py:10443-10720`: linear loop or `Send` fan-out by `execution_mode`
  (every run since 11-01 was linear: 374 provenance records, 0 parallel). Each builder request carries the sibling
  work orders, the interface design, fixes to keep, the specification slice, shared facts (CM.1), the ledger (CM.3),
  where-things-stand (PH.1) and the code-graph slice (CG.3) - all on today (provenance `switches_on`).
- **Guards** `repository.py:2090-2300` (setup scope M6; another work order's file; counts `_again_and_again`,
  `_outside_its_own_files`; delete/move held to the same) and `:6700-6760` (a rewrite that drops definitions:
  warn, then refuse on the second loss). Ownership table `WORK_ORDER_FILES` written by `record_work_order_files`.
- **Project memory** `agents/project_memory.py`: 30% of the window, 240k chars max, documents first; a read of a
  held, unchanged file is answered with a pointer (`HELD_POINTER`), a second pointer ends reading.
- Today's fixes in this area: LF.666 (builders see the setup's proven entry code), LF.679 (P4 measured form),
  LF.683 (reasoning tag per server, so salvage keeps reasoning closed), LF.686 (M6 setup scope, off).

## 2. Measured

**Time (14 runs of 11-07; stage spans from first to last record).** technical_lead 378 min (11.5% of all stage
minutes, third after defect_fix 22% and acceptance_author 16%), drafting 281 min (8.6%), specialist_* 113 min
(3.4%), scrum_master 62 min (1.9%). Planning median 20 min a run, p90 65; building (agent loop) median 0, p90 6;
drafting median 2, p90 61. Since 11-01 (123 runs): planning median 15 min, the lead's model calls alone 1,021 min.

**Reply sizes and the cap.** Today: scrum_master 38 replies, median 5.5k output tokens, p90 22.6k, 5 at the
cap (13%); technical_lead 80 replies, median 4.2k, p90 22.2k, 15 at the cap (19%). All 20 were salvaged
(`salvaged='reasoning'`), and each still yielded a `MilestonePlanOutput`/`SprintPlanOutput` tool call - so the cap
costs time, not the plan. **A capped planning reply is 17% of planning replies and 48% of planning model-call
minutes** today (82 of 170 min; 11-06: 179 of 297; 11-01: 163 of 326). Reasoning on a capped reply: median
80-105k characters (~20-26k tokens, i.e. the whole budget is thinking); on an uncapped reply 4-9k characters.
Across all stages today the cap took 191 of 1,199 call-minutes (16%); planning holds 43% of that. The run that
finished last today (2e7d285b, 12:35 UTC) still had 4 capped planning replies of 11, so LF.683 did not end them;
it only stops the reasoning being reopened in the text.

**Input size.** Since 11-01, median input tokens: technical_lead 57k (p90 124k), scrum_master 45k, specialist
76.5k (p90 106k), drafting 8.9k. The lead's first request in 2e7d285b: system 16k chars, project memory block
131k chars (specification with 13 ADRs 30k, sprint plan, then product files), workspace listing 1.7k. After the
lead's read turns the planning call sits at 94-140k input tokens (44a25a80, 2e7d285b).

**The lead reads what it was handed.** Since 11-01 the lead made 602 `read_file` calls; **453 (75%) were answered
by the memory pointer** ("is in the project memory at the start of this conversation") - 3.7 pointer turns a run,
each a full-context model turn (~1 min, 40-60k input tokens). Top paths: main.py 52, index.html 43,
requirements.txt 32, app.js 32, app.ts 27. Redundant-read rate (same stage, same args) today: technical_lead 0.36,
specialist 0.33, scrum_master 0.19 (all-time 0.36 / 0.34 / 0.16).

**Readiness resends.** All-time 1,075 resends in 325 runs (the 10-02/10-03 days alone 308). Since 11-01: **140
resends in 123 runs (1.1 a run), 151 model-call minutes; today 21 in 9 of 14 runs**. Reasons since 11-01 (one
resend lists several):

| Reason (rule in `readiness_problems`) | Count | Mechanical fix available |
|---|---|---|
| a work order names the locked acceptance suite file | 50 | yes: `with_the_harness_s_files_left_out` already drops it - but runs after readiness (`workflow.py:10265`) |
| a work order names no `files` (nearly always the testing order "Run the acceptance suite...") | 45 | yes: a run-only order is a `verification` line, or gets the specification's planned test files |
| `verification` command the sandbox refuses (no shell; `cd`) | 30 | yes: `with_refused_commands_noted` already annotates it - after readiness (`workflow.py:10291`) |
| carried-forward decisions missing | 12 | partly (ask only for the missing lines) |
| no testing work order | 11 | yes: `with_a_testing_work_order` runs before; the 11 are plans it did not reach |
| scope names a file nobody is given: start.sh 9, bookmarks.json 7, notes.json 6, app.ts 4, args.json 3, main.test.py 3 | ~35 | mostly: `_data_the_product_writes` (`work_orders.py:601-626`) reads `data_dir_env` from the pack, so on a custom stack (Falcon: no pack) every data file is "unbuilt"; start.sh is the harness's |
| no work orders at all | 4 | no (a real re-plan) |

So about 125 of 140 are problems the harness can repair without a model call. **6 of the 140 (4 today) sent
back the harness's own plan** (`"Every file the specification plans"`): fast delivery's plan failed the harness's
own readiness rule (notes.json on a pack-less stack) and the whole sprint went to the lead for 4-5 calls
(2e7d285b: 11:57-12:30 UTC, 2 capped replies). After every resend the lead's first turn is a `read_file`, not a
plan: the resend request (130-240k chars) carries the full prompt plus the JSON plan, and the model re-reads.

**Scrum master re-asks.** Today 38 replies in 14 runs = 2.7 a run (the one-call stage has a tool loop: 21 reads,
19% redundant). Gap/built-ahead re-asks could not be separated by text; `loop.sh effects` shows LF.202 "not
reached" on 2e7d285b.

**Drafting.** Since 11-01: 827 drafting requests, median output 1.2k tokens (p90 3.2k, max 35k - a draft that
ran away); **111 (13%) were compiler repair passes** ("The compiler reports, in the draft above"). Whether a repair
fixed the file, or a work order was left to the agent loop, is not recorded (log lines only). Builders (the agent
loop) ran in **47 of 123 runs since 11-01 (6 of 14 today)**, median 1 stage a run, median 31 tool calls a stage.

**Builder tool failures.** All-time 430 `status: error` plus ~1,900 refusals returned as `success` with
"Nothing was written" / "Refusing" (the KPI `tool_failure_rate` sees only the former: 1.4%). Grouped all-time:
edit_artifact ownership 385, replace_lines parse 381, write_artifact other refusal 274, write_artifact ownership
266, edit_artifact parse 155, write_artifact parse 144, read_file not found 143, replace_lines ownership 136.
Since 11-01 the picture is different: **ownership 64 (11-05: 31, 11-06: 33, 11-07: 0)**; withheld-tool refusals
80 (run_terminal_command 23, read_file 16, edit_artifact 15, delete 10, write 9, module_exports 8); "already
contains exactly this content" 11; "already_applied" 20; "refused 3 writes outside its own files" 3. Today's 6
builder stages made 97 calls with 1 failure. LF.679 has had no builder run to show on; the 11-05/06 refusals
predate it and 42 of 64 named an owner that never ran (its files drafted), which LF.679 removes.

**Builders rewriting the setup's files** (LF.666): not measurable from the transcript - drafting writes are harness
writes with no `tool_call` record and the setup's file list is not kept beside the plan. Item HR2.P.7 below.

**Parallel/linear toggle.** Unchanged and unmeasured since 11-01 (0 parallel runs); `_that_do_not_share_a_file`
staggering and the per-worker pause fix are only exercised by tests.

## 3. The first review's items in this area

| Item | Status | Evidence and verdict |
|---|---|---|
| P1 repair the plan, deltas keyed by label | open, **confirmed and reshaped**: it is a bug/quality fix, not a switch, and most of it needs no model call at all | 125 of 140 resends since 11-01 are mechanical and two of the three top causes are already repaired by code that runs *after* the check (`with_the_harness_s_files_left_out`, `with_refused_commands_noted`). Reorder first; the delta request is for the residue (carried decisions, no work orders) |
| P2 re-plan work orders from failures (switch) | open | 43 of 93 runs re-planned in the first review's window; since 11-01 the lead's "last_attempt" request exists (`_the_last_failed_attempt_at_this_sprint`), unmeasured. Keep as a switch, lower priority than P1/HR2.P.1 |
| P3 edit format by tier and file size (switch) | open; **partly wrong** on the data | Today's builders used edit_artifact 18/19 ok, write 6/6; `replace_lines` is already off (P.1 demote, `LINE_EDITS`). Diff-XYZ (NeurIPS 2025) and Aider's edit leaderboard say whole-file or lenient search/replace for a 30B Qwen and nothing for unified/line diffs; the 41-44% figure was `replace_lines`, already demoted. P3 shrinks to "anchored search/replace with lenient matching + whole-file for small files" and is only worth a switch once builders run again often (47 of 123 runs) |
| P4 ownership -> request_change | built in measured form (LF.679) | 0 refusals since; no builder run with a planned owner yet. Keep `loop.sh effects` watching "another work order's file" |
| P5 harness deletes its scratch files | not built on merit (owner 10-20 decision) | agreed; 2 builder deletes today, both answered |
| P6 two draft candidates for compiler-rejected files (switch) | open; **premature** | 13% of drafting calls are repair passes but their outcome is not recorded, so a candidate arm cannot be judged. Record first (HR2.P.5), then decide |
| P7 readiness rules in the schema | open; **reshape**: the prompt already names every rule (L.7); put the rules into the harness's own plan builder and the post-readiness repairs instead | 4 harness plans sent back today were the harness disagreeing with itself |
| WB.5 work orders per milestone (batching) | not built; **not supported by the data** | the cost is per turn of thinking (work-batching §8), and a capped planning reply is 100% reasoning. Batching the plan would multiply turns. Superseded by HR2.P.2 |
| WB.8 `loop.sh scan` | built | the audit has no line for "capped planning minutes" or "pointer reads"; add them (HR2.P.8) |
| SW/SP (single writer, workers learn) | direction set 10-24 | fast delivery is in practice single-writer-by-harness: 76 of 123 runs had no builder stage. SW.1 (defects by source) still the missing number |
| M6 `SETUP_SCOPE_GUARD` | built, off | unchanged; measurement planned |

## 4. Research (searched 2026-11-07; dates are source dates)

- **Plan-then-apply.** Aider architect/editor (2024-09-26): a reasoning model plans in prose, an editor model
  applies in "whole"/"editor-diff"; pairs beat solo (GPT-4o-mini 55.6 -> 60.2 self-paired). Claude Code plan mode
  (docs, fetched 11-07) and Cursor Plan Mode keep the plan as an editable file revised by instruction ("approve +
  manual edits", "keep planning"), never regenerated from scratch; Cursor advises re-running with a more specific
  plan over steering mid-build. Fit: the sprint and milestone plans are JSON documents the harness holds; repair
  them in place and ask the model only for the lines that changed.
- **Edit formats for small models.** Diff-XYZ (JetBrains, arXiv 2510.12487, NeurIPS 2025): Qwen2.5-Coder-32B
  apply EM search/replace 0.92 vs udiff 0.84; 7B 0.75 vs 0.58; line-marked udiff worst; "smaller open models
  benefit little from any formatting choice". Aider edit leaderboard: Qwen2.5-Coder-32B whole 72.9% (100%
  well-formed) vs diff 71.4% (94.7%); Qwen3-32B whole 45.8% vs diff 41.3%; all sub-14B entries run "whole".
  Aider's 2023-12 lesson: lenient matching cut edit errors 9x; asking for whole-block edits cut them 30-50%.
  SWE-agent (2405.15793): after one failed edit the next succeeds only 57% of the time; a linter in the edit tool
  +3 points. Cascaded Code Editing (2604.19201, 2026-04): a fine-tuned 14B "apply" model +11% Pass@2; sub-1B
  mergers ~0. Fit: whole-file below a size, anchored search/replace with lenient whitespace above, compiler check
  in the tool (already: parse/compiler refusals), escalate to whole-file after the first failed edit of a file.
- **CodePlan** (2309.12499, FSE 2024): a plan graph over a tree-sitter dependency graph, extended after each edit
  from the oracle's errors - repair, not regenerate; RPG/ZeroRepo (2509.16198, 2025-09) extend it to repo
  generation. Fit: the harness's `project_graph` slice and `interface_changes` are the pieces; the missing step is
  feeding readiness/compiler findings back as *plan edits*.
- **Harness studies 2025-2026.** "The Complexity Trap" (2508.21433, 2025-10): observation masking equals LLM
  summarisation at half the cost (Qwen3-32B); OpenHands condensers (2605.18854, 2026-05) change no outcome and
  LLM condensers add 24-94% tokens. "Beyond Resolution Rates" (2604.02547, 2026-04, 9,374 trajectories):
  context-before-edit and validation predict success; length does not once difficulty is controlled. IBM "From Plan
  to Action" (ASE 2026, 16,991 SWE-agent trajectories): a good plan helps, a subpar plan hurts more than none;
  extra early phases degrade; periodic plan reminders cut violations. Empirical Study of Harness Design
  (2609.20804, 2026-09, 176 settings): planning raises accuracy for weaker models and predefined tools help
  bash-weak ones. Kiro (2026-02-23): a one-line tool-description fix dropped wrong grep patterns 26% -> 0.3%.
  Fit: short correct plans with reminders; mask old observations; fix tool descriptions from measured misuse.
- **Constrained output for plans.** Let Me Speak Freely (2408.02442): JSON-in-one-pass costs LLaMA-3-8B 25
  points on reasoning; two-step "reason in text, then convert" matches unconstrained. "Constrained Decoding:
  Harmful or Beneficial?" (2610.35328, 2026-10, 11 open models): most of the loss is prompt/eval mismatch, decoder
  masking itself is near-free; "Thinking Before Constraining" (2601.07525, 2026-01): reason freely, switch the
  grammar on at a trigger token. JSONSchemaBench/SOB: compliance near-perfect with llama.cpp/XGrammar; value
  accuracy is the limit. Fit (HR.C2 scope): never make the planner reason inside JSON; let it think, then
  constrain the final object with `json_schema` - and bound the thinking, which is where 48% of planning minutes go.
- **Memory and ownership.** Aider repo map: 1k tokens of ranked tree-sitter symbols, expanded only when no files
  are in chat. Cognition (2025-06-12, 2026-04-22): one writer, read-only helpers, clean-context reviewer; parallel
  writer swarms still "mostly a distraction". AgentRoom (2026-08): file-claim locks; STORM (2605.20563, 2026-05):
  validate each write against the writer's last-seen state. Fit: the harness's ownership table is the claim lock;
  linear dispatch is the proven mode; the 131k-char memory block is 100x Aider's default and the lead still reads.

## 5. New items

**HR2.P.1 - Readiness repairs before it refuses (bug/quality, always on).** Evidence: 125 of 140 resends since
11-01 are mechanical; the two largest causes (locked suite file on an order: 50; refused verification command: 30)
are repaired by `with_the_harness_s_files_left_out` and `with_refused_commands_noted`, which run after the check
(`workflow.py:10265, 10291`) - the plan is sent back for what the harness then fixes anyway. Change: run both
repairs (and a "files-less run-only order becomes a verification line / gets the planned test files" repair, and
"scope names a data file or the harness's start script" exclusions) **before** `readiness_problems`; readiness
then sees only what the harness cannot fix (carried decisions, no work orders). The harness's own plan never goes
to the lead for a problem the harness made (`planned_work.py:58-115` drops the locked suite's file and data files
itself). Test: a plan whose testing order names the locked suite file and a `cd`-prefixed command yields zero
readiness problems (fails on old code: two problems). KPI: readiness resends a run (1.1 -> ~0.1), lead minutes.
Size S. Risk: low - the repairs already exist. Expected: ~1.2 lead minutes a run plus the resend's re-read turn
and, on 2e7d285b-shaped runs, 30 min and 2 capped replies.

**HR2.P.2 - A thinking bound for answer-only planning calls, with "think, then answer" (quality; measured on
2 runs per family because it changes a model setting's effect, so a switch `PLANNING_THINK_BOUND`).** Evidence:
capped planning replies are 17% of replies and 48% of planning call-minutes today (82 of 170; 11-06 179 of 297);
each spends 80-105k characters reasoning before a plan the salvage then extracts. LF.413's cap and LF.683's tag
limit the damage; nothing lowers the cause. Change: for `PLAN_REVIEW_STAGES` whose turn is a structured answer
(the plan tool), send a soft budget line computed from the plan's size (criteria x files), and on a capped reply
answer the *next* turn with thinking off (the `SALVAGED_REPLIES_TURN_THINKING_OFF` rule exists for fix stages only:
`settled_answer._a_fix_stage_s_salvaged_replies_turn_thinking_off`) - extend it to planning stages. Where the
pinned server honours `reasoning_budget_tokens` (llama.cpp PR 25961; AR found the owner's earlier build ignored a
per-request budget - re-probe on today's build with `loop.sh ready`, never change the server), pass it. Test: a
salvaged planning reply turns thinking off for the stage's next call (fails on old code: only fix stages do).
KPI: planning call-minutes, capped planning replies; guard: hidden score, readiness problems per plan. Size M.
Risk: a plan written with less thinking may be worse - hence the arm.

**HR2.P.3 - The lead's and builders' reads of held files are answered without a model turn (quality, always on).**
Evidence: 453 of the lead's 602 reads since 11-01 were pointer answers (75%), ~3.7 full-context turns a run;
specialists 185, acceptance 427, fixers 318 pointer answers. Today's redundant-read rates: lead 0.36, builders
0.33. Change: (a) the pointer reply carries the file's first 80 numbered lines when the request names a line
(the `MOST_WINDOW_LINES` case) so the second read is not needed; (b) `read_file` of a held unchanged file is
masked from the tool list for planning stages (HR.C3's masking, applied here first - the planner has nothing to
read that it was not given) with the listing block saying so; (c) the pointer's "second read ends reading" rule
is enforced for the lead too. Test: a technical_lead request whose memory holds `main.py` offers no `read_file`
(fails on old code). KPI: `redundant_read_rate`, planning minutes (~3-4 min a run). Size S. Risk: a file the
memory truncated - keep the tool when `files_held_line` names left-out files.

**HR2.P.4 - Plan repair by delta (the model half of P1; quality, always on once P.1 lands).** Evidence: every
resend and every revision (331 all-time, 40 since 11-01) re-asks the whole plan (`readiness_feedback`: "return the
whole plan again"; `build_milestone_revision_request` sends the full JSON); after a resend the lead's first turn is
a read (44a25a80 06:13, 2e7d285b 11:57, 12:02, 12:14). Change: the resend asks for `work_orders_changed` keyed by
the order's label and `carried_forward_decisions` only; the harness merges into the held plan (Claude Code/Cursor
"approve with edits"; CodePlan's incremental extension). Test: a resend for one missing decision returns one line
and the merged plan keeps every other order byte-identical (fails on old code: no merge path). KPI: resend output
tokens (median 4k -> <1k), resend minutes. Size M. Risk: the model answers whole anyway - accept either shape.

**HR2.P.5 - Draft outcomes recorded (bug: a built mechanism nobody can measure; always on).** Evidence: 111 of
827 drafting calls since 11-01 were compiler repair passes; whether the repair held, how many files went to the
agent loop and why, and how many drafted files a later stage rewrote are log lines only (`drafting.py:401, 530`).
P6 cannot be judged without it. Change: a `draft` transcript record per file (path, pass: first/content-refusal/
repair-n, accepted, left-to-loop reason) and `loop.sh effects` lines "drafts repaired and kept", "left to the
loop", "rewritten whole later" (from git history of the workspace). Test: a draft refused for a parse error records
two `draft` records (fails on old code: none). KPI: enables P6's. Size S. Risk: none.

**HR2.P.6 - Data files and the harness's scripts are never "files nobody is given" (bug, always on).** Evidence:
~35 resends since 11-01 (start.sh 9, bookmarks.json 7, notes.json 6, args.json 3); `_data_the_product_writes`
needs a pack's `data_dir_env`, so a pack-less stack (Falcon: 6 today) is sent back for its data file. Change: a
scope-named file with a data suffix that the specification's file plan (`drafting.planned_files`) does not list is
not a file to build, on any stack; a file the harness keeps (`kept_by_the_harness`) likewise. Pack facts stay in
packs: the suffix table is general. Test: scope "writes notes.json under DATA_DIR" on a workspace with no pack
yields no problem (fails on old code). KPI: resends. Size S. Risk: a product that really needs a seed data file -
the specification lists it, so it is still flagged.

**HR2.P.7 - Setup-written files are named to the ownership table (quality, always on).** Evidence: LF.666 tells
builders to keep the setup's entry code, but whether they do is unmeasurable; the ownership table holds only work
orders' files. Change: `record_work_order_files` also records the proven setup's files as `stack_setup`'s with
"keep its start path" semantics - a whole-file rewrite of one is warned once with the proven lines named (the
existing `_a_fragment_sent_as_the_file` path), never refused; `loop.sh effects` counts "setup file rewritten
whole". Test: a builder's `write_artifact` of the setup's entry file returns the warning (fails on old code).
KPI: false acceptances of the falcon kind (0/9 on falcon 6), start breaks. Size S. Risk: low (warning only).

**HR2.P.8 - Audit lines for the planning cap and pointer reads (quality, host side).** Evidence: no audit line
shows capped-planning minutes (48% of planning time) or pointer turns; `effects` reports "replies lost to the
output cap: 0" on 2e7d285b, which hides 5 capped-and-salvaged replies costing 14 min. Change: `loop.sh scan`
prints per run: capped replies by stage with minutes, pointer-answered reads by stage, readiness resends by
reason, harness plans sent back. Test: a fixture transcript with one salvaged planning reply prints the minute
line. Size S.

**HR2.P.9 - Edit format by size for the builders (P3, reshaped; switch `EDIT_FORMAT_BY_SIZE`, group Building).**
Evidence: Diff-XYZ and Aider (section 4): whole-file for small files, lenient search/replace above; the harness
already refuses line edits. Change: the builder prompt (not a new rule - the existing tool guidance) says
whole-file under N lines, `edit_artifact` above, and `edit_artifact` matches with whitespace-lenient anchors
(`anchored_edits.py`); after one failed edit of a file the next edit of it is asked as whole-file. Test: an anchor
differing only in indentation applies (fails on old code if strict). KPI: edit failure rate, builder minutes.
Size M. Low priority until builders run in more than 38% of runs.

Not proposed: WB.5 plan batching (the cost is per thinking turn, not per unit of work); P6 candidates (wait for
HR2.P.5); any change to the parallel toggle (unused since 11-01, keep as is).

## 6. Priority order and expected effect

1. **HR2.P.1 + HR2.P.6** (S, bugs): ~125 of 140 resends gone; ~1.2 lead call-minutes a run plus the re-read turn,
   and no more harness-plan-vs-harness-check loops (4 today, one of them 30 min).
2. **HR2.P.3** (S): ~3.7 full-context turns a run on the lead, more on builders/fixers; 3-5 min a run.
3. **HR2.P.5 + HR2.P.8** (S, measurement): makes P6, LF.666 and the cap cost visible at every audit.
4. **HR2.P.2** (M, switch): the largest lever in this area - up to ~80 planning minutes across today's 14 runs
   (~6 min a run, 48% of planning call time) if the bound holds the plan's quality; measured two runs a family.
5. **HR2.P.4** (M): the residue of resends and all 40 revisions a week answered by deltas.
6. **HR2.P.7**, then **HR2.P.9** when builders run often enough to measure.
