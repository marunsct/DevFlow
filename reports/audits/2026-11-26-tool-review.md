# Tool review: what each stage is offered, what it uses, and whether the tools work

Date: 2026-11-26 (JST). Read-only review; nothing in `src/`, `tests/`, config or docs was changed, no run was touched.

The owner's question: are the right tools offered to the agents or is something withheld, do the tools fire, are they
used, do they work as intended, and do they add value.

## What was read

- **Code.** `src/app/agents/role_agent.py` (where every tool list is built), `stage_tools.py`, `stable_tools.py`,
  `lean_fixer.py`, `settled_answer.py` (the withholding), `specialists.py`, `src/app/tools/*`,
  `src/app/analysis/package_exports.py`, `src/app/switches.py`, `src/app/observability/switch_firing.py`.
- **Transcripts.** The 26 most recently written transcripts over 0.5 MB, streamed inside the worker: runs started
  11-24 02:14 JST to 11-26 08:49 JST. 7,107 model requests, 9,016 tool calls and their results. Each request records
  the tool names it offered (`tools`) and the size of their schemas (`blocks.tool_schemas`), so offers are counted
  from what was sent, not from the code.
- **The four newest runs alone** (run-6c1444a0 tasks-api, run-e799301e, run-17098b4b, run-03668d05), for what the
  harness offers since the FX and deep-review bundles (fixers on their own short tool list).
