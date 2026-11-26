# Graphify, a code knowledge graph for the harness, and other performance features

Date: 2026-11-26 (JST). Read-only research; nothing in `src/`, `tests/`, the configuration or the owner's machine
was changed, and nothing was installed.
Evidence: the project's GitHub page, PyPI record and integration page, its issue tracker, four independent write-ups,
the published work on code graphs for repair agents (sources at the end), and this repository's code and reports
(`analysis/project_graph.py`, `agents/code_map.py`, `graph/localised_fix.py`, `analysis/outline.py`,
`agents/stage_tools.py`, `agents/memory_slices.py`, `analysis/grammar_parse.py`, `docs/PRODUCT.md`,
`docs/measuring.md`, `reports/research/2026-11-25-fixers-context-and-lookups.md`,
`reports/audits/2026-11-25-deep-review-context.md`).

The owner's question: "does graphiphy reduces the token and provides better performance when used with claude code if
so set it up, also research if that is something our harness can benefit from and create implementation plan if so,
also research on any such other useful features that improve performance and quality and plan for them as well".

## Short answers

1. **"Graphiphy" is graphify** (Graphify Labs, PyPI package `graphifyy`). It parses code with tree-sitter into a
   graph of files, symbols and relations, and gives the assistant commands to query the graph instead of reading
   files.
2. **Installing it for Claude Code: no, not as an always-on install.** The large savings figure (71.5x) is the
   project's own, from one hand-picked corpus, against a baseline of reading every file. Every independent measurement
   found of whole sessions shows no saving or a loss: 0 graph queries in about 60 sessions; +101% tokens at the same
   accuracy; 1.6-1.9x the cost on a large monorepo. A single lookup is cheaper than reading a file (628 against
   13,659 tokens), but Claude Code does not choose the graph by itself, and when told to, it pays for the graph and the
   reads. A bounded one-hour trial with no hooks is described in 1.5 if the owner wants a number for this repository.
3. **The harness: yes to the idea, no to the tool.** The harness already has its own code graph, and it already
   uses it the right way (the harness queries it and puts the answer in the request). Its graph is thin: import edges
   for Python and JavaScript/TypeScript only, definitions by pattern, no symbol references, and routes and tests are
   not in it. Seven of the benchmark languages get an almost empty answer. Ten items, KG.1-KG.10, close that with
   the tree-sitter grammars the worker already ships. Graphify itself would add a tool the local model never calls
   (`code_graph`: 0 calls in about 3,500 offers).
4. **Do not expect the graph to cure the re-reading by itself.** The 17.8 reads a file were caused by the request
   being rewritten (the fold fault and the summaries), which the 11-25 fixes address. The graph's part is different:
   the right files held from the first call, in every language, and definitions handed over instead of whole files.
5. **Other features: six items, PF.1-PF.6.** Most of what other harnesses do is already built here (section 3.1).
   The largest lever left is not code: the slot size (0 summaries on the 182K slot, one every 3-16 calls on 93K).

## 1. Graphify

### 1.1 What it is

| | |
|---|---|
| Name | graphify. The PyPI package is `graphifyy` (two y); the command is `graphify`. Other `graphify*` packages on PyPI and the site graphify.net are not the project's. |
| Repository | `github.com/Graphify-Labs/graphify` (moved from `safishamsi/graphify`, which still redirects; branch `v8`). Many forks and re-implementations exist (graphify-rs, graphify-ts): not the same code. |
| Author | Graphify Labs; started by the GitHub user safishamsi. PyPI owner account `captainturbo`. A hosted paid product, Graphify Cloud, is built on it. |
| Licence | Apache-2.0 (an MIT licence file is kept for earlier versions). |
| Activity | First release 0.1.1 on 2026-04-04; latest seen 0.9.120 (well over 100 releases in under eight months). About 153k stars, 14.7k forks, 802 open issues, 951 open pull requests on 11-26. |
| Needs | Python 3.11.5 to 3.14. This machine has 3.14.4, `uv` and `pipx`. |
| Installs | networkx, numpy, rapidfuzz, PyYAML, tree-sitter 0.25 and about 30 grammar packages. Extras for an MCP server, PDF, video, graph databases and model back ends. |

How it works:

