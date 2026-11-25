# Deep review: what fills each stage's request (every stage except the defect fixers)

Date: 2026-11-25. Reviewer: read-only. Times are JST. Nothing in `src/`, `tests/`, config or docs was changed.

## How this was measured

Every `model_request` record of 12 runs was rebuilt into the full conversation the model received
(`carried` + `messages`), then read as text, not counted:

| Group | Runs |
|---|---|
| Medium brief, thorough, about 92K-token slot | run-32362f3b (Medium 4, live), run-bc3cbd00 (Medium 3), run-c53e7bd2 (Medium 2) |
| Small, fast, 93K slot (olla, the endpoint every run now uses) | run-2f653f55 (fullstack-bookmarks, live) |
| Small, fast, 182K slot (the retired :8888) | run-1d79334d, run-2c83118a, run-b6c5c636, run-ec516cd8, run-cc265cee, run-c4fd577a, run-f4bab632, run-c46d5d9a |

The two live runs ended after the first pass (run-32362f3b failed, run-2f653f55 completed). The fold and waste
counts were run again on the complete transcripts on 11-26: unchanged for every stage outside the fixers (the
unit-test builder gained 12 calls with no new waste).

Two things to know before the findings:

- **The slot size decides everything below.** On the 182K slot no stage of any of the 8 small runs was summarised
  (2 summaries in total, both fixers). On the 92-93K slot every working stage is summarised every 3 to 16 calls.
  Since 17:45 JST on 11-25 every run uses the 93K slot, so the small families now behave like the medium ones
  (run-2f653f55: suite author 16 summaries in 168 calls, 130 of 155 reads were repeats).
- **Reported input tokens are doubled on salvaged replies** (a reply cut at the cap is continued with a second
  call, and the usage of both is summed). Sizes below are characters of the request as sent; real tokens are about
  characters / 3.8.

Scripts (read-only, run inside the worker) are in the session scratchpad: `ctx_agg.py` (blocks by stage),
`ctx_thrash.py` (summaries, reads), `ctx_fold3.py` (finding 1), `ctx_notes.py` (work notes as written),
`ctx_held.py` (held files against reads), `ctx_dup.py` (repeated lines), `ctx_waste.py` (ranking).

## Ranking

### By wasted input (4 runs on the 92-93K slot)

"Waste" = summariser calls + calls that did nothing but read whole files the stage had already read whole.
Salvaged replies are halved. It is a floor: a call that re-reads and also does one new thing is not counted.

| Stage | Input | Waste | Share | Calls | Re-read-only calls | Summaries |
|---|---|---|---|---|---|---|
| Suite author | 40.9M | 20.0M | 48% | 906 | 368 | 112 |
| (Defect fixers - FX builds, shown for scale) | 21.9M | 7.1M | 32% | 587 | 173 | 43 |
| Test round | 16.7M | 5.9M | 35% | 367 | 113 | 39 |
| Technical lead | 11.1M | 5.8M | 52% | 237 | 92 | 47 |
| Builder: unit tests | 10.3M | 3.4M | 32% | 215 | 63 | 26 |
| Builder: backend | 9.5M | 3.0M | 31% | 215 | 55 | 30 |
| QA lead (suite review) | 5.1M | 2.4M | 46% | 116 | 46 | 11 |
| Builder: UI | 7.0M | 1.9M | 26% | 146 | 34 | 23 |
| Security review | 2.1M | 1.5M | 71% | 60 | 30 | 14 |
| Builder: database | 5.0M | 1.4M | 28% | 118 | 26 | 20 |
| Code review | 3.0M | 1.4M | 46% | 60 | 24 | 7 |
| Custom setup | 7.0M | 1.2M | 17% | 193 | 22 | 31 |
| Milestone / advice reviews | 2.2M | 1.2M | 54-60% | 57 | 26 | 12 |
| Architecture review | 2.2M | 0.3M | 12% | 55 | 9 | 4 |
| Architect, scrum master, intake, tools, stack, consultations, escalation | 1.4M | 0.2M | - | - | - | 0 |

### By harm (a stage that loses its own conclusion)

