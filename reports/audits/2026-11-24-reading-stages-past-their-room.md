# What a reading stage holds once the product no longer fits whole

2026-11-24. Read-only design plan: no code changed, nothing committed, no run or container touched.
Basis: the code as of `a325ecb8` (LF.1284-1286 deployed), the measurement in the brief (the medium run after
LF.1286), and the stored transcript of the earlier medium run of the same kind of product (2,100 model calls), read
with three scratch scripts named at the end. The live run's own transcript was not read; where a number comes from
the earlier run it says so.

## Short answer

Holding files whole (LF.1284-1286) is right and stays. Past the memory's room it stops, and nothing replaces it: the
files that did not fit are "Not included here", the stage reads them whole into the conversation, and the old loop
returns for exactly those files. On the measured product no arrangement can show the whole product at once - the
product numbered is about four times the memory - so the stage has to be given three things in place of "all files
whole":

1. **an outline of every code file** (each definition, test and marked handler with its line range): 6% of the
   product's size, so it always fits;
2. **the few files it is working on, whole** - chosen at the start by rank, and **chosen again at every summary from
   what the stage has actually read and written** (this is also the answer for the suite's author, whose own files
   go stale);
3. **everything else by line range**, with a whole read answered whole only while the request has room for it.

Build order: the outline (step 1), the held files re-chosen at a summary (step 2), reads sized to the room behind a
switch (step 3). Reviewing in parts (the earlier report's step 2) stays the answer for the reviews and comes after,
if the reviews still loop. A product whose files fit is sent byte for byte as today in every step.

## 1. The measured room

### 1.1 The product against the memory (earlier medium run, every product file any stage read whole)

| Quantity | Value |
|---|---|
| Product files (22 code, 14 tests, 5 configuration, 4 other) | 45 |
| Their text | 272,322 characters, 6,824 lines |
| The same, numbered as the memory holds them | 324,250 characters |
| The memory (0.3 of a 91,776-token window, `project_memory.py:57`, `:888-897`) | 82,598 characters |
| Left for held files after the documents' room (`REVIEW_DOCUMENTS_ROOM`, `project_memory.py:548`, `:755`) | 70,598 |
| Files that fit whole, in the order the lead read them most | 13 of 45 |
| The lead's whole-file reads those 13 cover | 182 of 253 (71%) |
| An outline of all 45 (prototype: definitions, test titles, the marker line above a definition, line numbers) | 18,475 characters, 254 entries, about 410 a file |
| Files that fit whole after that outline | 8 (60% of the lead's reads) |

The brief's "9 files held whole, all that fit" on the live run is the same arithmetic on a product whose first files
are larger. So: the outline costs the room of about five whole files and in exchange names every definition of the
other 32-37 with the line to read it at.

The memory's existing map (`map_of`, `project_memory.py:282-315`) is not that outline: no line numbers, at most 12
definitions a file (`:237`), 20,000 characters, and a test file shows as its two or three helper functions - the
tests it holds are not definitions to `_DEFINES` (`:230-234`). Measured: each 165-324-line acceptance file has 2-3
entries in the map and 9-14 in the prototype.

### 1.2 The true request (finding 1.7 of the earlier report, now measured)

On the earlier medium run, reported `input_tokens` against the slot less the reply (59,776):

| Stage | Calls | Median | 90th | Largest | Past 59,776 | Past the 91,776 slot |
|---|---|---|---|---|---|---|
| technical lead | 188 | 53,977 | 68,289 | 118,150 | 62 | 2 |
| test rounds | 305 | 47,227 | 66,942 | 134,247 | 64 | 4 |
| suite's author | 424 | 50,593 | 74,898 | 143,791 | 102 | 5 |
| suite's review | 130 | 54,793 | 80,640 | 87,151 | 43 | 0 |
| code review | 46 | 48,820 | 71,133 | 86,126 | 15 | 0 |
| every stage | 2,100 | | | 146,251 | 492 (23%) | 53 |

Seven replies ended at their length limit. (A request past 91,776 means that run's slot was larger than the brief's
or the server cut the request; not checked.) The lead's request alone was 37,000-71,000 characters and its fixed
parts (system prompt, tool schemas, environment contract, workspace digest) 34,000-38,000. With a full memory that
is 154,000-192,000 characters, 51,000-64,000 tokens, **before the first read**. The conversation's true room on a
lead is therefore between nothing and about 8,000 tokens, while the summary trigger - which does not count the
memory - lets it grow by 19,000-27,000 counted tokens. One reply of eight whole reads (the lead reads about eight
files a call: 65 reads in 8 calls) is 55,000-65,000 characters and does not fit by itself.

Two consequences for the design:

- **No design may enlarge the memory or the kept conversation.** Everything below works inside today's
  82,598 characters.
- A whole file read into the conversation of a stage past its room is the thing that does not fit. Holding more
  whole files moves the edge; only reading by range removes it.

## 2. The candidates

| | Candidate | Fits the room? | What the stage loses | Cost | Risk to quality | Small runs | Verdict |
|---|---|---|---|---|---|---|---|
| a | Outline of every code file, plus whole text for the files ranked first | Yes: 18,475 + 8 files in 70,598 | The bodies of the files not held (37 of 45) until it reads their lines | Small: one new module, `render`, one sentence in the request | Low: nothing is taken away that was shown before except five whole files' room; a model that ignores the line numbers reads whole as today | Byte-identical (behind `fits_as_today`) | **Build, step 1** |
| b | A per-stage file cache answered with a pointer after a summary | Only as part of the memory: a pointer to text that is not in the request points at nothing, and section 1.2 leaves no room for a second store | - | - | A stage told "you have it" about text it cannot see: the fault `_the_text_is_in_view` was built to end (`workspace_backend.py:463-493`, `:1326-1329`) | - | **Not as a separate cache.** Its working form is: the memory's whole files are re-chosen at each summary from what the stage read (step 2). The pointer then points at real text |
| b' | The summary names the files read (LF.1285) so the model stops re-reading | Yes | Nothing | Built | None | - | Built; measured not enough (4 summaries, 65 reads after it). A name is not the text. Kept as the record step 2 reads |
| c | Review or plan in parts | Yes by construction | Cross-file faults in one part (answered by the outline of the other parts) | Medium: graph nodes, state, join | Medium for a plan: work orders of two parts can clash, and a join of plans is harder than a join of findings | Unchanged (one part) | **Reviews: yes, after steps 1-2** (earlier report 3.2). **Lead: no** |
| d | The lead given the sprint's slice of code only | Yes | Sight of code outside the slice | Small | High where the slice is wrong: the suite's tests reach the product over its interface, not by imports, so no agnostic reader maps a due test to the files behind it; `lead_files` already ranks by the criteria's words and by imports (`lead_files.py:78-86`). A wrong slice hides the file the sprint must extend | - | **As the ranking of the whole tier only** (never as "the rest left out"): the outline keeps every other file in sight |
| e | The author's held copy refreshed after each write | A re-render per write refits the room each time | - | A re-render at each write was measured: 48 calls re-read 2.4M cached tokens, about 18 minutes (`project_memory.py:1094-1106`) | - | - | **Refresh at each summary, not each write** (step 2): at a summary everything after the memory is evaluated again anyway |
| f | (found) A whole read that the request has no room for is answered by the file's outline and line ranges | Yes: this is the rule that makes the room hold | Friction: two or three range reads where one whole read was wanted | Small | Medium: changes what a tool returns. An earlier guard that refused re-reads after a summary cost a testing stage its work (`workspace_backend.py:463-470`); this one always gives the outline and never refuses a range | Unchanged while a whole read fits | **Build behind a switch, step 3** |
| g | (found) Count the memory in the summary trigger | - | - | Trivial | Every stage of every size summarises about 27,000 tokens sooner | Changed | Still not alone (earlier report 3.4). Step 3 gives the same protection only where the room is short |
| h | (found) The lead's own request made smaller (it quotes about 31,000 characters of the specification beside a memory that holds the same document's digest) | Frees up to four whole files | Depends on what is cut | Small | Not judged here | Changed unless gated | **Filed**: measure on the live run's `request_budget` records first |

Why (a) with (b as step 2) and not (c) for the lead: a plan is one answer about the whole sprint; what the lead
needs of most files is what they define and where (the outline), and the body of a handful (the sprint's tests, the
entry file, the data shapes, the handlers it extends - the measured top of its reads). A review is different: it
judges every body, so for a review the outline only tells it where to look and parts remain the way to see
everything once.

What other harnesses do (recalled, not looked up today): a ranked map of definitions beside a few whole files
(Aider's repository map); file skeletons first, line ranges second (Agentless); the files read most recently put
back after a compaction within a budget (several coding CLIs); a windowed file viewer as the only reader
(SWE-agent). Steps 1, 2 and 3 are those four, sized by this harness's measured room.

## 3. The design

### 3.1 Step 1 - the outline (small; always on past the size gate)

New `src/app/analysis/outline.py`:

- `entries(path, text) -> list[tuple[int, int, str]]` - (first line, last line, the line's text cut to 110
  characters) for: each line that defines something, by the two patterns the harness already has
  (`project_memory._DEFINES`, `project_memory.py:230-234`; `project_graph._DEFINES_ELSEWHERE`,
  `project_graph.py:54-60`); each test a suite or unit-test file declares (`suite._TITLED` and `_NAMED`,
  `suite.py:254-255`); and the marker line directly above a definition (a line that is not itself a definition and
  begins with a character that is not a letter, digit or quote), shown with it - that is where a handler's address
  is written in most languages, read without knowing any of them. An entry's last line is the line before the next
  entry at the same or a lesser indent. Anything a language needs beyond this goes in a column of
  `app.stacks.languages`, not here.
- `rendered(files, most_characters, order) -> str` - one block: `path (N lines)` then one entry a line as
  `first-last  text`. No cap per file; past `most_characters` the files are taken in `order`
  (`project_memory._by_relevance`, `:254-279`) and the rest counted, as `map_of` does.

Changes:

- `project_memory.render` (`:467-669`): when `review_files` is given, every code file not held whole is in the
  outline (it replaces `map_of` for this render only, `:661-668`), the outline is rendered before the whole files
  and its length comes out of `review_room` (`:548`). Order of the block: head, the documents' digests, the outline,
  then the whole files - what changes least first, so step 2 keeps the server's cache up to the whole files.
- `review_files.held_section` (`review_files.py:218-229`): one more sentence - the other files are outlined in the
  memory with their line numbers; read the lines needed by range. (New model-facing text: banned-words test.)
- `scripts/loop/effects.py` `review_reading_lines` (`:158-196`): per stage also whole reads against range reads, and
  `acceptance_author` added to `_REVIEW_STAGE` (`:160`).

Tests that fail on the old code (new file `tests/test_a_stage_past_its_room_holds_an_outline.py`):

1. `test_every_code_file_is_whole_or_outlined_with_its_lines`: 30 files of 8,000 characters, a definition at line
   150 of a file that does not fit; `render_for_a_review` shows that line number for it. Old: the map has no line
   numbers.
2. `test_a_test_file_s_outline_names_its_tests`: a 200-line suite file with ten titled tests left out of the whole
   tier; all ten titles are in the memory with their lines. Old: its two helper functions only.
3. `test_an_outline_entry_ends_where_the_next_begins`, and `test_a_marker_line_is_shown_with_its_definition`.
4. `test_an_outline_reads_a_language_with_no_import_reader` (a file `_DEFINES_ELSEWHERE` covers).
5. `test_the_outline_sentence_uses_no_banned_word`.
6. Guard, passes on old and new: a product that fits - memory and request byte-identical (extend the guards in
   `tests/test_a_review_holds_the_files_it_judges.py` and `tests/test_a_lead_holds_the_files_it_plans_from.py`).

### 3.2 Step 2 - the whole files are chosen again at every summary (medium; always on past the gate)

Covers (b) and (e) with one mechanism. A summary is the moment the stage loses what it read and the moment the
server's cache after the memory is lost anyway.

- `compaction._prepare` (`compaction.py:192-246`): besides the merged ranges, keep the reads in order with their
  counts (`_files_read`, `:122-139`, before `_merged_ranges` drops the counts) in a new record `harness_reads`,
  carried from summary to summary like `FILES_READ`.
- `compaction._build_new_messages_with_path` (`:336-378`): beside `forget(...)`, leave a mark in the visit's
  `project_memory` store (`stage_memory.store`) with the files written and the reads.
- `review_files.chosen_again(named, written, reads, repo_root) -> list[str]`: the files this visit wrote, the
  latest first; then the files it read, most reads first, then latest; then the opening's order. Only files
  `under_review` accepts (`review_files.py:114-146`).
- `project_memory.ProjectMemoryMiddleware.wrap_model_call` (`:1111-1158`): on the mark, when some file the visit
  read or wrote is not held as it is now, render again with `render_for_a_review` on `chosen_again`, replace the
  visit's `snapshot`, `held`, `files` and `first_held`, and rewrite the request's line of held files in the message
  it sends (the way `_without_the_list` rewrites a re-plan's request, `:709-721`, `:1133-1134`). Files kept by the
  harness and a later sprint's tests stay out as now (`:573-582` run before the held-file branch).
- `review_files`: a tuple `WRITING_STAGES = ("acceptance_author",)`; `holds_what_it_reads` covers it. The author
  opens as today (a first writing has no files; a repair's suite files go through the same gate as the suite's
  review, `acceptance_nodes.py:1329-1340`); from its first summary its own files are held as they are now.
- Not per write: between summaries a write's own result is the current copy in the conversation, a read of a file
  changed this visit already returns the file (`project_memory.py:1172-1177`), and the memory stays byte for byte.

Effect on the loop: after one summary the files the stage was reading are in the memory, numbered; a read of one is
a one-line pointer, and a run of pointers already ends the stage's reading (`settled_answer.py:945-959`). What the
stage reads beyond the room is in the outline.

Tests that fail on the old code (`tests/test_a_summary_holds_what_the_stage_was_reading.py`):

7. `test_after_a_summary_the_memory_holds_the_files_the_stage_read`: a visit opened holding A and B, with C, D, E
   outlined; the replaced messages read C twice and D once; the next call's memory holds C and D numbered and a read
   of C is answered with the pointer. Old: the memory is the visit's first snapshot and the read returns the file.
8. `test_after_a_summary_a_writing_stage_holds_its_files_as_they_are_now`: the stage wrote F and changed it; the
   next call's memory holds F's present text. Old: no F, or its text at the visit's start with "read for the current
   text".
9. `test_the_request_names_the_files_held_now`.
10. `test_a_later_sprint_s_tests_are_not_chosen` and `test_a_file_the_harness_keeps_is_not_chosen`.
11. Guards: `test_the_memory_is_not_rendered_again_between_summaries` (a write between two calls leaves the snapshot
    byte-identical) and `test_a_stage_whose_reads_were_all_held_keeps_its_memory` (small products: nothing changes
    at a summary).

### 3.3 Step 3 - a whole read is given whole only while the request has room (small; switch, off until measured)

Switch `READS_SIZED_TO_THE_ROOM` (doubtful, so behind a switch and in `docs/measuring.md`): it changes what a tool
returns.

- The room left is known exactly: the last reply's reported `input_tokens` against the input ceiling
  (`context_budget.py:354`), less what this reply's earlier reads returned. Kept per visit in `stage_memory` by a
  small middleware beside `FreshConversationMiddleware` (`workspace_backend.py:496-516`).
- `WorkspaceBackend.read` (`workspace_backend.py:1279-1345`): a read with no `offset` or `limit` of a file longer
  than a range read, when its numbered text is larger than the room left, is answered with the file's outline
  (`outline.entries`), its length and "read the lines you need by range". A range read is never changed. The same
  answer for a whole re-read of a file whose text left at a summary and which has not changed since
  (`_the_text_is_in_view`, `:1326-1329`) once step 2 could not hold it.
- A product that fits never meets it: the room left is larger than any of its files.

Tests: 12. `test_a_whole_read_past_the_room_left_gets_the_outline_and_its_ranges` (old: the whole file);
13. `test_a_range_read_is_never_answered_with_an_outline`; 14. `test_a_whole_read_that_fits_is_whole` (guard);
15. switch off: as today (guard); 16. banned words for the answer's text.

### 3.4 Step 4 - reviews in parts (earlier report, section 3.2; only if the reviews still loop)

Unchanged, with one gain from step 1: a part's memory holds its files whole and the other parts' files as the
outline. Start it when, after steps 1-2, a review on the medium brief is still above 1.5 reads a file.

### 3.5 Filed, not built here

- The lead's request size (candidate h) and the trigger's count (g): read the live run's `request_budget` records
  for the held stages (`project_memory._noted_as_built`, `:830-837`) and the largest `input_tokens` a held stage
  reports. If held openings are past the input ceiling at the first call, the whole tier must be sized to the
  ceiling less the request, not to the memory's share (`render_for_a_review`, `:758-770`, deliberately does not).
- The slot on the earlier run: 53 requests reported more than 91,776 input tokens.

## 4. What each stage holds past its room

| Stage | Whole at the start | Outline | After a summary |
|---|---|---|---|
| Technical lead | The sprint's due tests and the code its criteria touch, in turn (`lead_files.for_the_plan`, as now) | Every other code and test file | The files it read most |
| Test round | The milestone's changed files (as now) | The rest | The files it read most |
| Suite's review | The suite's files not locked earlier (as now) | The rest, the product's code included | The files it read most |
| Suite's author | As today | From its first summary | Its own files as they are now, then what it read |
| Reviews | The files under review (as now) | The rest | The files it read most; parts if step 4 is built |

## 5. How to measure

Per held stage, from the transcript (`loop.sh effects`, the extended `review_reading_lines`): summaries; whole reads
and range reads per distinct file; pointer answers; files held at the start and after each summary; the largest
reported `input_tokens` against the ceiling; calls and minutes.

| Measure (medium brief) | Now (brief; earlier run) | Target after steps 1-2 | With step 3 |
|---|---|---|---|
| Lead: reads a file | 2.4 in 8 calls and rising (12.2 over a full visit) | at most 1.5 | at most 1.2 whole |
| Lead: summaries a visit | 4 in 8 calls (21) | at most 2 | at most 1 |
| Lead: calls to a plan | 30-159 | under 15 | under 12 |
| Author: reads of its own file | 3-8 (up to 24) | at most 2 | - |
| Held stages' calls past the input ceiling | 21-33% (earlier run) | not higher | none |

Quality, which must not fall: plans sent back as not ready (`work_order_problems`), work orders naming a file or
name that does not exist, the sprint's suite result, the hidden score. Small families: the guard tests, and one run
whose effects report shows no outline and no re-chosen memory.

Stop rule for step 3: if the lead's plans are sent back more often with the switch on, or a stage makes more than
three range reads of one file in a row, it stays off and the answer is parts for that stage.

## 6. Order, size and risk

1. Step 1, about a day: one module, `render`, one sentence, six tests. Lowest risk, and it is what makes range reads
   possible at all.
2. Step 2, a day to a day and a half: `compaction`, the memory middleware, `review_files`, the author's node; seven
   tests. The main risk is a memory re-rendered when it should not be (cache); the two guards cover it.
3. Deploy 1 and 2 as one bundle at a run boundary; measure on the medium brief.
4. Step 3, about a day, behind its switch; on for one medium run.
5. Step 4 only on the measure in 3.4.

All of it reads languages through the existing patterns and tables; no stack is named outside them.

## What was not verified

- The live run after LF.1286: its transcript, its files' sizes and its held stages' real request sizes. The room
  table is the earlier medium run's product (45 files) on the brief's window.
- That the local model reads by range when given line numbers. Step 1 makes it possible; step 3 is there because it
  may not.
- The outline prototype is a scratch script, not the proposed module; the marker-line rule was checked on this one
  product only (it caught the handlers' addresses and class-level markers; it has not been run on a product whose
  handlers are registered by a call rather than a marker - those appear as their handler functions only).
- The cost of evaluating a re-rendered memory at a summary on the owner's server (at most the whole-file tier,
  about 17,000 tokens a summary); not timed.

Scratch scripts (not in the repository):
`/tmp/claude-1000/-home-arun-Desktop-langchain/d4298d72-a977-42bb-8a37-f5c3120002bc/scratchpad/outline/sizes.py`
(files, sizes and reads per stage),
`/tmp/claude-1000/-home-arun-Desktop-langchain/d4298d72-a977-42bb-8a37-f5c3120002bc/scratchpad/outline/fit.py`
(what fits whole, the outline prototype) and
`/tmp/claude-1000/-home-arun-Desktop-langchain/d4298d72-a977-42bb-8a37-f5c3120002bc/scratchpad/outline/inp.py`
(reported input tokens against the slot).