- **Code**: parsed on the machine with tree-sitter (about 40 languages). No model call; a 17,750-line Python library
  built in 2.1 seconds, a rebuild after one edit in 1.6 seconds (independent test, version 0.9.92).
- **Documents, PDFs, images**: sent to a model for "semantic extraction": the assistant's own model inside
  `/graphify`, or a back end chosen by whichever API key it finds (Gemini, Kimi, Claude, OpenAI, DeepSeek, Azure,
  Bedrock, Ollama). `--code-only` skips this; `GRAPHIFY_BACKEND=none` forbids it.
- **Output**: `graphify-out/graph.json`, `GRAPH_REPORT.md`, `graph.html`. Each edge is marked `EXTRACTED` or
  `INFERRED`.
- **Queries**: `graphify query "<question>"` (a subgraph, about 1,700-2,000 tokens an answer), `graphify explain
  "<name>"`, `graphify path "<A>" "<B>"`; the same as MCP tools (`query_graph`, `affected`, `get_neighbors`, ...).
- **What it writes outside the project**: `graphify install` writes `~/.claude/skills/graphify/SKILL.md` and a
  section in `~/.claude/CLAUDE.md`. `graphify claude install` writes a section in the project's `CLAUDE.md` and
  PreToolUse hooks in the Claude Code settings; `--project` puts all of it under the repository's `.claude/`.
  `graphify hook install` adds git hooks that rebuild on commit and checkout. Queries are logged to
  `~/.cache/graphify-queries.log`.
- **The hooks**: before search calls, single-file reads and shell readers (`cat`, `head`, `sed -n`) the hook reminds
  Claude to ask the graph first (at most 5 reminders a session); `--strict` refuses the first raw read of a session.
  The sources disagree on the exact matchers; I could not read the hook's JSON.
- **Network**: none for code. The document pass and the hosted MCP server (`api.graphify.com`) send data out. The
  project states it has no telemetry.

### 1.2 Does it reduce tokens and improve results with Claude Code?

| Source | What was measured | Result |
|---|---|---|
| The project (website, skill step 8) | corpus tokens divided by the tokens of a graph answer, on one mixed corpus of 52 files | 71.5x. The baseline is "read every file"; the build's model calls are not counted; tokens are estimated as characters / 4. The project's own table gives 5.4x for a 4-file corpus and about 1x for a 6-file library. |
| The project (README, today) | retrieval and question answering against memory tools | recall 0.497, key-fact coverage 82.0% against 70.8% for grep/read on 6 questions. The README no longer states a token figure. |
| Independent reproduction guide (pantheon-org) | the benchmark's code | "from a single self-curated example, not an independent benchmark"; no fixture to reproduce it. |
| Independent, one Python library (HackerNoon, 10-21) | single lookups | `explain` 628 tokens against 13,659 to read the file (about 20x); a `query` 1,728 tokens, cut at 82 of 536 nodes; an ambiguous name is refused. Not a session measurement. |
| Independent, two production projects, 14 days (dev.to, May) | about 60 Claude Code sessions, transcripts searched | 0 graph queries on both projects; the report file read once; about 1,500 hook reminders ignored. "A knowledge graph the agent doesn't read isn't a tool." |
| Issue 985, the reporter (May) | 1,484 files | each query about 2,000 tokens, 3-4 a workflow; grep cost less. Open, no maintainer answer. |
| Issue 985, a .NET monorepo (August) | graph MCP against a code-only agent | 1.6-1.9x the cost, weaker answers. |
| Issue 985, a public C#/TypeScript repository of 136,000 lines (11-23) | 10 runs an arm | the agent never called the graph unprompted; told to ask it first: 195,676 tokens against 97,265 (+101%) at the same accuracy. |
| Issue 985, a contributor's benchmark (11-23) | | "graphify calls don't replace grep for day to day use cases". |
| A different tool of the same kind, CodeGraph, on a 280-file repository (40 runs) | with and without | tool calls -55%, tokens -22.6%, time -20%, cost +6.8%, same answers. |