1. **Builders (all four roles).** Summarised every 4 to 7 calls, each note made from one or two calls; the notes
   invent work that is left and drop what was learnt (finding 2). The files the stage needs are not the ones held
   (finding 3). Run-32362f3b's backend builder ended on the call cap with its tests never run.
2. **Test round.** 21 summaries in 160 calls; one file read 36 times; reads folded before they were seen
   (finding 1); a new attempt was handed a stale note as fact (finding 5).
3. **Technical lead.** Its "contracts your work orders copy from" section is cut blind in the middle (finding 4).
4. **Suite author, QA lead, reviews.** Mostly waste rather than wrong conclusions; the fold bug hits them too.
5. **Architecture review.** Reads, 46 times, a document its request already holds whole (finding 6).
6. Early stages (intake to scrum master, escalation): no conclusion lost. One relevance finding (7).

## Findings

### 1. A file read is folded to 300 characters before the model has seen it (bug, always on the 93K slot)

**Evidence.** run-32362f3b, `test_round_0`:

- 19:29:45.753 JST: `read_file` of `routes/auth.py` returns 10,466 characters. 19:29:45.912: the next request
  carries it as 300 characters and "[Folded by the harness ... the rest was left out because it is older than the
  latest steps. Run the same call again if you need what it said.]". It was the latest step.
- The same file again at 19:35:36, 20:03:51 and 21:06:32, folded each time. The stage read it 36 times.
- 21:06:28: three reads (`routes/auth.py`, `schemas.py`, `main.py`) arrive as 536, 531 and 535 characters. The
  model answers "Let me read the full contents of the key files", reads them again, the conversation passes 15
  messages, they arrive whole, the trigger is crossed, and summary 12 is made at 21:06:40. Then it starts over.

Counted with `ctx_fold3.py` (a long read whose every copy in the next request is folded):

| Run | Reads folded unseen | Stages hit | Conversation length when it happened |
|---|---|---|---|
| run-32362f3b | 53 (46 outside fixers) | 13 | 10-15 messages, all 53 |
| run-2f653f55 (small) | 17 (15) | 6 | 10-12, all 17 |
| run-bc3cbd00 | 33 (27) | 8 | 10-15, all 33 |
| run-c53e7bd2 | 191 (174) | 22 | 10-15 for 184; 7 at 30 |
| 8 small runs on the 182K slot | 0 | 0 | - |

**What the model had vs needed.** It asked for a file and received its first six lines and an instruction to ask
again. Every such call is a full request (40-55K tokens) spent on nothing, and it pushes the stage to its next
summary.

**Root cause.** `src/app/agents/compaction.py:436`:
`cutoff = observation_folding.boundary(min(self._determine_truncate_cutoff_index(messages), len(messages)))`.
deepagents 0.7.13 returns `len(messages)` from `_determine_truncate_cutoff_index` when the conversation has at
most `keep` (15) messages, meaning "all are recent, shorten nothing", and its own `_truncate_args` returns early on
`cutoff_index >= len(messages)`. The override has no such return: for 10 to 15 messages
`boundary(len)` is 10, so the first ten messages are folded and their write arguments shortened. Below 10 the
boundary is 0; from 16 the cutoff is `len - 15`. A conversation is 10 to 15 messages long exactly after a summary
(summary message, kept tail, one reply with its reads), which is where the 93K slot keeps every stage.
On the 182K slot the argument trigger is rarely reached, which is why the 8 small runs show none and why
`docs/measuring.md` lists `OBSERVATION_FOLDING` as "no signal".

**General.** Every stage with tools, every stack. 294 reads in 4 runs.

**Fix (always on, it is a bug).** In `_truncate_args`, take the cutoff first and return unchanged when it is
`>= len(messages)`. Independently, never fold a tool result that no model reply follows: `fold` should stop at the
last AI message. The folded line's wording ("older than the latest steps") is then true.

**Test from real output.** Capture the 12 messages of `test_round_0` at 19:29:45 JST (summary message, kept
tail, the reply with five reads, five results). Assert `_truncate_args` returns the five results whole. It fails on
today's code. A second case with 16 messages must fold as today.

### 2. The work note (PA.2) is written without the stage's aim, from one or two calls, and carries invented work forward