- **Schema sizes** by building each tool in the worker and measuring its JSON, the way the transcript does. They add
  up to the recorded figure (a fixer's nine tools: 17,129 built, 17,102 recorded).
- **Two experiments in a scratch folder in the worker** (no model call): the search tool against a file with a
  heading line, and the file finder against five patterns.
- Earlier reports, read first and not repeated: `reports/audits/2026-11-25-deep-review-silent-mechanisms.md`,
  `reports/audits/2026-11-25-per-agent-audit.md`, `reports/audits/2026-11-25-deep-review-instructions.md`,
  `reports/research/2026-11-26-graphify-and-performance-features.md` (KG.10 retires `code_graph`).

All times are JST unless marked UTC. Token figures are characters divided by four.

## Summary

| # | Finding | Severity | Evidence in one line |
|---|---|---|---|
| TR.1 | `module_exports` cuts its list at 60 names and says "Only these names exist" | High | Both calls in the sample, live tasks-api fixer: the list for `pydantic` stops at `NegativeInt`; `ValidationError` and `field_validator` are not in it |
| TR.2 | The read tool is withheld for the whole stage, whatever the file | High | 51 of 85 refused reads (60%) asked for a file whose text the request no longer held |
| TR.3 | The notice that goes with a withheld tool contradicts itself and names tools the stage does not have | Medium | One message says "reading and running are withheld", "everything that runs a command still works" and "every tool except three is refused" |
| TR.4 | The four built-in readers carry the library's own descriptions, with false and unhelpful statements | Medium | "reads up to 100 lines" (it is 400), "use the execute tool with `rg`" (no such tool), "almost ALWAYS use this tool before ... `edit_file`", in about 5,600 requests each |
| TR.5 | `grep` answers "No matches found" for a pattern that would match | Medium | 31 of 69 patterns written as regular expressions found nothing (45%), against 15 of 74 plain ones (20%); `^## ` asked 7 times by one reviewer |
| TR.6 | A writer's last write is refused at the call budget, outside fix stages | Medium | 18 refused writes in 15 stage visits of 8 runs: builders, suite writers, test rounds, setup |
| TR.7 | Seven tools in every writer's list made 9 calls in 4,260 writer requests | Medium | 6,221 characters, about 1,550 tokens, a quarter of a writer's tool schema |
| TR.8 | `research` is offered because a check said the model looks things up; in stages it never did | Low | 2,343 offers, 0 calls |
| TR.9 | Four command slips the harness could absorb, each costing a model call | Low | `cd /workspace/...`, a program path doubled with the working directory (7), a `*` with no shell (9 of 9 failed), `python -m py_compile` (3) |
| TR.10 | An edit's error tells the stage to call `replace_lines`, which is off | Low | 1 case; the text is in four places |

What is fine: no stage was offered a tool its prompt does not have, or the reverse, in any system or request text
(the 11-25 fix for the architect holds). No tool was called that was not offered. Tool order and schema bytes are
identical on every call of a stage. The largest tool schema is 7% of a 93,000-token slot. Details in
"Checked and fine".

## 1 to 3. What each stage is offered, what is withheld, what it uses

"Offered / called" are counts over the 26 runs: requests that offered the tool, then calls of it. Schema size is the
median recorded `tool_schemas` in characters. Every stage also has its answer tool (not listed).

| Stage | Offered (from `role_agent.create_role_agent` and its callers) | Schema | What it called | Withheld or missing, and is that right |
|---|---|---|---|---|
| Product manager | `read_file` only (`LEAN_TOOL_LISTS`: a read-only role on an empty workspace) | 2,934 | Nothing in 26 visits | Right. The brief is in the request |
| Tools and models | `ls`, `read_file`, `glob`, `grep` | 17,373 (answer schema) | 37 reads, 3 `glob`, 2 `ls` in 50 requests; every listing answered "No files found" | Right, but the listers are dead weight here: the workspace holds only `docs/` |
| Stack selector | readers, `look_up_package`, `read_docs`, and `research` or the web pair | 11,751 | `look_up_package` 8 in 32 requests; nothing else | Right. The one stage where the registry tool earns its place |
| Specialist advisors (`consult_*`) | readers | 6,871 | 53 reads in 169 requests; `ls`, `glob`, `grep` 0 | Right; the three listers are never used |
| Principal architect | No tools when the specification is written in parts (207 of 284 requests). Otherwise readers; with `look_up_package`, `read_docs` and web tools in 15 requests | 12,506 | 18 reads, 6 `look_up_package`, 3 `read_docs` | Right since LF.1475-1484: the prompt names `read_docs` only where it is offered |
| Architecture review | readers | 8,654 | 294 reads, 96 `grep` (30 found nothing, TR.5) | Right |
| Scrum master | readers | 8,438 | 49 reads, 2 `glob` | Right |
| Technical lead | readers; `changed_since_sprint` once a sprint is accepted | 11,159 | 758 reads, 23 `ls`, 4 `glob`, 2 `changed_since_sprint` | It cannot run anything. The 11-25 evidence review (4b) found it wishing to run the tests; that was answered by giving it the printed errors, which is the right fix. No tool needed |
| Builders, agent loop (backend, database, UI) | 15 to 18: readers, `write_artifact`, `edit_artifact`, `delete_artifact`, `move_artifact`, `run_terminal_command`, `read_command_output`, `look_up_package`, `module_exports` (JavaScript and Python packs), `read_docs`, `research` or web pair, `look_at_page` (products with a page), `changed_since_sprint` | 23,280 to 24,203 | reads 822, commands 231, edits 106, writes 91, `ls` 22, `delete_artifact` 8, `grep` 11; the rest 1 call in all | See TR.7. A write to another work order's file is refused: right |
| Builders, drafting path | none (one file a call) | 0 | 347 requests | Right |
| Unit-test writer | the builder list plus `run_validation` | 23,719 | reads 462, commands 213, edits 45, writes 43, `run_validation` 14 | Writes to product code refused (per-agent audit, PA.3 and PA.8). Right |
| Acceptance author | as the unit-test writer | 24,263 | reads 1,360, edits 186, writes 147, `run_validation` 129, commands 54, `ls` 36 | Right |
| Acceptance review, dispute | readers (and `changed_since_sprint`) | 7,080 | 315 reads, 6 `glob` | Right |
| Test round (thorough) | as the unit-test writer | 24,656 | reads 435, commands 52, `run_validation` 48, edits 19 | Right |
| Fixers, since 11-26 (`lean_fixer.TOOLS`) | `read_file`, `grep`, `write_artifact`, `edit_artifact`, `delete_artifact`, `run_terminal_command`, `read_command_output`, `module_exports`; the web pair after two failed fixes | 17,102 | Four newest runs, 81 requests: reads 67, commands 39, edits 9, `module_exports` 2 (both TR.1), writes 1, `grep` 0 | No `ls` or `glob`: right, the request lists the workspace. No `look_at_page`: see TR.7. Reads refused wrongly: TR.2 |
| Fixers, rewrite path | none | 0 | 211 requests | Right |
| Code, security, milestone and advice reviews | readers (and `changed_since_sprint`) | 7,062 to 8,647 | about 740 reads, 6 `grep`, 2 `ls` | Right: they hold the files they judge (LF.1284-1289). The security review has no advisory tool; the harness asks OSV itself (59 requests in the sample), which is the better place |
| Custom setup (no pack) | the unit-test writer's list plus `use_runtime` | 24,594 | commands 129, reads 92, writes 23, edits 14; `use_runtime` 0 in 162 offers | Known (silent mechanisms, finding 5) |
| Escalation, research brief | none | 0 | | Right |

No model request carries a stage named for the release in these 26 transcripts: the release checks are the harness's.

Never offered to any stage in 7,107 requests: `write_todos` and the sub-agent tool (the library's own; `HARNESS_TASK_LIST`
is unset), `replace_lines` (`LINE_EDITS` unset), `code_graph`, `ask_specification`, and any MCP tool
(`HARNESS_MCP_SERVERS` is unset in the worker, so that path is untested).

### The tools, over 26 runs

| Tool | Requests offering it | Calls | Results that gave nothing or refused | Schema (characters) |
|---|---|---|---|---|
| `read_file` | 5,705 | 6,566 | 844 (13%): 362 an outline in place of the text (two medium runs, `READS_SIZED_TO_THE_ROOM`, now off), about 170 "in the project memory", 117 "quoted whole in your request", 110 "already read", 85 withheld | 1,777 |
| `run_terminal_command` | 4,260 | 970 | 86 refused before running (65 by a rule, 21 withheld); of 883 that ran, 487 exited 0 | 2,191 |
| `edit_artifact` | 4,260 | 538 | 112 (21%): 83 errors, 11 withheld, 10 already applied, 8 repeated | 1,668 |
| `write_artifact` | 4,260 | 356 | 64 (18%): 52 errors, 7 withheld, 5 repeated | 522 |
| `run_validation` | 2,464 | 194 | 1 withheld; 135 of 193 exited 1, which is the suite failing, as expected | 1,090 |
| `grep` | 5,679 | 143 | 46 found nothing (TR.5), 7 repeats | 2,383 |
| `ls` | 5,598 | 134 | 56 (42%): 28 "No files found", 18 repeats, 10 errors or refusals | 466 |
| `glob` | 5,598 | 38 | 21 "No files found" | 1,633 |
| `read_command_output` | 4,260 | 26 | 4 (a guessed name, answered with the real list) | 1,557 |
| `delete_artifact` | 4,260 | 24 | 9 | 774 |
| `look_up_package` | 4,226 | 17 | 2; 14 of the 17 calls were the stack selector's and the architect's | 1,145 |
| `read_docs` | 4,226 | 3 | all three on 11-24, the wrong-registry case since fixed | 1,031 |
| `look_at_page` | 1,795 | 3 | 0; all three by fixers, who no longer have it | 921 |
| `module_exports` | 3,104 | 2 | both cut and mislabelled (TR.1) | 651 |
| `changed_since_sprint` | 903 | 2 | the same call twice by one lead | 691 |
| `move_artifact` | 4,179 | 0 | | 927 |
| `research` | 2,343 | 0 | | 855 |
| `search_the_web`, `read_web_page` | 1,883 each | 0 | | 876, 616 |
| `use_runtime` | 162 | 0 | | 859 |
| The answer tool of a writer (`SpecialistOutput`) | every writer request | | | 5,606 |

Commands by program, 970 calls: `python`/`python3` 213, `cd` first 122 (taken as the working directory, which works),
`ls` 85, `npm` 77, `cargo` 65, `cat` 61, `find` 59, `npx` 57, `mvn` 53, `node` 52. So 212 commands (22%) only looked
at files: the model reaches for the shell's `ls`, `cat` and `find` more often than for `ls` (134) and `glob` (38).

## Findings

### TR.1 - `module_exports` cuts its list at 60 names and says "Only these names exist" (High)

- **Evidence.** `src/app/analysis/package_exports.py:26` `MOST_NAMES = 60`; the names are sorted and cut at lines 135
  and 179; line 207 adds `"note": "Only these names exist; import from this list or write the function yourself."`
  whether or not the list was cut.
- **Live case.** run-6c1444a0 (tasks-api), fixer `defect_fix_2_1`, 10:09:10 and 10:09:59 JST 11-26: two calls with
  `{"module": "pydantic"}`. Both answers list 60 names from `AfterValidator` to `NegativeInt`. The sort puts capitals
  first, so `ValidationError`, `field_validator`, `model_validator` and every other name after "N" is missing, and
  the note says they do not exist. The defect was a test expecting `ValidationError`; the product file imports
  `field_validator`. The fixer had 16 calls and spent two here.
- **How often.** Both calls of the tool in 26 runs. It is one of the eight tools a fixer keeps, and a pack's guidance
  tells stages to use it, so use will grow.
- **Fix.** Return every name while the list is under a character budget (a few thousand characters). When it is
  cut, say how many names there are and that the list is cut, and never say "only these". Add an optional `name`
  argument: asked for one name, answer whether the package exports it and the closest names it does export.
  Files: `src/app/analysis/package_exports.py` (`python_package_exports`, `script_package_exports`, `exports_of`,
  `exports_tools`).
- **Switch.** Always on: the tool states something false.
- **Test that fails on the old code.** A scratch package whose entry file exports 70 names: `exports_of` for it either
  holds the 70th name or says the list is cut; today it returns 60 names and "Only these names exist". A second
  test: `name` set to an exported name past the 60th answers yes.
- **Measured by.** Calls whose answer was cut while claiming to be complete (2 of 2 now; 0 after).

### TR.2 - The read tool is withheld for the whole stage, whatever the file (High)

- **How it works now.** After several reads that returned nothing new, `settled_answer.py` withholds `read_file`
  "for the rest of this stage" (`_READ_TOOL_WITHHELD_NOTICE`, line 2082; `_remember_the_read_tool_is_withheld`,
  line 1259). `wrap_tool_call` (line 2759) then refuses any call of it with "Use what this conversation already
  holds", for any file.
- **Measured.** 85 reads were refused this way in 26 runs. For each I checked whether the stage's request still held
  the file: as a file in its project memory, or as a read result since the last summary.

  | The refused file was | Refusals |
  |---|---|
  | held in the project memory | 17 |
  | read since the last summary, so still in the conversation | 17 |
  | read before a summary, its text gone | 46 |
  | never read and not held | 5 |

  So 34 refusals were right and 51 (60%) told the stage to use text it did not have. By stage: fixers 21 of 36,
  the acceptance author 13 of 17, the builders and the unit-test writer 11 of 21.
- **What the stage did next** (59 refused replies): the same read again 21, a write 17, another tool 12, text only 5,
  its answer 4.
- **The live tasks-api fixer** (run-6c1444a0 `defect_fix_2_1`, 10:10:34 JST 11-26), four refusals in one reply:
  - `tasks_api/routes.py`, `tasks_api/database.py`, `tasks_api/models.py`: **justified.** All three were whole in its
    project memory, and each had been answered with a pointer to it three or four times.
  - `tests/test_models.py`: **not justified.** The memory lists it under "Not included here (read when needed)". The
    fixer read it once at 10:01:46; two summaries followed (10:05, 10:09); the summary's own note says its text "is
    no longer in this conversation". The defect names a failure at `tests/test_models.py:143`. The fixer then wrote
    the product files without the test in front of it.
- **Related, and off.** `FIXERS_HOLD_WHAT_THEY_READ` (LF.1406) re-chooses a fixer's memory after a summary, which
  would move some of the 46 into "held". It does not change the refusal, and it covers fixers only.
- **Fix.** Decide per file, not per tool. When the read tool is withheld, a read of a file that is in the project
  memory, or whose read result is still in the conversation, is refused as now. A read of any other file runs, and
  counts against the stage's call budget like any call. The refusal names the file and says where its text is.
  Files: `src/app/agents/settled_answer.py` (`wrap_tool_call`, the read-withheld state),
  `src/app/agents/project_memory.py` (which files are held, lines 1659-1668),
  `src/app/agents/workspace_backend.py` (the read guard's record of what this conversation has read).
- **Switch.** Always on: the refusal's own sentence is false in 60% of cases.
- **Test that fails on the old code.** A stage with the read tool withheld: a read of a file neither held nor read in
  this conversation reaches the tool; a read of a held file is refused. Today both are refused. Build the fixture
  from the captured `defect_fix_2_1` conversation.
- **Measured by.** Refused reads by the four classes above (`loop.sh effects`); fix stages that end with no write.
- **Not shown.** That a wrong refusal lost a fix. This is a count of refusals, not of outcomes.

### TR.3 - The notice that goes with a withheld tool contradicts itself and names tools the stage does not have (Medium)

- **Evidence.** The same fixer, 10:10:34 JST, one human message made of four blocks:
  1. `LAST_CALLS_KEPT_FOR_A_WRITE` (`settled_answer.py:1979`): "Reading and running are withheld from here".
  2. `_READ_TOOL_WITHHELD_NOTICE` (line 2082): "`grep` and the directory listings still work, and so does everything
     that changes a file or runs a command."
  3. `_a_tool_withheld_notice` (line 2059): "`read_file` has been withheld ... Everything else still works."
  4. `stable_tools_notice` (line 1897): "refused if called on this call: every tool except `delete_artifact`,
     `edit_artifact`, `write_artifact`."
- Blocks 2 and 3 are false on this call; block 4 is true. A fixer has no directory listing at all since FX.3
  (`lean_fixer.TOOLS`), so block 2 names tools it was never offered. The phrase reached fixers in 5 requests of the
  live run.
- The refusal just before it said "The tools you may call now: `delete_artifact`, `edit_artifact`, `grep`,
  `module_exports`, `read_command_output`, `run_terminal_command`, `write_artifact`" (line 2787). That was true for
  the call it answered and false for the next one, which is the only call the model can act on.
- This is not the 11-25 instructions finding 4 (the first-12 list); that one is fixed.
- **Fix.** Build one notice per call from the set that is really withheld on that call: one sentence for why, one
  list of what may be called, taken from the offered list. The older blocks give their reason only. The refusal's
  "you may call now" list is computed for the next call, or left out when the next call's set is not known.
  Files: `src/app/agents/settled_answer.py`.
- **Switch.** Always on (what the model is told must be true).
- **Test that fails on the old code.** For a stage offered a fixer's tools, on its last two calls with the read tool
  withheld: the notice names no tool outside the offered list, and no sentence says a tool works that block 4
  refuses. A second test bans the whole words the prompt-rule policy lists, since the notice is prompt text.
- **Measured by.** Calls to a withheld tool on the call after a notice (`loop.sh effects` counts refusals already).

### TR.4 - The four built-in readers carry the library's own descriptions (Medium)

- **Evidence.** `ls`, `read_file`, `glob` and `grep` come from deepagents 0.7.13 through
  `role_agent._workspace_filesystem_middleware` (`src/app/agents/role_agent.py:352-370`). The middleware takes
  `custom_tool_descriptions`; the harness passes none, so the library's text is sent as it is, in 5,598 to 5,705
  requests each. Statements in them, against this harness:

  | Tool | The description says | Here |
  |---|---|---|
  | `read_file` | "By default, it reads up to 100 lines" | 400 (`workspace_paths.py:150`). The prompt's copy of this sentence was fixed on 11-25; the tool's own was not |
  | `read_file` | "Speculatively batch multiple `read_file` calls in one response when several files may be useful" | The prompts say to read only a file named as not included. 13% of reads return nothing new, and five reads are made per write in fix stages |
  | `read_file` | "Large tool results may be offloaded to a file"; images, audio, video and PDFs "return multimodal content blocks" | Cut command output is read with `read_command_output`; the served model reads no images |
  | `ls` | "You should almost ALWAYS use this tool before using the read_file or edit_file tools" | No stage has `edit_file`. Every request lists the workspace and says it need not be listed |
  | `grep` | "If you genuinely need regex, use the execute tool with `rg`" | No stage has `execute`; `rg` is not an allowed program |
  | `grep` | "`grep(pattern="foo\|bar")` searches for the literal text" | The harness's backend tries each alternative (`workspace_backend.py:1453`): `test_alpha\|test_beta` found both in the scratch test |

- The 11-25 instructions review compared tool names in messages with the offered list and found them consistent. It
  did not read the schemas, which is where these are.
- **Fix.** Pass the harness's own descriptions for the four tools: the real default, read the files the work needs
  in one reply (keeping the batching, dropping "speculatively"), where cut output is read, and no tool that is not
  offered. Shorter than the library's (the four are 6,259 characters now). Files: `src/app/agents/role_agent.py`.
- **Switch.** Always on for the false statements. The reading sentence is a wording change with a measurable effect;
  ship it in the same change and watch the measure below.
- **Test that fails on the old code.** Build the middleware's tools: no description names a tool outside the
  harness's tool names (`edit_file`, `execute`, `write_file`), and `read_file`'s states the default the path
  middleware applies. Plus the banned-words test for the new text.
- **Measured by.** Reads per write and the share of reads that return nothing new, per stage, before and after;
  hidden scores unchanged.

### TR.5 - `grep` answers "No matches found" for a pattern that would match (Medium)

- **Evidence.** 143 calls. 69 patterns were written as regular expressions (`.*`, `|`, `^`, `\.`, a character
  class); 31 of them found nothing (45%). Of 74 plain patterns, 15 found nothing (20%).
- The tool matches literal text. A note says so, but only for some characters: `^## ` on the specification was
  answered "No matches found" with no note, seven times, to the architecture reviewer of run-e799301e (08:52 to
  10:39 JST 11-26), who was looking for the section headings. In the scratch test, `^## ` finds nothing in a file
  whose second line is `## Heading`.
- Other cases: `^async fn list_notes`, `^name = "url"` in a lock file, `import.*from.*LoginPage`,
  `version = "2\.4\."`, `Date.now\(\)`.
- The architecture reviewer is the heaviest user (96 of 143 calls, 30 empty).
- **Fix.** Match as a regular expression when the pattern compiles as one and the literal search found nothing; say
  in the result which way it matched. Keep the literal search first so plain text behaves as now. Where neither
  finds anything and the pattern has any special character, say so (today the note misses `^` and `$`).
  Files: `src/app/agents/workspace_backend.py` (`grep`, `_each_alternative`).
- **Switch.** Always on: "No matches" for text that is there is a wrong answer.
- **Test that fails on the old code.** A file with a line `## Heading`: `grep("^## ")` returns that line. A file with
  `async fn list_notes`: `grep("^async fn list_")` returns it. `grep("a.b(")` (not a valid expression) still searches
  literally.
- **Measured by.** Share of searches that find nothing, by pattern kind (45% and 20% now).
- **Not shown.** That each of the 31 would have matched; only the anchor case was reproduced.

### TR.6 - A writer's last write is refused at the call budget, outside fix stages (Medium)

- **Evidence.** 18 calls of `edit_artifact` (11) or `write_artifact` (7) were answered "withheld ... No tool is left
  to you: return your structured response now", in 15 stage visits of 8 runs: backend builder 5, unit-test writer 4,
  acceptance author 4, test round 3, UI builder 1, setup 1. None in fix stages.
- **Cause.** LF.1270 keeps a fix stage's last two calls for a write (`_a_fix_stage_s_last_calls`,
  `settled_answer.py:1992`). Every other writing stage still loses every tool on the calls kept for its answer.
  The same loss was measured for fixers before LF.1270 (10 fix stages on one medium run).
- **Fix.** Apply the same rule to every stage that can write: on its last two calls the looking tools are withheld,
  the writing tools stay, and the answer is asked for once after a write. Files: `src/app/agents/settled_answer.py`.
- **Switch.** Always on (the owner's rule: what works in one stage is proposed for all).
- **Test that fails on the old code.** A builder stage at its last two calls: `edit_artifact` is not in the withheld
  set and a call of it runs. Today it is refused.
- **Measured by.** Refused writes at the budget per run (18 in 26 runs); builder and suite-writer stages that end
  with a change described in the answer and not on disk.

### TR.7 - Seven tools in every writer's list made 9 calls in 4,260 writer requests (Medium)

- **Evidence**, writers only (builders, unit-test writer, acceptance author, test round, fixers, setup):

  | Tool | Offers | Calls by writers | Characters |
  |---|---|---|---|
  | `move_artifact` | 4,179 | 0 | 927 |
  | `read_docs` | about 4,180 | 0 | 1,031 |
  | `research` or the web pair | about 4,180 | 0 | 855 or 1,492 |
  | `look_up_package` | about 4,180 | 4 | 1,145 |
  | `look_at_page` | 1,795 | 3 | 921 |
  | `module_exports` | 3,104 | 2 | 651 |
  | `changed_since_sprint` | about 680 | 0 | 691 |

  Together 6,221 characters, about 1,550 tokens, a quarter of a writer's 24,000-character schema. The per-agent
  audit (C9, PA.18) and the silent-mechanisms review (finding 5) reported the same picture on earlier runs; nothing
  has changed except for fixers, whose own list (FX.3) dropped six of the seven.
- **Going further than those reports:**
  - `move_artifact` is in `writing_tools` (`role_agent.py:187`) on the argument that create, change and remove belong
    together. Remove is `delete_artifact` (24 calls). Move was called 0 times in 4,179 offers.
  - `look_at_page` is offered to builders, suite writers and test rounds (1,276 offers, 0 calls) and no longer to
    fixers, the stage it was written for (`specialists.py:1313`), who made its only 3 calls in 519 offers. It works:
    both results opened gave the page's roles and names. Either a fixer of a failing page criterion gets it back, or
    it is retired. On this evidence, retire it from the lists and keep the harness's own page probe.
  - `glob` (38 calls in 5,598 offers, 21 of them empty; 1,633 characters) and, for read-only roles on a workspace that
    holds only `docs/`, `ls` and `grep` too: the advisors and the tools architect made 5 listing calls in 219
    requests, every one answered "No files found". `LEAN_TOOL_LISTS`'s empty-workspace rule fired for the product
    manager only (26 requests in 26 runs).
  - The fixer's list shows the gain is real: 17,102 characters against 23,334, with no tool missed in 81 requests.
- **Cost, stated fairly.** 66% of input tokens in the six newest runs were read from the server's cache, and the
  tool list is in the cached part, so the token cost falls mainly on the first call of a conversation and after each
  summary. The other cost is choice: a small model with 17 tools.
- **Fix.** One list of tools per role kind, like `lean_fixer.TOOLS`: builders get the readers, the four file tools
  less `move_artifact`, the command tool and `read_command_output`; test writers add `run_validation`; a tool
  outside the list is added only where the stage's request asks for it (`kept_tools` already does this). The stack
  selector and the architect keep `look_up_package`. Files: `src/app/agents/stage_tools.py`,
  `src/app/agents/specialists.py`, `src/app/agents/role_agent.py`.
- **Switch.** Behind a switch (an efficiency change): extend `LEAN_TOOL_LISTS` or add one switch for the role lists;
  kept only if hidden scores do not fall.
- **Test that fails on the old code.** With the switch on, a backend builder's tool names equal the role list; with a
  request that asks for a page view, `look_at_page` is added.
- **Measured by.** `tool_schemas` characters per writer request (24,000 now, about 15,000 expected); calls refused
  for a tool not offered (0 expected); hidden scores.

### TR.8 - `research` is offered because a check said the model looks things up; in stages it never did (Low)

- **Evidence.** `research_tool.tools_by_tier` offers `research` in place of the web pair when the model diagnosis's
  check (`models/research_check.py`) measured that the model looks things up. Since 11-25 it replaced the web pair
  in most runs: 2,343 offers, 0 calls. The web pair before it: 1,883 offers, 0 calls.
- So the check's "yes" does not predict what the model does inside a stage. `WEB_TOOLS_BY_MEASURED_TIER` (off) would
  remove the tools only for a model the check says never looks things up, which is not this model.
- **Fix.** Let run evidence overrule the check: a tool offered more than a set number of times across scored runs
  with no call is treated as "never calls" for that model. The harness's own lookups (21 stuck-fix lookups, 34 registry requests
  and 59 OSV requests in the sample) are not affected. Files: `src/app/tools/research_tool.py`,
  `src/app/models/research_check.py`.
- **Switch.** Under `WEB_TOOLS_BY_MEASURED_TIER`, as now.
- **Test that fails on the old code.** A model whose check says yes and whose stored use says 0 calls in N offers is
  offered no web tool with the switch on.
- **Measured by.** Offers and calls of `research` per run.
- **Not verified.** I did not read the stored verdict; I infer "yes" from the tool being offered.

### TR.9 - Four command slips the harness could absorb (Low)

Each costs one model call; a fixer has 16.

- **`cd /workspace/<project> && ...` is refused.** run-6c1444a0 `defect_fix_2_0`, 09:38 JST 11-26:
  "'/workspace/tasks-api' is not a directory in this workspace." The same folder as `working_directory` works,
  because `workspace_paths.py:318` strips the sandbox's mount there. `_a_cd_taken_as_the_working_directory`
  (`agent_toolkit.py:773`) does not. The sandbox prints `/workspace/...` in its own output, so the model learns it.
  Test: `["cd", "/workspace/proj", "&&", "prog"]` runs `prog` in `proj`.
- **A program path that repeats the working directory.** `["tasks-api/.venv/bin/python", ...]` with
  `working_directory: "tasks-api"` exits 127 "not found": 7 calls in 3 runs, 5 of them by fixers. The harness
  already shortens such a path when it is an argument ("the working directory is already ..."), not when it is the
  program. Test: that call runs `.venv/bin/python` in `tasks-api`.
- **A `*` with no shell.** `["ls", "-la", ".venv/bin/python*"]`: 9 of 9 such calls failed with "cannot access", and
  nothing told the stage why. Shell operators already get an explanation. Test: the result carries a note that a
  `*` is not expanded here and names the listing tool or `find -name`.
- **`python -m py_compile` is refused as able to "execute arbitrary code"** (3 calls). It compiles and runs nothing.
  This is a Python fact, so it belongs in the per-language table of allowed modules, not in general code.
- Files: `src/app/tools/agent_toolkit.py`, `src/app/tools/sandbox.py` (`workspace_rooted_arguments`).
- **Switch.** Always on. **Measured by.** Commands that exit 127 or are refused for a path, per run.

### TR.10 - An edit's error tells the stage to call `replace_lines`, which is off (Low)

- **Evidence.** run-bc3cbd00 `acceptance_author_2`: "or - simpler - call `replace_lines` with the line numbers of the
  one you meant". `LINE_EDITS` is unset, so no stage has the tool. The text is at
  `src/app/tools/repository.py:1578, 3974, 4364`. Prompts are already cleaned by `role_agent.without_line_edits`;
  tool results are not.
- **Fix.** Give the advice only when `line_edits_offered()`; otherwise say to add a differing line to `find`.
- **Switch.** Always on. **Test.** With `LINE_EDITS` off, the ambiguous-passage error does not name `replace_lines`.

## 4. Works as intended: the most used and the most refused

- **`read_file`** answers the call. Its failures are the harness's own guards (13% of results), covered above and
  in the 11-24 reading-loop reports.
- **`edit_artifact`** results are good: each shows the lines as they now read, and 41 said "matched ignoring
  indentation". Of the 55 errors I could sort (83 in all), 22 are a stage writing outside its files (the testing work order on product code:
  per-agent audit PA.3 and PA.8), about 15 the language service ("would add errors the language service is sure
  of"), 10 "could not find that text". 11 stages repeated an identical failing edit.
- **`write_artifact`**: of 52 errors, 12 are the "refused N writes outside its own files" stop, about 30 a parse or
  language-service refusal, 3 "another fix wrote this file and you have not seen it" (right, in parallel mode).
- **`run_terminal_command`**: the `cd` at the front of a command is absorbed (about 30 notes); shell operators are
  explained (7); a repeated passing command is answered without running (10, plus 23 notes); `rm` is sent to
  `delete_artifact` (10). 7 timeouts. The dependency gate refused 2 installs, both the editable-install case that
  LF.1313 fixed.
- **`run_validation`**: 194 calls, one refusal. The next call after it is a read 83 times and an edit 16 times.
- **`read_command_output`**: 157 command results were cut with a pointer to it; it was called 26 times and answered
  22. Four calls guessed a name and were given the real list.
- **`look_up_package`**: 15 of 17 answered. One refusal was a stage past its share (12 lookups), one a Maven name in
  the wrong form.
- **`ls`**: a folder that does not exist answers "No files found" 28 times and "path_not_found ... exists, but
  nothing has been written under it yet" 4 times. Both are true; the second is clearer.

## 5. Adds value

- **Reading leads to writing slowly.** Fixers: 1,125 reads for 206 changes. Acceptance author: 1,360 for 333.
  Reviews read and answer, as they should.
- **Lookups by the model lead nowhere because there are none.** 17 registry calls, 14 by the two design stages. The
  harness's own lookups do the work: 59 advisory requests, 34 registry requests before a manifest is drafted, 21
  stuck-fix lookups (outcomes are in the 11-25 research on fixers).
- **Calls that only add a turn:** the 844 reads with nothing new, 46 empty searches, 56 empty or repeated listings,
  176 refused or repeated writes, 86 commands refused before running. Together about 1,200 of 9,016 calls (13%).
- **`module_exports` took value away** in its only two calls (TR.1).

## Checked and fine

- **Prompts and tool lists agree.** Every system prompt and opening request of the 26 runs was scanned for the name
  of a tool the request did not offer. The only hits are the architect's `read_docs` on runs before LF.1475-1484.
  Mid-stage notices and tool results were scanned too: TR.3 and TR.10 are the only misses.
- **No tool was called that the request did not offer.**
- **Stable for the prompt cache.** 42 distinct tool sets, none ever sent in two orders. `tool_schemas` had one size
  for each of 602 (run, stage, list) groups. The list changed inside a conversation 8 times in 26 runs (the five I
  opened were 11-24 runs: the web tools added to a fixer, `changed_since_sprint` appearing after an acceptance).
  `STABLE_TOOLS` fired 131 times (a refusal in place of a changed list).
- **Schema size against the slot.** The largest recorded is 25,988 characters, about 6,500 tokens, 7% of a
  93,000-token slot. A fixer's is 17,102 (about 4,300), of which its answer tool is 5,606.
- **Switches on that never fire, tool-related.** `CODE_GRAPH_TOOL` and `ASK_SPECIFICATION` are no longer recorded as
  on (silent mechanisms finding 4, fixed). `LEAN_TOOL_LISTS` fires (26 requests, the product manager).
  `PACKAGE_EXPORTS_NAMED` offers its tool in 3,104 requests for 2 calls (TR.1, TR.7). `WEB_TOOLS_OFFERED` and
  `WEB_TOOLS_AFTER_TWO_FAILED_FIXES`: as the silent-mechanisms review found, offers and no call (TR.8).
  `PRODUCT_PREVIEW` is off in the worker though runs record it as on; not followed up here.
- **`glob` works.** Five patterns in the scratch test all matched; the 21 empty answers in runs asked for files that
  were not there yet.
- **`read_docs`** now defaults to the run's registry (`docs.py:282-314`); no call since the wrong-registry case.
- **Stack packs add no tool.** Tools are defined in `tools/`, `agents/` and `analysis/` only; a pack's guidance names
  `module_exports`, which is offered where the pack's language is one the tool reads.

## Not verified

- Whether any finding costs a hidden test. Everything here is counted from transcripts; nothing was run.
- TR.2's classes rest on my reading of the request: "held" means a `=== path ===` block in the opening request.
  A file held in another form would be counted as not held. The live case was checked by hand; the other 50 were not.
- TR.5: only the `^` case was reproduced. I did not confirm that the specification of run-e799301e has `## ` lines.
- TR.6: whether the 18 refused writes changed an outcome.
- TR.8: the stored verdict of the research check.
- The roughly 36 language-service refusals of a write or an edit were not checked for false findings (the plan
  already carries one such leftover from LF.1401).
- MCP tools: none is configured, so none was offered and nothing could be measured.
- The release stage: no model request in the sample; I did not trace its code.
- Only four runs are on the newest harness, so the fixer's new list rests on 81 requests. Three medium runs
  (run-bc3cbd00, run-c53e7bd2, run-32362f3b) make up about 2,670 of the 6,000 requests that carried tools.
- Token counts are characters divided by four.

## Build list, ranked

Each item stands alone. All are technology-, framework- and product-agnostic except the last part of TR.9, which
goes in the per-language table.

| Rank | Item | Size | Files | On or switch | Test that fails on the old code |
|---|---|---|---|---|---|
| 1 | TR.1 `module_exports` tells the truth when its list is cut, and can answer for one name | S | `analysis/package_exports.py` | Always on | 70 exports: the answer holds the 70th or says it is cut |
| 2 | TR.2 a withheld read is decided per file | M | `agents/settled_answer.py`, `agents/project_memory.py`, `agents/workspace_backend.py` | Always on | A file neither held nor read is read; a held one is refused |
| 3 | TR.3 one true notice per call, built from the withheld set | S | `agents/settled_answer.py` | Always on | No tool named that is not offered; no "still works" for a refused tool; banned-words test |
| 4 | TR.6 every writing stage keeps its last calls for a write | S | `agents/settled_answer.py` | Always on | A builder's edit on its last call runs |
| 5 | TR.5 `grep` falls back to a regular expression and says how it matched | S | `agents/workspace_backend.py` | Always on | `^## ` finds `## Heading` |
| 6 | TR.4 the harness's own descriptions for the four readers | S | `agents/role_agent.py` | Always on | No description names `edit_file` or `execute`; the read default is the real one; banned-words test |
| 7 | TR.9 the four command slips | S | `tools/agent_toolkit.py`, `tools/sandbox.py`, the language table | Always on | One test per slip |
| 8 | TR.7 tool lists per role kind | M | `agents/stage_tools.py`, `agents/specialists.py`, `agents/role_agent.py` | Switch | A builder's list equals its role list |
| 9 | TR.8 run evidence overrules the research check | S | `tools/research_tool.py`, `models/research_check.py` | Switch (`WEB_TOOLS_BY_MEASURED_TIER`) | Checked yes, used 0 of N: no web tool |
| 10 | TR.10 no `replace_lines` in an error when it is off | S | `tools/repository.py` | Always on | The ambiguous-passage error without the name |

Items 1 to 7 touch what the model is told or refused in the stages that fix and write, so they belong in one bundle
at a run boundary. Items 8 and 9 are efficiency changes and want a measuring pair.