Reading: the graph answers a structural question in fewer tokens than reading files, and it caps the worst
exploration. A whole Claude Code session does not get cheaper, because (a) Claude already searches narrowly with
grep and sub-agents, so the real baseline is far below "read everything"; (b) it does not choose the graph unless
forced; (c) forced, each answer is about 2,000 tokens that stay in the conversation and the files are still read
before an edit. The cases where it helps are a first look at an unfamiliar large codebase and cross-module questions.
This repository is the opposite case: the sessions that work on it carry `docs/STATE.md`, `docs/PRODUCT.md` section 18
(the repository map) and a memory index, and mostly know where things are.

### 1.3 Safety

- **Advisory GHSA-pcc4-rvhr-2pr8** (medium, 5.5): the Fortran extractor follows `#include` lines, so indexing an
  untrusted repository could read host files into the graph. Not a risk for the owner's own code; the fixed version
  was not shown on the page I could read. Do not index a repository you do not trust.
- **Provenance**: the package name with a doubled letter looks like a typosquat and automated skill audits (Snyk on
  skills.sh) flag it as unverifiable; it is nevertheless the name the project's own README gives. Install only
  `graphifyy`, pinned to a version, from PyPI.
- **Pace**: several releases a week, 802 open issues. The hooks and commands have changed between 0.9 releases; a
  hook that breaks stops or slows every Claude Code session in the project.
- **Data leaving the machine**: only if the document pass or the hosted MCP server is used. This repository holds
  213 Markdown files (plans, decisions, the operator section of the handover): use `--code-only` and
  `GRAPHIFY_BACKEND=none`, and do not add the hosted server.
- **What it would change here**: a section in the checked-in `CLAUDE.md`/`AGENTS.md` chain; hooks that fire in every
  session, including the audit cron and the build agents in `.claude/worktrees/` (ten copies of the repository,
  which it would also index unless excluded); `graphify-out/` as untracked files against the "leave nothing
  uncommitted" rule; a rebuild at every commit of a repository that is committed many times a day.

### 1.4 Verdict

**Do not install it as a standing part of the owner's Claude Code.** The evidence does not support "reduces tokens"
for session work, and the always-on form (CLAUDE.md section and hooks) has real costs in this repository. Nothing is
lost by waiting: the code graph costs nothing to build later.

If a structural aid for Claude Code is wanted, the lower-risk one is the language server: this harness is Python,
Pyright is already in the worker image, and Claude Code has a code-intelligence (LSP) plugin for it in its official
plugin list (`/plugin`, search "pyright"; verify the name there). It gives exact definitions and references with no
graph to keep fresh.

### 1.5 An optional one-hour trial (no hooks, no CLAUDE.md change, nothing sent out)

Only if the owner wants a number for this repository. Exact flags changed across 0.9.x: check `graphify --help`
before the build line.

```bash
# 1. Install, pinned, in its own environment (touches nothing in the repository or ~/.claude)
uv tool install "graphifyy==0.9.120"
graphify --version

# 2. Keep the output out of git without editing .gitignore
cd /home/arun/Desktop/langchain
printf 'graphify-out/\n' >> .git/info/exclude

# 3. Build from code only, no model back end (expect seconds, "Token cost: 0 input")
GRAPHIFY_BACKEND=none graphify extract . --code-only      # confirm the sub-command with --help
#    check that .claude/worktrees/, node_modules/ and data/ were skipped (node count in GRAPH_REPORT.md);
#    if not, exclude them the way --help states and rebuild

# 4. Check it answers
graphify explain "src/app/analysis/project_graph.py::neighbourhood"
graphify query "where is a fixer's request built and what does it hold"

# 5. Measure: five questions of the kind really asked here, each in a fresh session, both ways
claude -p "<question>" --output-format json                # baseline: note usage, num_turns, total_cost_usd
claude -p "Use the graphify CLI (query/explain/path) before reading files. <question>" --output-format json

# 6. Remove
graphify uninstall --purge ; uv tool uninstall graphifyy ; rm -f ~/.cache/graphify-queries.log
```

Keep it only if the graph arm uses at least 20% fewer total tokens at equal correctness on four of the five
questions. Do not run `graphify install`, `graphify claude install`, `graphify hook install` or
`claude mcp add ... api.graphify.com` during the trial.

## 2. Can the harness benefit?

### 2.1 What the harness has today