PA.2 / LF.1360 is deployed and its four sections appear in every note. The content was read for 60 notes of the
two live runs. Three separate faults.

**2a. The summariser is not told the aim for 6 of 9 stage families.** `aim_of` (`compaction.py:145-150`) takes the
first 1,500 characters of the request. What that was, from the real summariser inputs:

| Stage | "What the stage was asked to do" as shown |
|---|---|
| Suite author, fixers | The real ask (good) |
| Builders (database, backend, UI, unit tests) | "Where things stand ... Finished this sprint: specialist_database_0 ..." then the technology stack. `--- Delegated task ---` starts about 6,000 characters in and is never shown |
| Test round | "The technology stack for this project (already decided)" |
| Architecture review | "Technical constraints, quoted from the brief" |
| QA lead | "The brief, as the customer wrote it" |
| Code review | "Work orders in this batch" (partly right) |
| Technical lead | Empty: 0 characters (run-32362f3b, 20:19 JST) |

**2b. The note invents and keeps work that is done, and drops what was learnt.** run-32362f3b,
`specialist_backend_1`, 14:18-15:01 JST, 8 summaries in 40 working calls:

- 14:41:54: a write of `auth.py` is answered with a type notice (`Cannot access attribute "update"`, line 301);
  the next reply corrects it and writes the file again. Note 2 (14:42:59) records "write attempt failed" and, under
  Left, "Create `routers/auth.py`" - the stage was writing `routes/auth.py`.
- Notes 3 to 8 carry "Resolve the SQLAlchemy `FromClause` `update` error" forward. From note 4 it has moved to
  `routes/auth.py` **line 301**, while the same note says that file is lines 1-276. By note 6 it is "blocking test
  collection"; by note 7 the Decided section plans a rewrite of code that had no such error.
- Notes 5 to 8 say "Changed: None" while the harness's own line under each note lists five files written.
- Note 4 records what the stage learnt the hard way: the command tool takes no `cd`, `&&` or `||`. Note 6 drops
  it. 14:58:59, 14:59:33, 14:59:55: the stage sends `cd task-management-dashboard && ...` three more times.
- From note 6 on, Found is a list of file descriptions ("`schemas.py:1`: Pydantic request/response models"),
  which the prompt forbids. The cause is visible in the input: summary 6 was made from one reply with eight reads,
  four answered "is in the project memory" and four folded to six lines (finding 1). There was nothing else to
  summarise.

The stage ended at 15:01 on its call cap with the test suite never run. Between note 4 and note 8, 14 calls
(about 750K input tokens) changed nothing.

**2c. The earlier note is copied, not checked.** Each summary is given the previous note plus about 9,000
characters of new conversation (`CTX_SUMMARY_BUDGET` 4,000 tokens, `context_policy.py:110`, less role, aim and the
earlier note). Nothing tells the summariser which Left items a later write settled, so a Left item lives until the
stage ends.

**Root causes.** `compaction.py:145` (aim), `compaction.py:369-381` (earlier note handed over as text),
and the summary rate itself (findings 1 and 3): a note per two calls cannot hold a conclusion. The model's
reasoning, where its conclusions are, is not in the conversation at all; its visible text is one line a reply.

**General.** Builders: 10/9/10/8 summaries in run-32362f3b, 19/11/13/18 in run-c53e7bd2. Test round 21. The same
drift (a Left item repeated after the file was written) was seen in `test_round_0` notes 4 to 8.

**Fix (always on).**
- The aim: each request builder marks its ask (the request-budget `Part` kinds already tag `INSTRUCTION` and
  `EVIDENCE`, `request_budget.py:96`); `aim_of` takes those parts, and falls back to the opening only when none is
  marked. No per-stage text in `compaction.py`.
- A harness-written ledger in every note, not asked of the model: files written (already kept as
  `FILES_WRITTEN`), each command run with its exit code, each refusal the tools gave (once). The model writes
  Found, Decided, Left only.
- A check of the note against the workspace before it is kept: a path that does not exist, or a line past a
  file's end, is struck with a line saying so; a Left item naming a file written since the earlier note is marked
  "written since - verify".
