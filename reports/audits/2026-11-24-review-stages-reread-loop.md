# Why review stages re-read the same files on a medium product, and what to build

2026-11-24. Read-only design review: no code changed, nothing committed, no run or container touched.
Basis: the code as of `f6cbdb54`, the measurements in the brief (one medium FastAPI + React run), and one local
experiment with the real agent stack and a stub model (no model server, no run). The run's transcript was not
available, so every per-file size below is an estimate and is marked as one.

## Short answer

A review needs about 20 files in view at once. The harness puts them in the one place it later deletes: the
conversation, as `read_file` results. The room the conversation has is smaller than the files, so each summary throws
away two or three batches of reads, keeps nothing a reviewer can judge from, resets the read guard, and the reviewer
reads them again. Nothing but the 40-call cap ends it.

The two switches tried on the run could not have helped, for reasons that are in the code:

- `REQUEST_BUDGET_FOR_EVERY_STAGE` shrinks the project memory, but **the summary trigger never counts the project
  memory** (verified, below).
- `REPLY_ROOM_SIZED_PER_ROLE` **changes nothing for any review role**: twice their 17,000 row is 34,000, capped at the
  32,000 already held (`src/app/agents/reply_room.py:36-41`, `:69-70`).

The fix is to stop using the conversation as the store: the files under review are handed over by the harness, held
outside the conversation, and a set too large for one request is reviewed in measured parts whose findings the
harness joins. A set that fits today is sent exactly as today.

## 1. The mechanism, step by step

### 1.1 The numbers a review stage runs under

Derived in `src/app/agents/context_budget.py` and confirmed by building the real advice-review agent locally
(window 91,776, reply 32,000): the summariser was built with `trigger=('tokens', 43020)`, `keep=('messages', 15)`,
kept tail at most 6,453 tokens.

| Quantity | Value | Where |
|---|---|---|
| Slot | 91,776 tokens | server profile, `context_budget.py:233-262` |
| Reply held back | 32,000 | `context_budget.py:106`, `:340-350` |
| Framing held back | 6,000 | `context_budget.py:97` |
| Input ceiling | 53,776 | `context_budget.py:354` |
| Summary trigger (0.8) | 43,020 | `context_budget.py:138`, `:303-305`; `role_agent.py:431-437` |
| Tail kept by count | 15 messages | `context_budget.py:137`; `role_agent.py:441` |
| Tail kept by size | 6,453 tokens (0.15 of the trigger) | `compaction.py:71`; `role_agent.py:442` |
| What the summariser is shown | the last 4,000 tokens of what it replaces | `context_policy.py:49-50`; `compaction.py:177-186` |
| Before a second summary | 15 + 8 = 23 messages after the summary message | `compaction.py:68`, `:262-267` |
| Project memory | 0.3 of the window = 82,598 characters (about 27,500 tokens) | `project_memory.py:57`, `:800-809` |
| Opening target with the budget switch | 43,020 x 3 - 10 x 5,376 = 75,300 characters | `request_budget.py:39`, `:89` |
| Call cap | 40 | `settled_answer.py:780` |

### 1.2 What a reviewer is told to review

Each review is pointed at the whole sprint, and in a first sprint that is the whole product.

- **Code review.** The diff since the last accepted commit, cut at 30,000 characters with "read the files for the
  rest" (`src/app/ci.py:633-642`; `src/app/graph/engineering.py:592`, `:613`). In a first sprint every file is new, so
  the diff is every file with a `+` on each line, and 30,000 characters is four or five of twenty files. Its prompt
  says "Read files with your tools when the diff is not enough" (`code_reviewer.py:73`).
- **Security review.** The list of changed files (`workflow.py:9005-9045`) and their source up to 24,000 characters;
  every other file is named as "not shown" and the request ends "Open each of them with your read tools before
  deciding" (`security_reviewer.py:80`, `:115`, `:122-127`). On 21 files that is an instruction to make about 17 reads.
- **Advice reviews.** Only the list of changed files; the prompt says "Read the code that was built - the changed
  files first - before deciding" (`advice_review.py:67`, `:101`). No source at all.

So the exploring is instructed, not a model fault. The security-and-reliability advice review covers the whole
product, which is why it looped (112 reads, 6 summaries) while the other advice reviews, whose items touch a few
files, finished in 3-4 calls with none.

### 1.3 Where the files could have been held, and why they were not