| Piece | What it does | Limit found |
|---|---|---|
| `analysis/project_graph.py` (CG.1), `.harness/project-graph.json` | per file: imports, imported by, defines, criteria of acceptance tests; rebuilt only when a source file changed | import edges for two families only (`reachability.FAMILIES`: Python; JS/TS/Vue/Svelte). Go, Rust, Java, Kotlin, C#, Ruby, PHP, Swift: definitions by one pattern, no edges. File level: no "who calls this function". |
| `neighbourhood` in fix and work-order requests (CG.2, CG.3; `PROJECT_GRAPH_FIXES`, `PROJECT_GRAPH_BUILDERS`, on) | one hop, at most 1,500 characters | "tested by" needs a test that imports the file: an acceptance suite that calls a service over HTTP imports nothing, so it is empty for every service. `docs/measuring.md`: "no signal" - nobody knows how often it says anything. |
| `code_graph` tool (CG.4, `CODE_GRAPH_TOOL`) | `where_is`, `who_uses` on request | 0 calls in about 3,500 offers; left out by `LEAN_TOOL_LISTS`, so it is offered nowhere. |
| `graph/localised_fix.py` (FX.2, always on) | failing request or stack frame matched to the route's handler, plus the modules it imports, held whole first | routes found by pattern at fix time and not kept in the graph; "modules it imports" empty outside the two families. |
| `analysis/outline.py` (LF.1287), `agents/room_for_reads.py`, `agents/memory_slices.py` | every definition and test with its lines; a read with no room answered by the outline; a fixer's long file held as windows round the failing lines | definitions by pattern and indentation, not by a parser; `SLICED_MEMORY` follows imports "where the code graph knows it" - two families. |
| `agents/code_map.py` (WS.7) | a map of a seeded codebase for the planning stages, size-aware (80 files) | entry points and "most imported" come from the same two-family import graph. |
| `analysis/grammar_parse.py` | tree-sitter grammars (`tree-sitter-language-pack`, already a dependency) used to refuse a file that does not parse | used for syntax only, for six languages. Nothing reads definitions, imports or calls from the trees. |
| `analysis/language_service.py`, `compiler_check.py` | Pyright, the TypeScript service, and the compiler for compiled languages, after writes | diagnostics only; no references. |

So the harness has the design graphify's users had to learn the hard way (the harness asks, the model is handed the
answer), and lacks the part graphify does well: a parser-based graph in every language, down to the symbol.

### 2.2 Judgement

**Would a fuller graph cut the re-reading?** Partly, and not the largest part.

- The 17.8 reads a file (suite author, medium run) and the 69% repeat reads in failing fixers came from the request
  being rewritten: reads folded before they were seen (10-15 messages after a summary) and summaries that dropped
  what was read. Those are fixed or being measured (the deep-review fixes, FX.4, `FIXERS_HOLD_WHAT_THEY_READ`). A
  graph does not stop a summary.
- What a graph changes is how much must be read at all. The fixers that were handed their file edited within a few
  calls; those with "Affected files: (none identified)" read 26-34 times and changed nothing. FX.2 now finds the
  handler, but its second hop (what the handler imports and calls) is blind in seven languages, and a five-file
  path of 12,800 tokens is still handed over as whole files when the fixer needs four functions.
- Published effect of the same idea: a repository graph added to existing repair agents raised resolved issues by
  2-2.7 points (RepoGraph, SWE-bench Lite); graph-guided localisation cut localisation cost by 86% at equal accuracy
  in its authors' measurement (LocAgent); Aider's ranked map of definitions is how it fits a repository in a small
  budget. Modest, real, and all harness-driven or prompt-carried, none relying on a weak model choosing a tool.

**For a 35B local model: harness-driven only.** The model called `code_graph` 0 times, the web tools 0 times and
`module_exports` 0 times. Every item below puts the graph's answer in a request or in the reply of a tool the model
already calls (`read_file`, `grep`, a write). No new tool.