- No summary of fewer than 4 model replies: stub the old read results instead (the FX "stub old reads" idea,
  for every stage).

**Tests from real output.** (1) The real opening of `specialist_backend_1` (14:18:10 JST): assert the aim
contains the delegated task's first line. (2) The real note 4 text and the real file list: assert
`routes/auth.py:301` is struck (file has 276 lines) and `routers/auth.py` is struck. (3) The real messages of
summary 6: assert no summariser call is made.

### 3. The files a builder holds are chosen alphabetically; the largest is a harness file it cannot change

**Evidence.** run-32362f3b, `specialist_backend_1`, opening request 14:18:10 JST, 179,801 characters:

| Held whole in the memory | Characters | Used by this stage |
|---|---|---|
| `playwright.setup.mjs` (harness-kept) | 24,905 | never read, cannot be changed |
| `models.py` | 10,824 | yes |
| `database.py` | 3,732 | yes |
| `scripts/unit-tests.mjs` (harness-kept) | 3,392 | no |
| `playwright.config.js` (harness-kept) | 2,101 | no |
| `src/styles.css`, `index.html`, `src/App.tsx`, `src/main.tsx`, `tsconfig.json`, `vite.config.ts` | 3,400 | no (frontend) |
| `main.py`, `alembic.ini`, requirements, others | 4,500 | yes |

Not held, and read from the first call: `schemas.py` (10,857 characters, read 9 times - the previous builder's
file this one builds against), `acceptance/auth.spec.js` (7,592, 4 times), `error-handling.spec.js` (3 times).
About 34,000 of the 61,000 characters of held files (55%) were of no use to a backend builder, in each of 40
calls. The UI builder held the same 24,905-character file; so did the suite author at its last call.

After `REQUEST_BUDGET_FOR_EVERY_STAGE` went on (17:47 JST), `specialist_ui_ux_2`'s memory fell from 101K to 52K
and held **no product code at all** - two document digests, the outline and `package.json` - while the stage read
`styles.css` 15 times, `App.tsx` 13 times, `useAuth.tsx` 8 times.

`test_round_0` opened holding `alembic/env.py` and `001_initial.py` (13,600 characters) and not `routes/auth.py`
(read 36 times), `auth.spec.js` (23), `schemas.py` (20), `error-handling.spec.js` (20), `tests/test_auth.py` (13).

**Root cause.** `src/app/agents/project_memory.py:177-200`, `_ranked`: with `CANONICAL_MEMORY` on,
`named = not canonical and ...` is always false, so the request's own file names no longer rank anything and the
order is documents, then application and config files **by path**. `playwright.*` sorts before
`task_management_dashboard/*`, and within that folder `schemas.py` sorts last. The harness-kept files
(`kept_by_the_harness`, `:502`) are not demoted for a stage that cannot write them. The choice "again at each
summary" (`:1244`) ranks by reads, but reads answered from the memory or folded are the ones counted, so it swings
between two sets (`test_round_0`: 90K, 66K, 79K, 57K of memory across the visit) and each swing drops files read
ten times.

**General.** Every builder and test round on a product past the memory's room; any stack (the order is by path).

**Fix (always on; the order stays fixed for a whole visit, so the cache is kept).** Rank once at the stage's
opening by what its request names: files the work order owns, files in "Interfaces to implement or call", their
neighbours from the code graph, the due tests. Then the rest by path. Harness-kept files go last for every stage
without the right to change them, and into the outline when room is short. At a summary, add files to the held
set by reads; do not drop one the stage read three times.

**Test from real output.** The real file list of run-32362f3b at 14:18 JST with the real backend work order and
the real budget (82,598): assert `schemas.py` and `acceptance/auth.spec.js` are held and `playwright.setup.mjs` is
not. Fails today.

### 4. The technical lead's contracts section is cut blind in the middle

