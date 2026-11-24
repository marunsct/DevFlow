# Agents that work like a team: using outside knowledge the way people in each role do

Date: 2026-11-24 (JST). Kind: research and plan. Read-only on the code; nothing was changed, run or deployed.
The run measurements quoted from today come from the main session's audit (given in the brief); they were not
re-counted here. Web sources are linked in section 3; where a figure comes from a secondary or vendor page it says so.

## (a) The short answer

1. **A person in a team does not "have a search tool". They have routines.** Before choosing a library they check
   what is current and whether it fits their toolchain. Before writing against an unfamiliar release they read that
   release's documentation. When stuck they search the exact error, read the maintainer's answer, check it fits
   their version, and try it. Before release they check advisories. The knowledge arrives at fixed points of the
   work, in a known order of trust.
2. **The harness should run those routines itself and hand each role a short, checked note.** That is the pattern
   that already works here (the registry versions before a manifest, the architect's reading done first, a Rust
   import answered from the crate's own source). Offering tools and waiting for the model to call them does not work
   on the local model (zero calls in 24 runs) and, by the published evidence, works only modestly even on frontier
   models while they are coding.
3. **Most "training data against the real ecosystem" failures are not search problems.** They are fit problems the
   registry, the toolchain and the installed package can answer exactly: which release this toolchain builds, which
   name the installed package really exports, which release is deprecated, end of life or has an advisory. The Rust
   0/9 (rustc 1.85 against crates needing 1.86-1.88) was settled by a resolver setting, not by a search. So the order
   is: local truth first, registries second, version-pinned official documentation third, the issue tracker fourth,
   question-and-answer sites fifth, the general web last.
4. **A found answer is a hypothesis until it is tried.** The stuck lookup today hands three raw leads to the fixer;
   2 of 9 such defects were fixed afterwards. People read the resolution (not the question), check the version, and
   test. The harness should do the same: condense to one note (cause, fix, versions it applies to, source), check the
   versions against the project, and record whether the next fix closed the defect.
5. **Build first:** a standing sheet of stack facts with a toolchain-fit check, and a rebuilt stuck lookup with
   outcome measurement (section (e)). Production needs one outbound gate and one shared lookup service; both are
   designed below and the first bundle does not block on them.

## (b) What the harness does today, role by role, against how a person in that role works

Legend for the last column: **gap** = nothing does it; **partial** = done at one point or for some stacks.

| Role | How a person works | What the harness does today (cited) | Gap |
|---|---|---|---|
| Product manager | Looks at comparable products, what users expect of the category, constraints (regulation, accessibility). | Read-only role, workspace readers only; no outside knowledge at all (`docs/PRODUCT.md` 3.2; `src/app/agents/product_manager.py`). | **Gap.** Deliberately low priority: the hidden tests score the brief, and market input risks scope growth. |
| Consultants (UI/UX, database, backend, security, testing) | Current practice guides, the framework's own recommendations for the version in use. | Read-only advisors with no lookups (`docs/PRODUCT.md` 3.2, 3.3). | **Gap.** They advise from training data only. |
| Stack selector | Compares candidates on maturity, documentation, licence, maintenance, security, fit with the toolchain. | Offered `look_up_package`, `read_docs`, web tools, MCP (`src/app/agents/stack_selector.py:165`) - all model-chosen. Nothing is put in front of it. | **Partial.** Depends on the model asking. No end-of-life, advisory or maintenance facts exist anywhere. |
| Principal architect | Reads current docs, release notes, deprecations and advisories for the chosen libraries before specifying. | The harness reads first: registry releases of each library and up to 10 documentation topics, then withholds the lookup tools (`src/app/agents/research_brief.py:129-165`, called from `src/app/graph/nodes/specification.py:95-145`). | **Partial, and the best pattern in the codebase.** The docs read are the latest (`llms.txt` or the registry README, `src/app/tools/docs.py:1-23`), not pinned to the release chosen; no changelog, deprecation, end-of-life or advisory input. |
| Design review | Checks choices against known pitfalls and advisories. | Read-only (`docs/PRODUCT.md` 3.2). | **Gap.** |
| Scrum master, technical lead | Rarely need outside knowledge. | Read-only. | None needed. |
| QA author and QA lead | Current test tooling for the stack; the runner's own docs. | The pack owns runner configuration (`docs/PRODUCT.md` 3.4); QA as a specialist is offered docs and registry tools. | Small. Pack currency is a maintainer routine: `scripts/loop/pack_freshness.py` reports pins a major behind, nightly. |
| Builders (specialists) | Official docs for the installed release, the package's own types, the migration guide when an API has moved. | Tools offered: `look_up_package`, `module_exports`, `read_docs`, web tools, MCP (`src/app/agents/specialists.py:1509-1511`). Harness-driven: registry releases before a manifest is drafted (T4, `src/app/graph/registry_versions.py:1-13`, `src/app/graph/drafting.py:302`); pack guidance and known errors. | **Partial.** Versions are handled; API knowledge for the installed release is left to the model's choice to ask. |
| Fixers | Search the exact error with library and version; read the issue's resolution; check it fits; try it. | Harness-driven T1/T2/T3 (`src/app/graph/stuck_lookup.py:1-18`, `src/app/graph/nodes/fixes.py:272`, setup at `src/app/graph/acceptance_nodes.py:468`), sources in `src/app/tools/lookups.py:289-298`; web tools after two failed fixes (`src/app/graph/web_tools_after_two_failed_fixes.py`, `fixes.py:522,911`); a Rust import answered from the crate's source (`src/app/analysis/rust_crate_exports.py`). | **Partial, low yield** (2 of 9 fixed after a lookup). Specific weaknesses below. |
| Code, advice, milestone reviewers | Best-practice guides for the framework version. | Read-only. | **Gap**, low priority. |
| Security reviewer | CVE and advisory databases for the exact dependency versions. | Read-only; no advisory data. `RELEASE_AUDITS` only adds the ecosystem's audit command to the generated CI, because the sandbox has no network outside installs (`src/app/stacks/release_audits.py:1-20`). The private search keeps an NVD engine (`docker/searxng/settings.yml`) that no step asks. | **Gap.** The harness never sees an advisory for what it ships. |
| Release | Checks the runtime and dependencies are supported. | Probes and audits of the product; no end-of-life or advisory check. | **Gap.** |

Specific weaknesses in what exists (each is a line of code, not an opinion):

- **One long query.** A lookup sends one string of up to 160 characters: cleaned error plus stack words
  (`lookups.py:53`, `lookups.py:410`). Stack Exchange's search and GitHub's issue search both answer short queries
  far better than long ones.
- **GitHub issues are searched across all of GitHub and ordered by comment count** (`lookups.py:178-179`), not within
  the library's own repository and not by relevance. The registry lookup already returns the package's home
  (`package_registry.py:86`, `_homes`), so the repository is known.
- **The excerpt is the question, not the answer.** For an issue the excerpt is the issue's body - the reporter's
  description (`lookups.py:188`) - cut to 600 characters (`lookups.py:49`). The resolution lives in the closing
  comment, the linked pull request or "fixed in x.y".
- **No version check.** Nothing compares the versions a lead talks about with the versions the project runs. The note
  tells the model to check (`lookups.py:56-57`); the model does not.
- **Stack Overflow is asked first** (`lookups.py:290`). Its question volume has collapsed (section 3), so errors from
  releases of the last two years are mostly not there.
- **Registry fit is done for two ecosystems only.** The newest release this toolchain builds is worked out for crates
  and NuGet (`package_registry.py:160-187`, `305-325`); npm reads `/latest` alone (`package_registry.py:112-124`) and
  PyPI the newest version alone (`127-141`). No reader reports a deprecated or yanked release other than crates.
- **Model-chosen searches leave uncleaned.** `search_the_web` sends the model's query as written
  (`web_search.py:182-203`); only the harness's own lookups pass through `cleaned` (`lookups.py:94-107`). The private
  words removed are the folder name and the contract's project and title (`stuck_lookup.py:143-153`) - not the
  product's own nouns from the brief.
- **Process-local and unlocked state.** One lookup per error per run is kept in a module dictionary
  (`stuck_lookup.py:43`, and `registry_versions.py` `_SHOWN`), lost on a worker restart and not shared between
  workers. The daily counter is read, changed and written with no lock (`lookups.py:332-339`), so concurrent runs
  under-count against a source's cap. The cache is one file per query under `DATA_DIR/lookups`
  (`lookups.py:379-401`), with no entry for "nothing found" (`lookups.py:443`), so an empty search is repeated.
- **Offering costs and does not pay.** The web tools are offered again to every documentation-reading stage
  (`stage_tools.py:84-88` re-adds them when `WEB_TOOLS_OFFERED` is on), about 3,300 characters of schema for five
  seldom-called tools on every request (`stage_tools.py:3-7`), for zero calls.

## (c) Research findings, with sources

### 1. How engineering teams use outside knowledge, and how they pick the best answer

- **What developers search for.** Studies of search logs find the commonest tasks are learning an unfamiliar term,
  explaining an exception or error message, finding reusable code, fixing a common bug and finding a library
  ([Xia et al., "What do developers search for on the web?"](https://link.springer.com/10.1007/s10664-017-9514-4)).
  A Bing study covered about a million exception queries ([arXiv 2006.00385](https://arxiv.org/abs/2006.00385)).
  Queries are usually the error text verbatim or a short description of the problem; searching from wrong output
  without a hypothesis often returns irrelevant results
  ([Michigan study of debugging with Stack Overflow](https://websites.umich.edu/~endremad/papers/SODebug2022.pdf)).
- **How libraries are chosen.** In a survey of 115 developers the factors most often rated high-influence were
  maturity and stability (62%), usability (55%), documentation (51%), licence (45%), active maintenance (44%),
  security (39%), cost of ownership (39%); popularity only 30% and release frequency 3%
  ([Larios-Vargas et al., FSE 2020](https://arxiv.org/abs/2005.12574)). These are facts a registry, a repository and
  an advisory database publish.
- **Accepted is not the same as current.** Of obsolete Stack Overflow answers, 58.4% were already obsolete when
  posted and only about a fifth were ever updated; 44.1% of them were the accepted answer
  ([Zhang et al., TSE](https://arxiv.org/abs/1903.12282)). An accepted answer needs its date and version read.
- **Stack Overflow is drying up.** Monthly questions fell from about 200,000 at the peak to 3,862 in December 2025
  ([DevClass](https://devclass.com/ai-ml/2026/01/05/dramatic-drop-in-stack-overflow-questions-as-devs-look-elsewhere-for-help/4079575),
  [Techzine](https://www.techzine.eu/news/devops/137686/stack-overflow-in-freefall-78-percent-drop-in-number-of-questions);
  secondary reports). Errors introduced by recent releases are answered in the project's issue tracker, release
  notes and migration guide, not there.
- **The signals people use**, in order: the project's own source (docs, release notes, a maintainer's reply), a match
  with the version in use, recency, then votes or reactions. This is the ranking the plan adopts.

### 2. State of the art in coding systems that use outside knowledge

- **Stale knowledge is measured and large.** On Rust API changes, models scored 56.1% on APIs from before their
  cutoff and 32.5% after; retrieval of the API's documentation raised post-cutoff success from 34.9% to 48.4%, and
  the exact API information to 57.7%. Behavioural changes that keep the signature were hardest (38%)
  ([RustEvo2](https://arxiv.org/abs/2503.16922)). Models reproduce deprecated calls because training data holds
  them and nothing at inference says they are deprecated
  ([Wang et al., ICSE](https://arxiv.org/abs/2406.09834)). Version-conditioned Python tasks sit at 48-51% for
  frontier models ([GitChameleon 2.0](https://arxiv.org/abs/2507.12367)); see also
  [VersiCode](https://arxiv.org/abs/2406.07411).
- **The right documents beat a search tool; running the code beats both.** In GitChameleon 2.0, retrieval of three
  relevant documents added up to 10 points (GPT-4.1 48.5% to 58.5%), agents given a web search tool landed at 46-55%
  depending on engine, a sandbox to run code raised every configuration, and self-debugging added 10-20 points. The
  lesson for this harness: execution feedback and exact local facts first, targeted documents second, open search
  last.
- **Models pick stale and unsafe versions systematically.** Across 10 models, 36.7-55.7% of tasks with pinned
  versions carried a known CVE, 72-91% of those disclosed before the model's cutoff; static compatibility was
  19.7-63.2%, installs failing most; "externally anchored version constraints" cut both
  ([Correct Code, Vulnerable Dependencies](https://arxiv.org/abs/2605.06279)). This is the paper for T4 and for the
  stack-facts item below.
- **Invented packages.** 19.7% of recommended packages did not exist; open models 21.7% against 5.2% for commercial
  ones; 43% of invented names recurred in all ten repeats; retrieval cut CodeLlama from 26.3% to 13.4%
  ([Spracklen et al., USENIX Security 2025](https://arxiv.org/abs/2406.10279)). A registry check is the cheap answer;
  the harness has one in its dependency gate.
- **Version-pinned documentation services.** Context7 resolves a library, then returns documentation for a version
  written into the library id; if the version is missing it silently returns the nearest or the latest
  ([Context7](https://github.com/upstash/context7),
  [specifying versions](https://www.mintlify.com/upstash/context7/guides/specifying-versions)). No independent
  accuracy measurement was found - vendor claims only. One practitioner comparison found editor documentation
  indexing helped little and rules plus Context7 helped most
  ([VirtusLab](https://virtuslab.com/blog/ai/providing-library-documentation/)). The harness asks Context7 without a
  version (`lookups.py:210-237`).
- **Search by API, not by browser.** OpenHands-Versa uses a search API because browser searches "were frequently
  blocked by CAPTCHAs"; search is about 40% of its tool calls on a research benchmark and far fewer on software
  tasks - even a frontier model seldom searches while coding. Summarised results (Tavily 64.2%) beat raw snippets
  (Brave 57.0%) ([OpenHands-Versa](https://arxiv.org/abs/2506.03011)).
- **Claude Code** separates search (titles and links) from fetch (a page condensed by a small model against a stated
  question), which keeps raw web text out of the main agent
  ([analysis](https://mikhail.io/2025/10/claude-code-web-tools/); third-party). That condensing step is what the
  stuck lookup lacks.
- **Research agents.** Anthropic's multi-agent research system: start with short broad queries and narrow; agents
  default to long specific queries that return little; early agents chose content farms over authoritative sources
  until heuristics were added; each sub-agent needs an objective, an output format, sources and boundaries; cost is
  about 15 times a chat ([Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system)). Open
  designs follow plan, search, read, reflect ([LangChain Open Deep Research](https://www.langchain.com/blog/open-deep-research),
  [survey](https://arxiv.org/abs/2506.18096)).
- **Advisories and lifecycle as data.** OSV has a batch query with no key and no stated rate limit
  ([OSV API](https://google.github.io/osv.dev/post-v1-querybatch), [FAQ](https://google.github.io/osv.dev/faq));
  deps.dev returns licences and advisories per package version ([deps.dev API](https://docs.deps.dev/api/v3/));
  GitHub's advisory endpoint filters by `package@version`
  ([GitHub](https://docs.github.com/en/rest/security-advisories/global-advisories)); endoflife.date publishes
  support cycles per product ([API v1, beta](https://endoflife.date/docs/api/v1/)).

### 3. Why a local model does not call offered tools, and what makes research reliable

- **Calling a search tool requires knowing what you do not know.** Plain prompting does not give reliable
  retrieve-or-not decisions ([RetrievalQA](https://arxiv.org/abs/2402.16457)); judging sufficiency from the model's
  own output is biased toward "I know" ([SeaKR](https://arxiv.org/abs/2406.19215)). A model whose training data holds
  the old API is confident, which is exactly when a lookup is needed.
- **The decoder allows it.** Under `tool_choice: "auto"` a prose or edit reply is always legal; this repository's
  earlier report (`reports/research/Steering stubborn local models.md`) covers the llama.cpp mechanics.
- **Choice among many tools, in a request shaped as "change this file"**, favours the five tools that do 97% of the
  work (`stage_tools.py:3-7`).
- **What works instead:** fixed code paths for predictable steps and model-directed loops only where flexibility is
  needed ([Anthropic, Building effective agents](https://www.anthropic.com/research/building-effective-agents)). In
  practice: (1) the harness decides when; (2) the harness forms the queries from structured evidence (error code,
  library, version); (3) one model call condenses what was found against a stated question into a fixed form; (4) the
  harness checks versions; (5) the next build or test is the judge. A forced research turn (only the search tools
  listed, `tool_choice` required) is the fallback where a query must come from the model.

### 4. Concurrency and production

- **Self-hosted search is not a production general-web source.** General engines block or CAPTCHA private instances,
  with suspensions of 7 to 15 days from a data-centre address
  ([SSD Nodes guide](https://www.ssdnodes.com/learn/fix-searxng-engine-captcha-errors); vendor), which matches what
  was measured here (`web_search.py:52-55`). Keep SearXNG for developer engines; use direct APIs for facts.
- **Paid search, indicative prices** (third-party comparisons, check before relying): Serper about $1 per 1,000,
  Brave about $5, Tavily $5-8, Exa $4-7
  ([comparison](https://parallel.ai/articles/the-honest-2026-comparison-web-search-apis-for-ai-agents.md)). At one
  to five general-web queries a run this is under a cent a run; the cap matters more than the price.
- **Untrusted text.** Instructions planted in READMEs succeeded about 84% of the time in one study, and most reviewed
  defences stopped under half of adaptive attacks
  ([CSA note](https://labs.cloudsecurityalliance.org/research/csa-research-note-readme-instruction-injection-ai-coding-age/),
  [SoK, arXiv 2601.17548](https://arxiv.org/abs/2601.17548)). The structural defence is the one proposed here: raw
  pages never reach the role that can write or run; only a fixed-form note does, and a note can only suggest a change
  the build then judges.

### 5. Measuring that outside knowledge helps

- Hidden tests conditioned on versions ([GitChameleon 2.0](https://arxiv.org/abs/2507.12367)), before-and-after
  cutoff splits ([RustEvo2](https://arxiv.org/abs/2503.16922)), install and dynamic pass rates for chosen versions
  ([PinTrace paper](https://arxiv.org/abs/2605.06279)). Anthropic's advice for a research feature: start with about
  20 real cases, because early effects are large
  ([Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system)).

## (d) The plan, ranked and phased

Principles for every item: the harness runs the research at a fixed point and hands over a note; model-chosen tools
are an extra, offered by the model's measured tier; anything stack-specific is a row in the per-ecosystem readers
(`package_registry.py`), the language table, a pack or `seed.py`; bug and quality fixes on, doubtful items behind a
switch in the "Internet lookups" group and measured; registries and official sources count as package metadata (as
T4 does today), searches follow the run's lookups choice.

### Phase 1 - know the ground, and make stuck lookups answer (the first bundle)

**HK.1 Stack facts: one standing sheet of what is true today.** Rank 1.
- What: at stack setup and after every install, the harness writes `.harness/stack-facts.json`: the toolchain
  versions here; for each dependency the release chosen and why (the newest stable release this toolchain builds),
  its release date, deprecated or yanked, runtime needed, peers; later the advisories (HK.6) and support dates.
  The "newest that fits" rule moves from two ecosystems to every reader, each reading its registry's own field
  (engines, requires-python, required Ruby, PHP requirement, Go directive, target framework, rust-version).
- Roles: stack selector, architect (replaces the registry half of the research brief), builders at a manifest (T4
  reads the sheet), fixers (every fix request names the versions in two lines), security reviewer, release.
- Concurrency and production: registry answers are public and identical for every tenant - shared cache keyed by
  ecosystem and package, one hour for "latest", permanent for a given version's metadata. Privacy: only public
  package names leave; a name that is the product's own or not found in the registry is not asked twice.
- Cost and latency: 10-30 registry requests a run, parallel, a few seconds, no model call.
- Measure: installs failing on a version or runtime mismatch per run (target zero); runs that never build; hidden
  score held. Stop: parked if four families times two runs show no fall in version-caused defects.
- Risk to quality: choosing an older release than a brief asks for - the brief's stated version always wins and the
  sheet says so. Size: M.

**HK.2 Toolchain-fit check after the install resolves.** Rank 2.
- What: read the lock file or resolved set; compare each resolved package's required runtime with the toolchain; a
  mismatch is a stated cause on the first defect, with the release that fits. This is the general form of the Rust
  finding and the NU1202 finding (LF.1248), found in the first minute instead of after rounds.
- Roles: setup, fixers. Stack specifics: how to read each lock file, in the language table.
- Measure: minutes from first install to first green build on Rust, C#, Java and the two no-pack families. Size: S-M.

**HK.3 The stuck lookup rebuilt as a person does it.** Rank 3.
- (a) Local truth before the web: a name the installed package does not have is answered from the package's own
  files in every language (the Rust mechanism, LF.1281, generalised through the language table and
  `package_exports.py`), and the installed package's changelog is searched for the symbol.
- (b) Several short queries from structured evidence instead of one long line: error code plus library; the
  message's stable words; library, major version and symptom. Stop at the first that answers.
- (c) Search where the answer lives: the library's own repository issues (from the registry's home), by relevance,
  closed ones first; then Stack Exchange; then the developer engines. Order chosen by the library's release date:
  a release newer than about two years goes to the tracker first.
- (d) Read the resolution: for an issue, the closing comment, the maintainer's replies and the linked change; for a
  question, the accepted answer with its date.
- (e) Rank as people do: project's own source and maintainer reply, version match, recency, reactions.
- (f) Condense with one build-model call into a fixed form: cause, the change to make, versions it applies to,
  source, and "does not apply to this project" as an allowed answer. Raw leads no longer enter the fixer's request.
- (g) Version check by the harness against the stack facts; a note for another major line is labelled or dropped.
- (h) "Nothing found" is cached for a day and recorded.
- Roles: fixers, setup. Production: issue and answer pages are public; cache by cleaned query, shared. Privacy:
  queries are built from error codes and public library names, which is safer than cleaned free text. Cost: one
  small model call and 3-8 requests per stuck defect, 10-30 seconds, only when stuck.
- Measure: share of looked-up defects closed by the next fix (today 2 of 9); repeated-signature rounds; the replay
  set of HK.4. Stop: if after 20 lookups the share is under 40% and the replay set does not improve, park (g)-(f)
  and keep (a).
- Risk: a confident wrong note steers a fixer. Mitigations: the allowed "does not apply", the version check, and the
  existing revert-on-no-gain machinery. Size: M-L.

**HK.4 Outcome records and a replay set.** Rank 4 (needed to judge the rest).
- What: every note gets an id; the ledger links note, defect and the next fix's result; `loop.sh effects` prints fix
  rate after a note against stuck defects without one. A replay set is built from past runs' stuck defects whose
  eventual fix is known (the Rust crate versions, sqlx macros, NU1202, passlib with bcrypt 5, the invented gem
  version): for each, does the note name the known fix? It runs with recorded answers, no model server needed.
- Size: S-M. No quality risk.

**HK.5 One outbound gate (the part needed now).** Rank 5.
- What: every outward query - including a model's own `search_the_web` and `read_docs` topics - passes one function:
  `cleaned`, plus the product's own nouns taken from the brief and specification (names of the product, its entities
  and routes), plus an outbound record shown on the run page. Size: S. Required before any multi-tenant use.

### Phase 2 - each role gets its routine

**HK.6 Advisories and support dates for what ships.** Rank 6. After install, the resolved names and versions go to
OSV's batch query; runtime support dates from endoflife.date. Findings above a severity bar go to the security
reviewer as evidence and to release as a gap or a fix (bump to the fixed release when the sheet shows one that fits).
Privacy: names and versions of public packages only. Cost: one request. Measure: advisories at release per run
before and after; no hidden test lost. Risk: an upgrade that breaks the build - only auto-apply within the same
major, else report. Size: M.

**HK.7 Documentation for the installed release, where training data is likely stale.** Rank 7. The model's profile
gets a knowledge-cutoff date (part of the model diagnosis). A dependency whose installed major was released after it
is flagged in the stack facts. For flagged libraries only, a builder's request carries a short API card for the
names its work order uses: first from the installed package's own types and source, then from version-pinned
documentation (Context7 with the version in the id, the project's `llms.txt`), plus the migration guide's section
when one exists. Evidence: RustEvo2 (+13.5 points after cutoff), GitChameleon (+10). Cost: a few requests per
flagged library per run, cached by library and version for every tenant. Measure: defects whose cause is an API that
does not exist in the installed release, per run, on trap families (section (e)). Risk: request size - cards are
capped and only for flagged libraries. Behind a switch. Size: L.

**HK.8 Stack selection and architecture on evidence.** Rank 8. The selector and architect receive a table per
candidate: current release and date, last release activity, support end, open advisories, toolchain fit, pack
available. The ADR records the row it relied on. Uses HK.1 and HK.6 data. Measure: stack-caused failures on no-pack
and medium briefs. Size: S once HK.1 and HK.6 exist.

**HK.9 Consultants and reviewers: the framework's own current guidance.** Rank 9. For the chosen framework, the
official security and testing pages for the installed major are read once (as the research brief does) and given to
the security consultant, the testing consultant and the security reviewer. Behind a switch; measured on quality
tests and review findings confirmed by a test. Size: M.

**HK.10 Product research for the product manager.** Rank 10, doubtful, off until measured, and only with the user's
explicit consent per run because the query must describe the product's category. The harness forms two or three
category queries (private nouns removed, shown to the user), reads a handful of comparable products' public feature
pages, and gives the product manager a list of "what users of such products expect". Items enter as assumptions and
could-haves, never as scope (`agents/scope_discipline.py` applies). Hidden tests cannot score this; it is judged by
the end-of-run product review on the medium brief. Risk: scope growth and time. Size: M.

### Phase 3 - strong models and production

**HK.11 Tools by measured tier.** The model diagnosis gains a check: given a job that needs a fact newer than its
cutoff and a search tool, does the model call it? Models that pass get a single `research(question)` tool that runs
the HK.3 pipeline and returns a note (never raw pages). Models that fail get no web tool schemas at all; the "Always"
choice then means "the harness researches at every routine point", not "tools are offered". This removes the
schemas the local model never uses. Size: M.

**HK.12 A lookup service fit for many runs and tenants.**
- One module in front of every source, with: a shared cache in the database (not files) keyed by source and
  normalised query or `ecosystem/package@version`; single-flight so ten runs asking for one package make one request;
  per-source token buckets with atomic counters (replacing `lookups.py:332-339`); per-tenant daily budgets; a
  circuit breaker per source; once-per-run records kept in the run's own state (replacing the module dictionaries).
- What is safe to share between tenants: answers to queries that contain only public identifiers - package names,
  versions, error codes, cleaned error text. Never shared: which tenant asked, anything from product research
  (HK.10), anything a tenant's "Off" choice forbids. Lifetimes: version metadata permanent, "latest" one hour,
  advisories six hours, error notes seven days, "nothing found" one day.
- Sources under load: registries, OSV, deps.dev, GitHub (token, 30 searches a minute) and Stack Exchange (key,
  10,000 a day) as primaries; SearXNG for developer engines; one paid search key as the general-web fallback with a
  hard daily cap. Keys per deployment, and optionally per tenant for their own quota.
- Determinism for measuring: each run keeps its notes in `.harness/research/`; a Measure batch can run against a
  frozen snapshot of the cache (`LOOKUPS_FROZEN=<date>`), so both arms of a pair read identical answers and a rerun
  reproduces. Size: L.

## (e) What to build first, and how to measure it

**The bundle: HK.1, HK.2, HK.3, HK.4 and HK.5.** One subsystem ("what is true outside, checked"), shipped at a run
boundary. HK.1, HK.2, HK.4 and HK.5 are fixes and always on; HK.3's condensing call and version labelling sit behind
one switch in the Internet lookups group so they can be compared.

Order of work and proof:

1. **HK.4's replay set first, with no model runs.** Collect 15-25 past stuck defects with a known fix. Score the
   present lookup against it (the baseline), then each HK.3 step. Target: the note names the known fix in at least
   60% of cases where the fix is public knowledge; today's baseline is expected near the live 2 of 9.
2. **Pairs on one frozen SHA** (`SWITCHES_OFF=<the HK.3 switch> loop.sh bench <family>`, two runs per arm):
   `notes-api-rust`, `notes-api-csharp`, `notes-api-java` (toolchains with fit problems), `notes-api-hono` and
   `notes-api-falcon` (no pack: the model's own knowledge decides), `fullstack-bookmarks`. KPIs from the ledger:
   hidden and quality scores; runs that never build; install failures by cause; rounds repeating one error
   signature; share of looked-up defects closed by the next fix; active minutes. Off-rule as the plan states: a
   lost hidden test or 1.5 times the family's minutes turns the switch off.
3. **A stale-knowledge trap family (owner decision, as it adds a scored benchmark).** The same nine `notes-api`
   hidden tests, with a brief that asks for a framework whose current major line was released after the model's
   cutoff and changed its API, and a second variant on a toolchain one release behind the ecosystem's newest
   packages. Which framework is data in `bench.json`, refreshed when the model changes; the harness code stays
   stack-agnostic. This is the only benchmark where outside knowledge can move the hidden score, since the present
   families all already score full marks.
4. **The medium brief (`tests/brief_medium.md`: FastAPI or Express, React or Vue, PostgreSQL, JWT, Docker).** One
   thorough run on the bundle against run-c53e7bd2 as the baseline. Count, from the ledger: defects whose cause is a
   version or an API that the installed release does not have; install and build failures before the first green
   build; minutes to that build; stuck lookups made and closed; and (once HK.6 exists) advisories in the shipped
   lock file. The medium brief has many more dependencies than a benchmark family, so the stack facts and the fit
   check should show there first.

Stop rule for the bundle: kept if any of - never-built runs, version-caused defects per run, or the closed-after-
lookup share - improves across the pairs with no hidden test lost; otherwise HK.3's switch goes off and HK.1/HK.2
stay as fixes (they send nothing new outside and cost seconds).

Rough size of the bundle: HK.1 M, HK.2 S-M, HK.3 M-L, HK.4 S-M, HK.5 S - about one bundle of four parallel builds
(HK.3 split in two), each with its fail-on-old tests.

## Open points for the owner

1. A new scored benchmark family for stale knowledge (section (e) item 3).
2. Whether "Always" should stop offering web tool schemas to a model measured never to call them (HK.11), keeping
   harness-run research on.
3. Product research for the product manager (HK.10): wanted at all, given it needs consent and cannot be scored by
   hidden tests.
4. A paid search key for production's general-web fallback (HK.12); the free and official sources carry phase 1.