**Small and large products (owner rule, 10-23).** A ten-file product fits in memory whole; there the graph adds a few
lines and should stay out of the way. Each consumer below switches on by measured size (the product against the
stage's room), as `room_for_reads` already does.

**Not graphify as a dependency.** It pins tree-sitter 0.25 and about 30 grammar wheels beside the language pack the
worker has; its value beyond parsing (clustering, "god nodes", the HTML view, model-written labels, the hooks) is
for a person or a strong model exploring, not for this pipeline; and its edges would still need mapping to routes,
criteria and the locked suite, which only the harness knows.

### 2.3 Plan: KG.1-KG.10

Order: KG.1 first (a day, tells us the size of the gap), then KG.2-KG.4 as one bundle (the graph itself, always on
because it only fills answers that are empty today), then the consumers one measuring pair each.

| Item | What | Where | Size | On / switch | Measured by |
|---|---|---|---|---|---|
| **KG.1** | **Say what the graph says today.** One record per request that carried a neighbourhood or a localisation: how many files, edges and tests it named, by language; and how each fixer was localised (`route`, `trace`, `asked`, none). A firing signal for `PROJECT_GRAPH_FIXES`/`BUILDERS` in `switch_firing.SIGNALS`. | `analysis/project_graph.py`, `observability/switch_firing.py`, `scripts/loop/effects.py` | S | on (a record, no behaviour) | `loop.sh measuring` shows a count instead of "no signal"; the share of fix requests with an empty neighbourhood per family (expected: near 100% for Go, Java, Rust, Ruby, PHP, C#) |
| **KG.2** | **Definitions and imports from the parser, in every language of the table.** Read each source file's tree with the bundled grammar: every definition with its kind, name, first and last line, and enclosing definition; every import statement. Resolve an import to a project file through one resolver per language kept as a column of `app.stacks.languages` (Go: module path and package folder; Java, Kotlin, C#: declared package or namespace; Rust: `mod` and `use crate::`; Ruby: `require_relative`; PHP: `use` with the manifest's autoload map). The pattern stays as the fallback where no grammar loads. A tree with error nodes is still read (a grammar that mis-reads 1% of valid C# is unfit to refuse a write, which is why `grammar_parse` leaves it out, but fit to list definitions). | `analysis/project_graph.py`, a new `analysis/parsed_definitions.py`, `stacks/languages.py`; `outline.py` and `reachability.FAMILIES` read from it | M-L | on: fills empty answers in what is already built (FX.2's imports, `SLICED_MEMORY`, the outline, unreachable-code detection in seven more languages) | KG.1's empty share falls to the files that truly import nothing; a fixture project per language whose known edges are asserted; build time on a 2,000-file codebase under 5 s, cached by file time and size as now |
| **KG.3** | **References by name.** For each identifier used in a file that exactly one other project file defines, an edge "uses `name` of `file`" (the way Aider builds its map: definitions and references from the trees, no type resolution). A name defined in several files gives an edge marked ambiguous and is never stated as fact. Gives "what calls this function" and "what does this function call" per definition. | `analysis/project_graph.py` (schema: nodes gain `uses`, `used_by` keyed by name) | M | on (data only; shown through KG.5-KG.8) | precision on the fixture projects (target: no wrong unambiguous edge); graph size stays under 1 MB on a medium product |
| **KG.4** | **Routes, tests and criteria as part of the graph.** A route (method and path) points at the definition that handles it (`product_interface.declares_a_route`, moved from fix time to graph build time). An acceptance test points at the routes it requests and so at their handlers and criteria; a unit test at the definitions it references (KG.3). `localised_fix` reads the graph instead of scanning; "tested by" is true for services. For a page product, the same from a test's selectors to the component file that renders them, where the text matches exactly. | `analysis/project_graph.py`, `graph/localised_fix.py`, `acceptance/product_interface.py` | M | on (FX.2 is always on; this is its data) | share of fixers localised by `route` or `trace` rather than `asked` or none; "tested by" non-empty on the service families; calls before a fixer's first edit |
| **KG.5** | **Hand over definitions, not files, when the files do not fit.** Where the localised files are larger than the fixer's room, the request holds: the handler's definition whole, each definition it calls (one hop, KG.3) whole while room lasts, and the outline of the rest with line ranges. Where they fit, whole files as today. The same for a builder whose work order names files past its room. | `agents/memory_slices.py`, `agents/project_memory.py`, `graph/localised_fix.py` | M | switch `DEFINITIONS_BEFORE_FILES` (efficiency; doubtful because a fix may need a line outside the slice) | opening tokens of a fixer, reads and repeat reads per fixer, summaries per fix stage, fix rate at first attempt; hidden score must hold; 2 on / 2 off on a medium brief and one Go or Java family |
| **KG.6** | **The graph answers inside the tools the model already calls.** A `grep` whose pattern is a name the graph defines is answered first with "defined at `file` lines a-b; used in ..." and then the matches. A range read of a definition adds one line: what calls it. A `read_file` of a file with no room is already answered by the outline; that outline gains "used by". No new tool; `CODE_GRAPH_TOOL` stays unoffered. | `agents/workspace_backend.py`, `agents/room_for_reads.py` | S-M | switch `GRAPH_IN_SEARCH_ANSWERS` | calls between a stage's first search and its first write; `redundant_reads.py`; hidden holds |
| **KG.7** | **What a change breaks, said at the write.** When a write removes or renames a definition, or changes its parameters, and KG.3 shows other files using the old form, the write's reply names them (file and line), once. Extends `interface_changes.py` (which tells the next work order) to the author, now. | `tools/repository.py` (the write's reply), `agents/interface_changes.py` | S | switch `USES_NAMED_AT_THE_WRITE` (a note can mislead on an ambiguous name; only unambiguous edges are named) | interface-clash defects at CI and compile errors in the first test round, per run; notes shown against notes followed by an edit of a named file |
| **KG.8** | **A review holds what the change touches.** Code and security review requests hold the changed definitions and, for each, the signatures of what uses it (KG.3), instead of whole changed files plus re-reads (security review: 71% of its input was waste; code review 46%). Changed files that fit are still held whole. | `agents/review_files.py`, `agents/code_reviewer.py`, `agents/security_reviewer.py` | M | switch `REVIEWS_HOLD_THE_CHANGE_AND_ITS_USES` | review input tokens and re-read-only calls; findings confirmed by a later failing test must not fall; false findings must not rise |
| **KG.9** | **The codebase map in every language, ranked by use.** `code_map` takes entry points, test locations and "main modules" from the full graph, and past 80 files ranks modules by how much of the project reaches them (the rank Aider uses), weighted by the names the brief uses. | `agents/code_map.py` | S (after KG.2) | on (the map exists and is always on; today it is wrong outside two families) | a seeded Go and a seeded Java codebase: the map names the true entry point and the modules the change touches; opening listing calls of the planning stages |
| **KG.10** | **Retire the tool that is never called.** Remove `code_graph` from the tool lists and the `CODE_GRAPH_TOOL` switch (or keep it only for a model whose diagnosis measured that it calls optional tools). | `analysis/project_graph.py`, `agents/stage_tools.py`, `switches.py`, `docs/measuring.md` | S | removal | one switch fewer that reads "on" and acts nowhere |

Proof per item, as the rules require: a targeted test that fails on the old code from a real project fixture per
language (a Go handler importing a package, a Java service using a repository class, a Ruby `require_relative`), kept
in the per-language test folders; nothing in the shared code names a language or framework.

Cost: KG.1 and KG.10 under a day each; KG.2-KG.4 about a week as three parallel worktree builds (they meet only in
`project_graph.py`, so KG.2 lands first); KG.5-KG.8 a day or two each, independent of one another.

## 3. Other features

### 3.1 What other harnesses do that this one already has

Checked in the code before proposing anything.

| Practice (who) | Here |
|---|---|
| Localise before repairing (Agentless, AutoCodeRover) | FX.2 `localised_fix`, `LOCALISE_FIRST` |
| A map of definitions in the request (Aider) | `project_memory.map_of`, `outline.py`, `code_map.py` |
| Read by range, outline for a large file (SWE-agent's file viewer) | 400-line windows, `room_for_reads`, `memory_slices` |
| A check at every edit (SWE-agent's linter gate) | parser refusal at the write, Pyright and the TypeScript service, `compiler_check`, `verify_after_write` |
| Old tool results cleared, notes kept (Claude Code context editing, OpenHands condenser) | `observation_folding`, `old_reads_stubbed` (FX.4), work notes, `worked_out` |
| A stable prefix for the prompt cache | `stable_prefix`, `stable_tools`, `stable_memory_order`, the olla session header, the prefix-break KPI |
| Gathering on a cheap model, deciding on a strong one (Claude Code's search sub-agents) | `agents/gathering.py`, the one-call `localisation.asked` |
| Run only the tests that matter | a criterion's tests run on their own, due-only suite runs |
| Mutation testing to find weak tests | `MUTATION_GUIDED_TESTS`, section 6.5 of `docs/PRODUCT.md` |
| Several tool calls in one reply | measured per model (`capabilities.parallel_tool_calls`); the model already sends five reads a reply |
| Long command output kept by reference | `read_command_output`, `tool_result_bound` |

### 3.2 Plan: PF.1-PF.6, by expected effect

| Item | What | Evidence | Where | Size | On / switch | Measured by |
|---|---|---|---|---|---|---|
| **PF.1** | **Measure the slot size against the number of slots (owner's decision; the harness changes nothing on the server).** Two arrangements of the same two servers: four 93K slots (today) and two 182K slots. A measuring pair of the same family and one medium brief on each. | The deep review: 0 stage summaries in 8 small runs on the 182K slot; on 93K a summary every 3-16 calls, 26-71% of input wasted per stage, 130 of 155 suite-author reads repeats. Four slots only help if the halved context does not cost more than the parallelism gains. | owner's server settings; `models/server_profile.py` already reads the slot | S (two run pairs) | owner action, listed in `docs/owner-decisions.md` if agreed | active minutes, input tokens, summaries, hidden score per run, and runs finished per day, both ways |
| **PF.2** | **Two or three candidate fixes at once for a stuck defect, kept by its test.** On a defect's second failed attempt, the harness sends the same lean fix request to up to three fixers on separate branches (different seeds), runs the defect's own criterion and the regression set on each, and keeps the first that passes both; the others are dropped. Only while a model slot is idle. | Agentless and its successors select among sampled patches by tests and beat single-attempt agents at lower cost; here the fix rate at a third serial attempt of one cause is 11% (`docs/improvement-plan.md`), so serial retries are the expensive path. | `graph/nodes/fixes.py`, `tools/version_control.py` | M-L | switch `CANDIDATE_FIXES_WHEN_STUCK` | fix rounds and minutes per defect that failed once; hidden holds; tokens per accepted criterion must not rise more than 5% (the plan's kill rule) |
| **PF.3** | **Tests ordered by what the change reaches.** After a fixer's write, the tests whose route or definitions the changed file serves (KG.4) run first, then the rest only when those pass. Extends the per-criterion run to unit tests and to the regression check. | Test impact analysis is standard in large builds; here every suite run is minutes of wall time inside a fix round. | `graph/first_failure.py`, `acceptance/per_file.py` | S after KG.4 | switch `TESTS_REACHED_FIRST` | seconds from a write to its first failing result; regressions found late must stay 0 |
| **PF.4** | **A scout for the reading stages on a product past its room.** Before the suite author, the test round or the technical lead opens on a product larger than its room, one short call without reasoning is given the stage's ask and the graph's outline and answers with at most eight `file: lines a-b` ranges; those ranges are what the stage's memory holds. The generalisation of `localisation.asked` from fixers to the stages with the most waste (suite author 48%, lead 52%, test round 35%). | Claude Code and Cursor keep search in a separate conversation so its reads never fill the worker's; LocAgent's graph-guided localisation; the owner's rule to generalise what works in one stage. | `graph/localisation.py`, `agents/stage_memory.py` | M | switch `RANGES_CHOSEN_BEFORE_A_READING_STAGE` | re-read-only calls and summaries in those stages; hidden holds; the ranges asked for later that the scout missed |
| **PF.5** | **Lines only failing tests run (where a pack can report coverage).** A pack may declare a coverage command; when it does, the fixer's localisation adds the definitions executed by the failing test and by no passing one. | AutoCodeRover reports a higher resolve rate with this ranking when tests exist. Coverage of a server behind HTTP is awkward in several stacks. | pack field in `plugins/`, `graph/localised_fix.py` | L | switch; **park** until KG.4's route-to-handler share is measured: unpark if more than a fifth of fixers are still not localised | fixers localised to the right definition; calls before the first edit |
| **PF.6** | **A language-server plugin for the owner's own Claude Code sessions on this repository** (not the harness): exact go-to-definition and references on 200,000 lines of Python in place of repeated searches. | Section 1.4. | Claude Code `/plugin` | S | owner's choice | the same five-question measurement as 1.5 |

## 4. What not to do

- **Do not install graphify always-on** (hooks, CLAUDE.md section, git hooks) in this repository, and do not add the
  hosted MCP server: unproven for session work, and it changes every agent session that runs here.
- **Do not add graphify, or any graph server, to the worker as a tool for the model.** The local model does not call
  optional tools; the existing `code_graph` tool proved it. The harness asks; the model is handed the answer.
- **No embedding or vector search, no zoekt or Sourcegraph index.** The products built are tens to a few hundred
  files; exact search and a parsed graph cover them, and an embedding model would take GPU memory from the owner's
  model. Claude Code and Aider both work without one.
- **No language server per stack inside the worker for references** (the Serena approach). Nine servers to install,
  start and keep alive per run; name-based references from the trees give most of it for no new dependency. Keep
  the compiler and the two services for diagnostics, as now.
- **No model-written graph content** (labels, summaries, "inferred" edges). The graph is computed from the files and
  is never wrong about what it states; an ambiguous edge is marked and not shown as fact.
- **No structural-rewrite tool (ast-grep) offered to the model.** One more tool it would not call; KG.7 tells it what
  a rename breaks, and the edit tool it uses already takes twelve changes a call.
- **Do not expect the graph to replace the context fixes.** The fold fault, the work note and FX.4 decide the
  re-reading; KG.5 and KG.8 are measured after them, on the same slot size, or their effect cannot be told apart.
- **Do not show the graph to a product that fits in memory.** Size-switched, like `room_for_reads`.
- Already rejected in `docs/improvement-plan.md` section 6 and not proposed again here: an edit-format change, tool
  masking as a loop stopper, compaction that breaks the prefix cache, letting the model decide when to search.

## 5. Not verified

- The exact hook matchers and JSON that `graphify claude install` writes, and how it excludes folders (no
  `.graphifyignore` documentation was found): read `graphify --help` and the written files before any standing use.
- The headless build sub-command and flags for 0.9.120 (`graphify extract . --code-only` is from the README's
  wording, not from a run).
- The advisory's affected and fixed versions.
- The star count and issue counts are as GitHub showed them on 11-26; one review title in search results said 88k
  stars and "YC S26", which I could not open.
- The Claude Code Pyright plugin's exact name.
- All figures from RepoGraph, LocAgent, Agentless and AutoCodeRover are their authors' own, on SWE-bench subsets with
  hosted models; none was measured on a 35B local model.

## Sources

- Graphify repository: https://github.com/Graphify-Labs/graphify (also https://github.com/safishamsi/graphify)
- PyPI record: https://pypi.org/project/graphifyy/
- Claude Code integration page: https://graphify.com/integrations/claude-code
- Issue 985, "Graphify vs Claude Code AI agent": https://github.com/Graphify-Labs/graphify/issues/985
- Benchmark reproduction guide: https://pantheon-org.github.io/agentic-context/benchmarks/graphify/
- "I tested graphify on a real Python repo": https://hackernoon.com/i-tested-graphify-on-a-real-python-repo-heres-what-happened
- "I installed a knowledge graph on Claude Code; 14 days later the audit killed my enthusiasm":
  https://dev.to/rentierdigital/i-installed-a-knowledge-graph-on-claude-code-14-days-later-the-audit-killed-my-enthusiasm-1p1n
- Advisory list: https://advisories.gitlab.com/pkg/pypi/graphifyy/
- CodeGraph on Hono: https://dev.to/harrisonsec/i-tested-codegraph-on-hono-the-tool-call-savings-reproduce-the-cost-savings-dont-389p
- RepoGraph: https://arxiv.org/pdf/2410.14684
- LocAgent: https://arxiv.org/abs/2503.09089
- Scaffold taxonomy (Aider's ranked map, Agentless's localisation): https://arxiv.org/pdf/2604.03515
- SWE-bench leaderboard architectures: https://arxiv.org/pdf/2506.17208