**Evidence.** run-32362f3b, `technical_lead`, 13:50:42 JST. The section headed "From the approved technical
specification: the contracts your work orders copy from" reads:
`...auth.py - Authentication logic. Exports: hash_password, ... Implements JWT encode/decode usin` then
`--- TRUNCATED (23428 chars removed for context limits) ---` then `(401, "Not authenticated"). 2. Extract JWT
token...`. 23,428 characters of component boundaries and function contracts are gone, mid-word, with no line
range to read them from. The same request carries the sprint plan twice in two forms (digest 11,924 in the memory,
whole 16,707 in the request), the adopted advice (6,974), the intake (4,180) and `src/styles.css`.

**Count.** run-32362f3b 1 opening, run-bc3cbd00 22 requests carrying the marker (792K characters removed in
total), run-c53e7bd2 40 (840K). None in small runs.

**Root cause.** `src/app/agents/technical_lead.py:517` (the same head-and-tail cut is at `product_manager.py:264`,
`tools_models.py:360`, `stack_selector.py:54`; only the lead's fired in these runs).

**Risk.** Work orders written without the contracts of the files in the removed middle; builders then invent
signatures. Not proven to have cost a criterion in these runs.

**Fix (always on).** Replace the blind cut with the section-aware digest the memory already has
(`project_memory.digest_of`): whole sections for the files of this sprint, every other section as a heading with
its line range. Drop the second copy of the sprint plan first.

**Test from real output.** The real specification of run-32362f3b and the sprint-1 file list: assert the
request contains no "TRUNCATED", contains the contract line of every sprint-1 file, and names a line range for
each section left out.

### 5. A new attempt of the test round is told its last attempt "ended without a structured response" and is given a stale note as fact

**Evidence.** run-32362f3b, `test_round_0`. 20:13:32 JST: the stage finds the cause
(`UnsupportedCompilationError`, `ARRAY` on SQLite). 20:15:34: it answers (`SpecialistOutput`, with the cause
under `blockers`). No error, resume or restart follows; the sprint is re-planned and two builders change the code
(20:34). 21:06:16: the next test round opens with "[Carrying over from your previous attempt at this stage, which
ended without a structured response. The conversation is gone; these facts are not. Do not re-establish them.]
It ended because it produced no structured response: answer sooner this time", followed by a work note written
before the code changed, whose Found begins with two lines about `tests/test_auth.py:401` and `:406`.

The first statement is false, and the "facts" describe code that two stages had since rewritten. The model's
first reply: "I'll start by reading the key files" - it read everything again anyway.

**Root cause (not fully traced).** `workflow.py:2428` calls `carry_over_note`; `carry_over.py:44-56` reads the
last work note kept for the stage's thread. The note is kept at every summary (`compaction.py:181`) and nothing
seen clears it when the stage answers, so a later visit under the same stage name is treated as a restart.

**Fix (always on).** Clear the kept note and the restart reason when a stage returns its answer. A note carried
into a visit where product files changed since says so and lists them.

**Test.** Replay the real record sequence 20:15:34 answer, 21:06:15 opening: assert no carry-over text.

### 6. The architecture review reads, 46 times, the specification its request holds whole

**Evidence.** run-32362f3b, `architecture_review`, 11:52-12:56 JST, 51 calls, 2.2M input tokens, 4 summaries.
The request holds "Technical specification and ADRs under review" whole (41,437 characters). The memory beside it
holds the same document as "outline and the sections this request points at; **read others by line**". The
reviewer made 46 `read_file` calls of `/docs/technical_specification.md` (9 whole, 7 from line 400), and their
results were folded to 536 characters (finding 1). The same stage on the small runs is one call of 32K tokens.
The scrum master did the same twice in one message (digest 12,611 + whole 40,621).

**Root cause.** `project_memory.py:705`: the digest block is added whatever the request holds, and its header
invites reads. The copy in the request has no line numbers, so a reviewer citing a line has to read the file.

**Fix (always on).** When the request holds a document whole, the memory leaves it out and names it as held; a
read of it is answered with the pointer, as held files are. Number the in-request copy for stages whose findings
cite lines.

**Test from real output.** The real 11:52:40 request: assert `docs/technical_specification.md` appears once and
no "read others by line" for it.

### 7. The architect's "evidence for the chosen stack" is 19,354 characters of landing pages