The project memory is the store that survives a summary: it is rendered once per visit and put in front of every
call (`project_memory.py:1020-1061`), and a read of a file it holds is answered with a one-line pointer, not the file
(`project_memory.py:1071-1112`).

- For `security_review`, `advice_review_*` and `milestone_review` the memory is filled **documents first**
  (`_ranked`, `project_memory.py:155-178`): the specification, sprint plan, criteria, tests, milestone plan, intake
  and stack take the 82,598 characters and the code is "Not included here (read when needed)". Only `specialist_` and
  `code_review_` stages get the code ahead of the plans (`_ON_CODE_STAGES`, `project_memory.py:370`), and that list
  was extended to the code review for this same symptom ("read the four files under review seven times each over
  four summaries", `project_memory.py:367-369`).
- For the code review the memory does hold code, but 82,598 characters is roughly half of a 20-file product (estimate:
  6,000-8,000 characters a file), and the request repeats up to 30,000 of the same characters as a diff.
- The memory holds text without line numbers. A reviewer cites lines, so it reads held files too. With
  `FIRST_REREAD_ANSWERED` on, the first such read returns the whole file numbered into the conversation
  (`project_memory.py:1096-1103`): a second copy of what the memory already holds, in the part that gets summarised.

### 1.4 One batch of reads against the room

Estimate per file: `read_file` returns numbered lines; a 150-250-line source file is 6,000-9,000 characters, about
2,000-3,000 real tokens (3 characters a token, `context_budget.py:55`). Six parallel reads are 12,000-18,000 tokens.
The whole set of 19-21 files is 40,000-60,000 tokens: **more than the entire trigger of 43,020**, before the request
and the system prompt. No setting of the trigger below the window makes the set fit in the conversation.

What the trigger counts (system prompt, tool schemas, the opening request, the conversation):

- security review: about 30,000 characters of opening request (24,000 of source, the list, the facts), the prompt
  and the tool schemas: roughly 10,000-12,000 counted tokens before the first read;
- two to three batches of reads add 30,000-45,000: the trigger is crossed on the third or fourth call.

### 1.5 What a summary keeps and drops

`RequestKeepingSummarization` (`src/app/agents/compaction.py`):

1. **Cut.** The tail starts at 15 messages (two batches of six reads), then is cut to 6,453 tokens, only before a
   model message (`compaction.py:188-212`). One batch of six reads is already 12,000-18,000 tokens, so the loop stops
   at the last batch and keeps it whole: about six files stay, everything earlier goes.
2. **Summarise.** The summariser is handed only the last 4,000 tokens of what is being replaced
   (`compaction.py:177-186`) - one or two of the 12-18 file reads being dropped - with langchain's general
   "Context Extraction Assistant" prompt (session intent, summary, artifacts, next steps). It is not asked for
   findings, and the reviewer has written none: a reply that makes six reads has no text of its own.
3. **Rebuild.** The new first message is the opening request whole (up to 48,000 characters,
   `compaction.py:62`, `:155-164`), the summary, and "Files this stage has written" - empty for a reviewer
   (`compaction.py:276-310`). Nothing records which files were read or what was seen in them.
4. **Forget.** The read guard's record is cleared (`compaction.py:281-287`), and separately a read whose earlier text
   is no longer in the request is treated as new (`workspace_backend.py:1332-1335`). Both are right - the text really
   is gone - and both mean the next read of the same file returns every byte again.
5. **Hold off.** A second summary waits for 23 messages after the summary message (`compaction.py:262-267`). The rule
   counts messages, not calls: a batch of six reads is seven messages, so the kept batch plus two or three more
   reaches it. That is one summary every 2.3-3 model calls - the measured 11 in 31, 6 in 19 and 3 in 7.

### 1.6 Why the next call reads again

After a summary the reviewer holds: the request, a paragraph about one or two files, and the last six files. It was
told to judge 20. It cannot answer from six, so it reads the others; when those arrive the first six are next to go.
A reviewer can therefore never hold more than one to three batches (6-18 files) and never all of them, and it has no
way to bank a finding. Each cycle reads 12-18 files and loses 12-18. Nineteen files at 6-8 reads each over 25 calls
is that cycle run about eight times; 63% of calls only reading (deep review D.14) is the same thing.

### 1.7 Why the two switches did nothing here (verified)

**The trigger does not count the project memory.** `create_deep_agent` replaces its own summariser in place in the
core stack and puts every other middleware after it (`deepagents/graph.py:204-238`); the first middleware is the
outermost, so the summariser counts the request before `ProjectMemoryMiddleware` (`role_agent.py:801`, `:846`) adds
the memory. Checked with the real advice-review agent and a stub model:

| Call | Characters sent to the model | Tokens the summariser counted |
|---|---|---|
| 1 | 49,638 (44,479 of them memory) | 2,746 |
| 2 (after four reads) | 69,089 | 9,502 |
| 3 | 71,242 | 10,210 |

langchain's counter is 4 characters a token, scaled by the last reply's reported usage by at most 1.25
(`langchain_core/messages/utils.py:2405-2415`), so the scaling cannot cover it. Consequences:

- Cutting the memory from 126K to 84K characters moves the trigger by nothing. The measured "still summarised 3 times
  in 7 calls" is exactly what the code predicts.
- `request_budget.opening_target` and the comments in `compaction.py:194-199` reason as if the memory counted. It
  does not: the room for reads was never the memory's to give.
- The same fact means the real request is the counted tokens plus the memory (about 27,500) plus the other injected
  parts (environment contract, digest, plugin instructions). At a counted 43,020 the real request is past 70,000
  tokens on a 91,776 slot, so the 32,000 "held back for the reply" is not held back. I could not check the run's
  largest requests; this needs one reading of the transcript (the largest `input_tokens` of the review stages against
  59,776) before anything is changed. It is a separate matter from the loop and is filed in section 3.4.

**The reply room is unchanged for reviews.** `reservation` is the larger of 8,000 and twice the row, never above the
current 32,000; every review row is 17,000 (`reply_room.py:36-41`), so it returns 32,000 and the trigger stays 43,020.

### 1.8 A stack fault found on the way

`_WORTH_REVIEWING` is a fixed list of JavaScript, Python, HTML and JSON suffixes (`security_reviewer.py:84`). For a
Go, Rust, Java, C#, Ruby or PHP product `_select` skips every file (`:142-143`), so the request shows no source and
says "None of the changed files could be read for this request" (`:109-113`) - the reviewer then reads everything by
tool, on every size of product. It breaks the rule that stack knowledge lives in the language tables.

## 2. Options, ranked

| # | Option | Stops the loop? | Cost | Risk to quality | Small runs | Verdict |
|---|---|---|---|---|---|---|
| 1 | **The harness hands over the files under review, held outside the conversation; a set too large is reviewed in measured parts and the findings joined** | Yes: nothing has to be read into the conversation, and no part is larger than its room | Medium: one new module, three review nodes, the memory's order | Cross-file faults (a route nothing calls) are seen less in one part; answered by giving each part the other files' definitions (`map_of`) and the read tools | Unchanged by construction: a set that fits is sent as today | **Build** |
| 2 | Review stages' memory holds the code under review ahead of the plans (extend `_ON_CODE_STAGES`), numbered; the request stops repeating it and stops ordering a read of every file | Partly: reads of held files cost a line each and survive summaries; about half of a 20-file product still does not fit | Small | Plans shown as digests to a reviewer | Changed unless gated by size | **Build first, as step 1 of option 1** |
| 3 | Later sprints: changed hunks with context, not whole files; new files whole | Shrinks the set from sprint 2 on; a first sprint is all new | Small | Low | Unchanged in sprint 1 | Build with 1 |
| 4 | A summary for a stage that writes nothing keeps a harness-made ledger (files read, lines, sizes) and the reviewer's notes | No: the ledger says what was read, not what it said; the reviewer still needs the text. Notes need a new tool, and a weak model does not use one reliably | Small to medium | A reviewer trusting a ledger line passes code it no longer sees | None | Not alone; the ledger line is worth adding after 1 |
| 5 | Reads capped per reply to the room left | No: the set is still larger than the room; it only makes each loss smaller | Small | Low | Rarely fires | Skip |
| 6 | A larger trigger for read-heavy stages (`SUMMARISE_LATER_WITH_HEADROOM`, smaller review reply rows) | No: gains 8,000-15,000 tokens against a need of 40,000-60,000, and section 1.7 says the real request is already near the slot | Trivial | Truncated replies if the real request passes the slot | None | Skip until 3.4 is measured |
| 7 | Summaries keep more of the latest results verbatim | No: the tail is already the last batch; a larger tail leaves the conversation at the trigger and it summarises on every call (the measured reason for `KEPT_TAIL_SHARE`, `compaction.py:194-199`) | Trivial | - | - | Reject |
| 8 | `OBSERVATION_FOLDING` on for reviews | No: folds a read to 300 characters, the same loss without the summariser call. Saves the summary calls only | None (built) | Same re-reads | None | Not a fix |
| 9 | One call over everything (the slot can physically hold 20 files, the digests and a 20,000-token reply) | Yes | Small | High on a 35B local model: 50,000 tokens of code judged in one pass | Unchanged | The single-part case of option 1 is this, bounded by measurement; do not raise the bound without a run |

How to measure any of them, per review stage, from the transcript (`loop.sh effects`): model requests, `read_file`
calls, distinct files, reads per file, summaries ("Context Extraction Assistant" requests), minutes; findings per
review and how many name a file from each part; hidden score and false findings unchanged. Target on the medium
brief: reads per file at most 1.2, no summary in a review, under 10 requests a review; small families byte-identical
requests (a test, not a run).

## 3. Recommendation and build plan

Build option 1 in three steps, each shippable alone. Steps 1 and 2 are quality fixes (a review that passes code it
could not keep in view is a wrong review), so always on with a size gate, per the owner's switch policy; nothing here
needs a new switch. No new prompt rule is added; where request wording changes, the banned-words test applies.

### 3.1 Step 1 - the files under review are held, not explored (small)

New module `src/app/agents/review_files.py`:

- `under_review(repo_root, changed_files) -> list[tuple[str, str]]`: the changed files that are the product's code or
  configuration, by `app.analysis.file_kinds.classify_file` and `app.stacks.languages` (generated folders, lock files
  and the harness's kept files out), application before tests, each with its text. Replaces `_WORTH_REVIEWING`.
- `fits_as_today(files, repo_root, model, stage, opening) -> bool`: true when today's request and memory already
  show every file (the size gate). True means no other function of this module is used.
- `numbered(text) -> str`: as `project_memory._numbered` (`project_memory.py:988-990`), so a reviewer cites lines
  without a read.

Changes:

- `project_memory.render` / `render_for_a_stage` (`project_memory.py:467`, `:720-754`): a `review_files` argument.
  When given, those files are ranked first and held numbered, the plans follow as digests (`documents_at_most`, as a
  request past its budget already gets), the rest are named with their definitions as now. Given only when
  `fits_as_today` is false, for `security_review`, `advice_review_*`, `code_review_*`, `milestone_review`.
- `security_reviewer._the_source_under_review` (`security_reviewer.py:89-128`): when the memory holds the files, the
  request names them and says where they are; it no longer repeats 24,000 characters of them and no longer says
  "Open each of them" for files the memory holds. `source_coverage` reports held files as shown.
- `ci.diff_since` (`ci.py:633-642`) gains the list of files new since the commit; `build_code_review_request`
  (`code_reviewer.py:79-103`) shows hunks for changed files and names new files as held whole (a diff of a new file is
  the file with a `+` on each line).
- `advice_review.build_advice_review_request` (`advice_review.py:84-105`): same naming of where the files are.

Tests that fail on the old code:

1. `test_a_review_s_memory_holds_the_code_under_review_before_the_plans`: a workspace whose plans alone fill the
   budget; `render_for_a_stage(..., stage="security_review")` holds the changed source files. Old: all are in "Not
   included here".
2. `test_a_security_review_shows_a_product_in_any_language`: a `.go`, a `.rs` and a `.java` file; they are selected.
   Old: "None of the changed files could be read".
3. `test_a_review_is_not_told_to_open_files_it_already_holds`: 30 files of 3,000 characters; the request has no "Open
   each of them" for a held file. Old: 22 named as not shown with that instruction.
4. `test_a_new_file_is_not_sent_as_a_diff_and_as_itself`: a first-sprint code review request holds each new file's
   text once across request and memory. Old: twice for the first 30,000 characters.
5. Guard (passes on old and new): for a product whose files fit, the three requests and the memory are byte-identical
   to today's.

### 3.2 Step 2 - a set too large is reviewed in parts (medium)

- `review_files.parts(files, room_characters) -> list[list[str]]`: groups by measured size, files of one folder kept
  together, one group when all fit. `room_characters` is what the memory can hold after the plans' digests
  (`budget_for` less the digests), so the part size follows the model's window.
- `review_files.joined(answers)`: findings of all parts in one answer of the review's own schema, repeats of the same
  file and problem dropped (`app.agents.finding_category` already groups findings).
- `src/app/graph/nodes/reviews.py` `_the_security_review` (`:27-76`) and `_one_advice_review` (`:116-172`), and
  `engineering.code_review` (`engineering.py:573-625`): when there is more than one part, one `_run_gated_agent` visit
  a part, stage name `<stage>_part_<n>`, the part's files held in its memory, the other parts' files named with their
  definitions, and the findings of earlier parts in the request ("already found; do not repeat"). The part reached is
  kept in state beside the existing review cycle keys (`advice_review_cycle`, `reviews.py:106-113`) so a pause or a
  deploy resumes at the part in flight. The document is rendered once, from the joined answer.
- Parallel mode: parts of one review are independent and can use the existing review fan-out
  (`review_worker_node`, `reviews.py:204-228`).

Tests that fail on the old code:

6. `test_a_review_of_more_than_its_room_is_made_in_parts`: a stub agent, 20 files of 8,000 characters; the node makes
   as many visits as `parts` returns, each visit's memory holds exactly its part, and no visit's request plus memory
   passes the room. Old: one visit, most files left out.
7. `test_parts_findings_are_joined_once`: two parts raising the same finding; the rendered review has it once and
   names every part's files as covered. Old: no such function.
8. `test_a_review_in_parts_resumes_at_the_part_in_flight`: a pause in part 2 does not run part 1 again.
9. Guard: one part means one visit under the old stage name.

### 3.3 Step 3 - what a summary of a reading stage says (small, after 1 and 2)

`compaction._build_new_messages_with_path` (`compaction.py:276-310`): beside "Files this stage has written", a line
"Files this stage has read: path (lines), ..." built from the `read_file` calls being replaced, and a count of
summaries so far kept in the message's `additional_kwargs` like `CALLS_BEFORE`. It does not stop a loop by itself
(option 4), but a stage that still reads past its room is told what it covered, and `effects.py` can report summaries
per stage without parsing requests. Test: `test_a_summary_names_the_files_the_stage_had_read` (old: no such line).

### 3.4 Filed, not part of this build

- **The summary trigger does not count what the middleware after it adds** (project memory, environment contract,
  digest, plugin instructions): `role_agent.py:801`, `:846`; reproduction in the scratch script named below. Counting
  it as-is would make every stage summarise about 27,000 tokens sooner, small runs included, so it must not be
  "fixed" alone. First read the real numbers: per stage, the largest reported `input_tokens` against the slot less the
  reply. Then decide one budget for the true request (the deep review's item 3.1), with the trigger set from the slot
  less a measured reply, not from a count that leaves the memory out.
- **`REPLY_ROOM_SIZED_PER_ROLE` has no effect on any review role** (`reply_room.py:36-41`). Either the rows are
  re-measured without reasoning tokens or the measuring register (`docs/measuring.md`) should say the switch does not
  reach reviews, so the medium rerun is not read as a measurement of it for them.
- **`REQUEST_BUDGET_FOR_EVERY_STAGE` cannot change how often a stage is summarised** (same cause). Its M17 row lists
  "summaries a stage" as a measure; that measure will not move.
- The deepagents summary text tells the stage its history "has been saved to" a path under `conversation_history`
  (`deepagents/middleware/summarization.py:746-755`). The stage's read tools are rooted at the workspace, so a read of
  it would fail. Not checked in a transcript.

### Order and size

Step 1 (about a day, four files, five tests) removes the instruction to explore and most of the reads; step 2 (two to
three days, graph nodes and state) removes the remainder for sets past one request. Deploy each at a run boundary;
measure on the medium brief with the counts in section 2. Step 1 alone should be judged on reads per file and
summaries per review before step 2 is started: if a 20-file first sprint already fits in one part with the plans as
digests, step 2 can wait for a larger product.

## What was not verified

- Per-file sizes and the exact messages of the measured run: no transcript. The cycle length (one summary per 2.3-3
  calls) is derived from the code and matches the three measured ratios.
- Whether any of the run's summaries were forced by the server refusing a request (section 1.7).
- The milestone review's request was not read in detail; it is named in the plan because its memory is filled the
  same documents-first way.

Scratch reproduction of the count (not in the repository):
`/tmp/claude-1000/-home-arun-Desktop-langchain/d4298d72-a977-42bb-8a37-f5c3120002bc/scratchpad/rr/real.py`