**Evidence.** run-32362f3b, `principal_architect`, 11:30:59 JST, in all 17 calls. The section's headings include
"### Gold Sponsors" (a README's sponsor list), Playwright's badge line (`[![PyPI](https://badge.fury.io/...`,
"Join Discord"), React's API index (`startTransition`, `addTransitionType`, `act`) and Vite's "Rolldown Hooks".
The version table at its top is what the request asks the architect to cite. With the tools-and-models plan as raw
JSON (14,752) and the specialists' advice (14,642) the opening request is 65,436 characters; a revision adds the
previous specification (25,270) and the changes (11,421): 101,240. 4 of 16 architect replies ended at the output
cap.

**Root cause.** `src/app/stacks/stack_evidence.py:47` section built from fetched "getting started" pages with no
filter for navigation, badges or sponsor blocks.

**Fix.** Keep the table always. Under it, per library, only passages that match a term of the brief or of the
research brief's topics, with a cap per library; drop lines that are links only. On a revision, the table alone.
Behind a switch (doubtful: it changes what the architect knows), measured on specification review findings.

**Test from real output.** The captured section: assert no "Sponsors", no badge line, at most N characters a
library, the table intact.

### 8. Known items, judged against today's requests

- **Stages open near their summary trigger (PA.1, LF.1274/M17).** Right direction, not enough. After PA.1 cut
  them, openings in run-32362f3b were still 0.96-0.97 of the trigger before the cut and about 0.66-0.78 after
  (test round 21:06 JST: 152,834 characters against about 196,000). The budget (`request_budget.py:79`) counts the
  request and the memory; it does not count what is the same in every call: system prompt 19-28K, tool schemas
  23-25K for a builder, workspace listing 5-8K, about 52,000 characters, a quarter of the trigger. Technical lead
  (173K at opening), code review (158K) and the QA lead are sent uncut (`applied: true`, nothing cut, built
  130-140K). A builder has room for about four file reads before its first summary.
- **The summary trigger is counted in characters / 4** while the model tokenises this content at about 3.8
  (measured from unsalvaged replies), and the slot holds 61K input tokens: the trigger fires near 53K real tokens.
  There is little to gain by moving it.
- **Read-only roles carry writer guidance** (per-role audit 11-20, still open): the architecture reviewer's
  system prompt is 25,386 characters with PYTHON:SETUP, REACT:SETUP, POSTGRESQL, PYTEST and VITEST modules; a
  backend builder carries the REACT module (2,382). Small beside the above.

## Checked and fine

- **Repeated text inside one request.** Line-level repeats (numbered gutters stripped, lines of 50+ characters)
  are 2-8% of a request for every stage on every run; the exceptions are the QA lead (10-13%, the suite in its
  request and read again) and findings 4 and 6. The same file in the memory and in a read is rare because a read
  of a held file is answered with a pointer (34 of 73 reads for the backend builder).
- **Intake** (2.7K tokens, one call), **tools and models** (9K, 59% is its answer schema, 1-2 calls), **stack
  selector** (12K), **the five consultations** (10K each, one call), **scrum master** (3 calls), **escalation**
  (one call, 80-90% specification): nothing irrelevant of size, nothing lost. No release stage makes a model call.
- **Drafting** (fast runs): 8-12K tokens a file, specification sections plus the request. Fine.
- **The 182K slot**: no summaries, no folding, 0 reads folded unseen in 8 runs.
- **Pointer answers** for held files work as written; the model twice read them as "reads are now blocked" and
  went on from the memory, which is the intended result.
- **The test round's cause is carried to its next visit** (finding 5's note does contain the `ARRAY` line); the
  fault there is the false framing and the stale facts, not a lost conclusion.
- **LF.1399** (reads counted in the two-space gutter): the read counts in the summary messages are non-zero in
  both live runs.

## Not verified

- Whether any finding cost a hidden test: no run here is scored after the PA.2 deploy.
- Finding 2b's "main.py lacks /api/health" lines were not checked against the workspace; only the claims that the
  transcript itself contradicts are reported.
- Finding 5's root cause is read from the code path, not reproduced.
- Finding 3's waste share is from what the stage read and wrote; a held file used silently from the memory would
  count as unused. The harness-kept files cannot be such a case for a builder.
