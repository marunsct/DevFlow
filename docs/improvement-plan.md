# Improvement plan (open work only)

## 1. How to use this file
- Finished work (every LF fix, every built appendix, the older plans and reviews) is in the archive; `docs/ARCHIVE.md` lists it. This file holds only what is open.
- Read section 2 before any audit (what to check on live runs), section 3 to pick the next build, sections 4-6 before proposing anything new.
- Any change to a switch, a verdict or an item's state is made here in the same commit. Times are JST. "unverified" means the code did not settle it.

**Rules that apply to every row**
- Bug and quality fixes are always on, no switch. Only optional, non-quality changes get a switch, and each is measured.
- Off-rule for any switch (owner 11-17): a run it fires in loses a hidden test, or takes 1.5x its family's 5-run active minutes. Then that switch (or its group, when firing is not recorded) goes off and the family's next run verifies.
- An arm is two runs per family on one harness SHA (`SWITCHES_OFF="NAME" loop.sh bench <family>`, then `kpi_ledger.py switch-arms`). Mixed-version runs count for neither arm. Frozen-version measuring (owner 11-18): bundles ship at run boundaries.
- Before removing a tool or switch as "unused", probe its answers and a sample of runs where the need arose (WL.0 lesson).

## 2. Being measured now
Source of truth: `src/app/switches.py` (defaults and `EXPERIMENTS_ON`) and `loop.sh measuring` (counts over 412 scored runs). In code every grouped switch defaults off and `EXPERIMENTS_ON` turns all of them on except BATCH_ACCEPTANCE_AUTHOR and WEB_LOOKUP_WHEN_STUCK. The Switches line in the old STATE saying several groups are off disagrees with the code: unverified against the live deployment, check `loop.sh switches`.

**Cross-cutting gap (to fix first, S):** 51 of 58 switches leave no text `observability/switch_firing.SIGNALS` can read, so "never acted" and "acted, changed nothing" look the same. Add one firing signature per switch, on-by-default first. Proof: `loop.sh measuring` shows a number, not "no signal", in the Fired column.

### Efficiency group (on)
| Switch | What it does | Keep when | Standing |
|---|---|---|---|
| NEAR_GREEN_REPLANNED_ONCE | a near-green sprint (1-2 failing or 90% passing) is re-planned once, not again | no hidden loss in runs it fires in | fired 2 of 22 on-runs; hidden 0.90 on / 0.60 off, minutes 108 / 138. But Rust container 3 lost the hidden test of the criterion it left open: by its own rule it should go off; the default needs the owner's go-ahead (section 4) |
| REVIEWS_WITHOUT_REASONING | acceptance review answers without reasoning first (68-74% of output was reasoning) | hidden and false-acceptance rate not worse; minutes lower | register says hidden 0.81 on (24 runs) / 0.98 off (146), minutes 88 / 88: a hidden-score drop with no time gain. Re-examine now; likely turn off. Earlier pairs on wordstats-cli: 1 false acceptance in 4 on, 1 in 4 off |
| EQUIVALENT_MUTANTS_REMEMBERED | a mutant judged equivalent is not re-raised | fewer mutation-finding calls, mutation score not lower | no firing signal; needs 1 off run |
| MUTANT_CHECK_IN_THE_FIX_STAGE | the fix stage checks the mutant itself | model calls on mutation defects fall | fired 4; needs 1 off run |
| HARNESS_FINDINGS_RECHECKED | harness-raised findings are re-checked before a fixer is sent | fewer wasted fix stages | no signal; needs 1 off run |
| STABLE_MEMORY_ORDER | project memory in a fixed order | cache share up | fired 17; needs 1 off run |
| NEAR_GREEN_REPAIR_TO_ROUND | a suite repair leaving the suite near green goes back to the round | fewer extra re-plans (about 25 min each) | fired 0; needs a firing run |
| FIX_STAGES_THAT_CLOSE_NOTHING | stops fix stages that have closed nothing | fix rounds fall | fired 2 |
| ONE_DESIGN_REVIEW | one design review plus deterministic gates (contradictions only) | fewer design escalations | fired 0 |
| SPRINT_TIME_BUDGET | a time budget per sprint | active minutes fall, no hidden loss | fired 0 |

### Context and cost group
| Switch | What it does | Keep when | Standing |
|---|---|---|---|
| OBSERVATION_FOLDING | old long tool results folded | input tokens fall, no loss | on; no signal |
| STABLE_STAGE_PREFIX | the stage's opening bytes stay constant (cache) | uncached tokens per call fall | on; no signal |
| REASONING_KEPT_AFTER_AN_ANSWER | carried reasoning kept across an answer | uncached input per call, cache share | on; no signal |
| LEAN_TOOL_LISTS | tools almost never called are not offered | no loss | on; never fired |
| SLICED_MEMORY | fixers/builders get the memory slice they need (164k / 269k characters a request today) | request size falls, fix rate holds | on; never fired |
| LEAN_PROMPTS_FOR_STRONG_MODELS | shorter prompts for a model the diagnosis measured strong | acts only for strong models; needs a hosted-model run | on; never fired (local models are not "strong") |
| BATCH_ACCEPTANCE_AUTHOR | the acceptance author writes in batches of criteria | the whole suite is written | OFF. Refuted for one model earlier; fixed (a batch writer's blockers count only for its batch); back on after one run of a family shows a whole suite |

### Gates, probes, setup
| Switch | What it does | Keep when | Standing |
|---|---|---|---|
| SETUP_SCOPE_GUARD | a layered setup stage writes only framework files, declaration, smoke tests, manifests, test config | setup lines and minutes fall, custom-stack hidden score holds | on; needs 2 notes-api-falcon runs on one SHA |
| MILESTONE_EVIDENCE_GATE | milestone send-back only with a failing test, criterion or underline behind it | send-backs and minutes fall, hidden holds | on; no signal |
| DESIGN_REVISION_CROSS_CHECKED | a design revision is cross-checked | fewer design escalations | fired 19 of 19 |
| INTAKE_ASKS_FIRST | intake asks before a brief is over-ridden (all 4 earlier false acceptances traced to this) | false acceptances 0 | never fired |
| CONCURRENT_WRITE_PROBE / WRONG_SHAPE_BODY_PROBE | release probes: concurrent writes; wrong-shape body | defects found that no locked test asks, no false defect | fired 3 / 5 |
| EDGE_PROBE, PAGE_PROBE | edge cases for a service; page probe (markup in a field, console errors, sideways scroll at phone width, reload keeps items) | as above | on; never fired |
| UNIT_TEST_QUARANTINE | a unit test failing beside a green suite is set aside | no red unit tests shipped | on; no signal |
| DRAFTING_IN_WAVES | product files drafted in dependency order, later files shown earlier ones | fewer interface clashes (Rust, shared state) | on; never fired |
| DIAGNOSE_A_RECURRING_CAUSE | one diagnosis call before a third fix of the same cause | fix rate at 3rd attempt up from 11% | on; never fired |
| MUTATION_GAPS_BUNDLED | open mutation findings in one file go to one fixer; each closed only when the harness's check settles it (LF.1163) | calls and minutes on mutation defects fall, mutation score holds | OFF; needs 2 on / 2 off runs with mutation findings |
| CONTESTED_TESTS_CONFIRMED | past the reclassification cap, a disputed locked test is reopened only after the harness confirms its quoted repair (LF.1168) | minutes stuck at N-1 of N criteria fall; no false acceptance | OFF; measure on tasks-api |
| PRODUCT_PREVIEW | WS.4 product preview (LF.1171); left out: websockets, product cookies, internet at start | start success against the delivered-start check, time to first page, zero access without a token | OFF; needs container mode; first a real-Docker trial |
| WEB_TOOLS_AFTER_TWO_FAILED_FIXES | a fixer that failed twice gets web search and the page reader (LF.1172) | calls made; the defect's signature cleared after a call | ON for every run (owner 2026-11-23: web tools always, measured from here; the medium and high briefs are not counted, `switch_register._families`) |
| PULL_REQUEST_DELIVERY | a changed seeded product goes back as a pull request (LF.1175) | PR opens on a seeded run; no write outside its branch | OFF; first a trial against a scratch repository |
| QA_PROMPT_TRIMMED, REVIEWER_SHAPED_PLUGIN_CONTENT, LEAD_REPLAN_REQUEST_SMALLER | smaller prompts for the suite writer, reviewers and a re-planning lead (LF.1182) | author model minutes and reasoning share; input characters per review call; lead cut-offs and minutes per plan; hidden score and false acceptance unchanged | OFF. Three arms on tasks-api (7, 8, 9): all delivered full marks; the QA trim's suite-writer time 52 (repair bugs), 6.6 and 10.5 model min against 9.2 and 10.4 without it - no saving; reviewer shaping no cost seen; lead re-plan effect not separable. Verdict: leave all three off; drop the QA trim |
| (to build) Suite repair: what a reopen sends | review items 8-10: a reopen carries the lock's open problems on the same tests; a send-back after a successful rewrite goes to the rewrite again; QA's "built" decided from the product | minutes the suite is open per run; reopens per run | behind switches, measure on tasks-api |
| FIX_ORDER_CRITERIA_FIRST | failing criteria and release findings fixed before unit-test defects (LF.1201) | minutes to the first fixer of a failing criterion; rounds to green; regressions left open at release must not rise | OFF. Two page arms with it on (fullstack-bookmarks 2: 10 moved ahead, delivered 8/8 in 107 min; web-todo 5: 14 moved ahead, all 29 green in 45 fix minutes, 10/10 hidden) - no cost seen; third arm fullstack-bookmarks-py 1 delivered 8/8, 7/7 in 90 min; all three arms were on :8888 - one arm on :1234 to separate the model, then on |
| (to build) Page probe: an edit to an empty value | web-todo-react 2 lost a quality test (5 of 6) because editing a title to empty was accepted; the page probe adds an item and reloads but never empties a field in an edit control | quality tests on page products: edge-case loss rate | sure fix if the probe can find an edit control by role/name generically; else a switch |
| (to build) Reopen on a finding three product fixes did not clear | web-todo-react 1: an advice finding (a test finds its item by text its action hides) reached the QA lead, the dispute and two fixers, and was not acted on; five hours and four deferred criteria followed | minutes a locked test stays failing after three product fixes; false acceptance; hidden score unchanged | behind a switch; measure on a page run on :1234 |
| SUMMARISE_LATER_WITH_HEADROOM | the conversation is rewritten at 0.95 of the input ceiling, not 0.8 (LF.1203) | model calls and repeat reads per work order; history rewrites per run; hidden and quality unchanged | OFF. Verified live (notes-api-java 6, :1234): the switch is read and the later trigger is in force (one `summarised_later` record, 23:28 UTC), but on this model the reply reservation is 32,000 tokens so the ceiling is 53,775 and the later trigger buys only 8,067 tokens; rewrite rate unchanged (about 0.18 a minute); Java 6 delivered in 94 min against 178 for Java 5 (133 calls against 329), mostly fewer defects, not attributable to the switch. The room is the 32K reply reservation against replies of a few thousand: see the next row |
| REPLY_ROOM_SIZED_PER_ROLE | the room held back for a reply follows the role's measured reply size (LF.1204) | rewrites per run; model calls and repeat reads per work order; replies cut at the cap must not rise | OFF; measure on a Java run on :1234 together with SUMMARISE_LATER_WITH_HEADROOM |
| LONG_REASONING_BEFORE_A_READ | the reply after one that reasoned 8,000+ tokens and then only read goes without thinking, one reply, any stage (LF.1238) | model minutes per stage and per read; replies of 8,000+ reasoning tokens ending in reads only; hidden and quality score unchanged | ON (owner 11-17 rule for built switches); firings counted by `thinking_off_after_a_read` records |
| WEB_TOOLS_OFFERED | web search and the page reader offered to the stages that read docs, set by a run's "Always" lookups choice (LF.1166) | the tools are called and a stuck signature clears; hidden holds | ON for every run (owner 2026-11-23: web tools always, measured from here; the medium and high briefs are not counted, `switch_register._families`) |
| WEB_LOOKUP_WHEN_STUCK | harness looks up a stuck fixer's error (WL.4 T1) | repeated-signature rounds or minutes to green fall, hidden holds | ON for every run (owner 2026-11-23: web tools always, measured from here; the medium and high briefs are not counted, `switch_register._families`) |

### Premium bundles (on; each needs an off arm on today's SHA)
PREMIUM_MODEL_TUNING (guides, reply caps, thinking-off rules), PREMIUM_PROJECT_INTELLIGENCE (shared facts, canonical memory, code graph, lessons, decision ledger), PREMIUM_DEEP_VERIFICATION (mutation-guided tests, regression contract, audits, assumptions gate, screenshot rubric), PREMIUM_CHANGE_REQUESTS. Register: hidden 0.93 on / 0.70 off on only 2 off runs: too thin to park or keep. Verdict needs 2 on / 2 off per bundle, largest token share first. LESSON_DISTILLER fired 235; no member has a signal beyond the 7 that exist. Ledger: `loop.sh effects`.

### Other measurements open
- M11 sampling by mode: on for the Qwen3.6 model on both ports since 11-09; needs on/off pairs (hidden score, malformed tool arguments, replies lost to length).
- M12 redundant reads (restart re-read, in 4 runs): see 3.2.
- Hosted-model arm: see section 4 (waits on the owner's key).

## 3. To build, in priority order
Size S under a day, M a few days, L a week or more. "Proof" is the measurement that keeps it.

### 3.0 The 11-25 review bundle (owner 11-25: organise all review findings, build in parallel)
Sources: `reports/audits/2026-11-25-product-quality-ui-db-api.md` (PQ), `reports/audits/2026-11-25-per-agent-audit.md` (PA),
`reports/research/2026-11-25-preview-and-workspace-ux.md` (UX), the owner's thorough-mode rule (TG) and the specialist
questions (SP, SK). Waves group items by the files they touch, so each wave's builds run in parallel without clashes.
Merged duplicates: PQ.3 is SP.1; PQ.6 and PQ.9 go into SK.2; PQ.11's text path is SP.4; PA.10 and PQ.12 are one item.
| Wave | Items (one worktree build each line) | Always on / switch |
|---|---|---|
| A (building) | TG thorough mode: every blocking/major/critical/high pre-development finding resolved before development, plus the brief-deferral false positive | on |
| A | SP.1 a due adopted item not built is major and gating; SP.2 every adopted item placed in a sprint or declined | on |
| A | SP.3 specialists review their own domain (`SPECIALIST_DOMAIN_REVIEW`); SP.4 page facts for a UI/UX reviewer that cannot see | SP.3 switch, SP.4 on |
| B | PQ.1 every brief requirement and constraint becomes a criterion or a recorded exclusion; PQ.8 interface states as criteria | PQ.1 on, PQ.8 switch |
| B | SK.1 a work order carries its files' domain advice and goes to the role owning the domain; SK.2 short craft checklists by file kind, stack specifics in packs (with PQ.6, PQ.9) | SK.1 on, SK.2 switch |
| B | PQ.10 a quality score per run from the stored product; PQ.2 mechanical schema conformance | on |
| B | PA.8 a stage is asked to fix only files it may write; PA.3 the product builds before the testing work order | on |
| B | PA.2 the summary is the stage's work note; PA.12 later suite writers given the product's interface, not its source (moved up 11-25: one suite-author visit, 118 reads and 3 writes in 30 minutes) | on |
| B | UX.1-UX.8 full-window preview and workspace, own-window routes, preview toolbar, VS Code-style shell with Monaco, search, diff (app and read routes only) | on |
| C | TG.2 the acceptance review's findings and the suite's problems get severities, and in thorough delivery a gating one keeps the suite from locking (today it locks "with these still open" after the round cap); TG.3 a design escalation the person sends back does not count toward the shared `MAX_ESCALATIONS` | on |
| C | PQ.4 review findings survive an escalation; PQ.5 mechanical interface checks; PQ.7 fuller pack stylesheet; PA.6 mechanical plan repairs; PA.7 specification consistency pass; PA.9 advice sized to the brief; PA.11 custom setup from a drafted file; PA.14, PA.16, PA.17 | on (PA.9 switch) |
| D | PA.10/PQ.12 full-stack packs (service + page); PA.4 suite written a file at a time past the room; PA.13 per-role scoreboard; PA.15 unit-test fix side by failure (switch); PA.18 tool lists by measured use (switch); PA.1, PA.5 (measure the existing switches first); UX.9-UX.11 preview fidelity (`PRODUCT_PREVIEW`) | as marked |
| E | UX.12-UX.16 co-development turn-taking for brownfield (`CO_DEVELOPMENT`, off until one supervised brownfield run loses no edit); replaces WS.6 | switch |
Medium 4 (thorough, :1234) starts when waves A and B's run-side items are deployed. Each wave: targeted fail-on-old tests
per item, both suites once after the merge, one deploy at a stage boundary.

### 3.1 Internet lookups (Appendix 10, WL). WL.1, WL.2 and WL.4's trigger T1 are built.
| Item | Value | Size | Needs | Proof | Verified |
|---|---|---|---|---|---|
| WL.7 answer probe for every outside source in `loop.sh ready` (warning, not a block) and in the built-but-silent audit | the search died silently for a month | S | none | probe fails loudly on a blocked source | not built (nothing for searx or the new sources in scripts/loop) |
WL.3-WL.7 are built (LF.1159, LF.1161, LF.1166, LF.1170, LF.1172, LF.1173). Next: one page reader for the agents' tool and the lookups, with the connection held to the checked address (building).

### 3.1a Agents that work like a team: outside knowledge at fixed points of the work (HK, research 2026-11-24, awaiting the owner)
Plan: `reports/research/2026-11-24-agents-that-work-like-a-team.md`. The harness runs a person's routines itself and hands each role a short checked note (the local model called offered web tools 0 times in 24 runs). Phase 1 bundle:
| Item | Value | Size | Needs | Proof | Verified |
|---|---|---|---|---|---|
Built 11-25: HK.1-HK.10 (LF.1291-LF.1305; HK.7, HK.9, HK.10 and the stuck lookup's condensing behind switches, off) and KS.1-KS.7 (LF.1294-1297, LF.1304). Left: HK.11 tools by measured tier, the rest of HK.12, KS.8-KS.9 after numbers. Phases 2-3 (HK.6-HK.12: advisories and end-of-life, version-pinned API cards, stack-selection evidence, current security/testing guidance, product research, tools by measured tier, a production lookup service with shared public cache, single-flight, atomic per-tenant limits) are in the report.

### 3.1b Search without paid keys, as open-source harnesses do (KS, research 2026-11-25; owner: implement)
Plan: `reports/research/2026-11-25-open-source-web-search.md`. Building with HK.3/HK.4: KS.1 official channels per site (Stack Exchange API by id, GitHub REST/raw, registry documents), KS.2 code kept as fenced blocks, KS.3 "refused" told from "nothing found" with stated waits and a breaker per source, KS.4 blocked and duplicate SearXNG engines dropped (LF.1294-1295); KS.6 a probe per engine and source in `loop.sh ready`, KS.7 robots.txt with wildcards (LF.1296-1297). Next: KS.5 shared cache, single-flight, atomic counters (the first slice of HK.12). After numbers: KS.8 browser fallback (switch), KS.9 local documentation tier (switch).

### 3.2 Watch, try and steer a run (Appendix 11, WS). Nothing below is built except the pieces named.
| Item | Value | Size | Needs | Proof | Verified |
|---|---|---|---|---|---|
| WS.6 take over and hand back: replaced by UX.12-UX.16 (section 3.0, wave E) | person edits safely | L | UX.6 | no edit conflicts; locked suites read-only | not built; last |
UI-only steps keep the release-candidate count; WS.4 and WS.6 add a service and are measured.

### 3.3 Backlog from the latest runs (STATE and audits)
| Item | Value | Size | Needs | Proof | Verified |
|---|---|---|---|---|---|
| Restart re-read pattern (M12): switch `ONE_POINTER_ENDS_READING` (group Efficiency, off): a stage visit's first pointer ends reading (`POINTERS_BEFORE_THE_ANSWER` 2 to 1) | redundant reads 24-36% in 4 runs; lead re-plan minutes | S | none | redundant_read_rate and lead-plan minutes fall, hidden holds; 2 on / 2 off per family | open (switch name absent from src) |
| Browser-pack re-render through the filtered view: a DOM fix that a filter hides gave a false acceptance (web-todo, Haiku hybrid) | closes a false-acceptance class on page products | M | none | the page probe or the suite re-renders through each filter; no false acceptance in 3 web-todo runs | open (unverified how: no module found) |
| Rust routing decision: local Rust 0/9 in four runs, Haiku-built 9/9 twice | decide: route Rust to a stronger model, mark it experimental in the supported matrix, or keep local only | S (decision) | hosted key (section 4) | Rust hidden score | open decision |
| Stack-decision check: a database named as one engine "via" another's mode (SQLite via H2) goes back before the specification | a failed Java run (0/9) never started | S | none | no such decision survives design | open |
| A fixer that hits its call limit hands its findings on, so the next fixer or the ceiling does not leave unseen the defect that carried the cause (LF.1147 handled the ceiling case only) | stops cause loss between attempts | S | none | a hit-the-limit fixer's findings appear in the next request | unverified: LF.1145-1147 partly cover it |
| Candidate M8: a one-file rewrite is shown 60-70k characters of memory; try the failure's files and imports (~20k) | about 2 min prefill a run | S | none | rewrite fix rate holds | open |
| Extend SALVAGED_REPLIES_TURN_THINKING_OFF to `technical_lead` and `scrum_master` | at least 50 min per 30 runs | S | none | on/off minutes, plan quality | unverified |
| Per-role audit items still "not built" (11-10): `specification_rulings.verified` rejects a weak quote; QA lead reviews every suite once before the lock; no hand-typed count upstream of a test; write spec part 2 after part 1 with `function_contracts`; run-wide defect budget across cycles | false acceptances, 200-250 min per 30 runs | M each | none | per item, as the audit states | unverified: many may have shipped under LF.8xx-10xx; recheck each against code before building |
| Reasoning-cost review: record `salvage_requests` and `salvage_output_tokens`; count continuation calls in usage | tokens are undercounted | S | none | totals match the server | unverified |

### 3.4 HR2 switched items (harness-review section 10, bundle 8). None of these switch names exist in src; they were planned, each needs own switch and 2+2 arms.
`FIRST_TRY_CANDIDATES` (fix.2, three whole-file rewrites on a first try, targets 63% of fix minutes); `PLANNING_THINK_BOUND` (P.2, 48% of planning minutes); `DESIGN_REVIEW_IN_ONE_CALL` (D.3; ONE_DESIGN_REVIEW partly covers); `SUITE_PASSES_TWICE` (Q.3); `ADVICE_ONE_CALL` (G.6, 6 min a run); G.2 security as spec conformance; `SPEC_SLICES_BY_STAGE` (D.5); `CONTRACT_LIST_PROBE` (Q.8); `STOP_WHEN_OWN_TESTS_PASS` (fix.8); `REVIEW_THE_SUITE_DELTA` (Q.7); `SURRENDER_AFTER_A_FAILED_WRITE` (fix.5); `MUTATION_SURVIVORS_TO_QA` (Q.6b); `PRODUCT_LINT` (PR.6); `SETUP_PROOF_FEEDBACK` (SS.7); G.5 scanner note; D.8; `EDIT_FORMAT_BY_SIZE` (P.9, low); `MEMORY_BY_NEED` (C.2); `CAPS_FROM_THE_DIAGNOSIS` (C.4b); C.5 schema-first; C.1 estimated cache; E.2 stage forks. Size M each. Rule: build only if the measured cost is still present (re-measure first); several may be covered by 11-17/11-18 work. Source: archive `reviews/harness-review.md` section 10.

### 3.5 Deep-review plan (owner 11-18, implement all)
Built: bundles 1-6, waves 1-3 items named in the register (typed defects, fix journal, start first, drafting waves, golden examples per pack, language table, supported matrix at intake, dependency gate). The plan document is outside the repo, so what is left (item 2.8 role ablations one at a time; any wave 3 remainder) is **unverified**. Role ablations keep the owner's features (role injection, parallel/linear toggle, sprint summary, work orders, templates, Sprint Record).

### 3.6 Older plan items marked NOT STARTED, PARTLY or DECISION GATE in the old Appendix M
Checked: none of these has a module in src. Each is a candidate only if a measurement shows its cost.
| Item | What | Size | Trigger to build |
|---|---|---|---|
| PX.1 prefix-break reason per model call | cache_report has `prefix_break` fields; the per-reason split (tools, steering, thinking, clock, memory order, truncation, eviction) is partly there | S | unverified how much remains; finish if cache share is a priority |
| PX.4 `APPEND_ONLY_HISTORY`, PX.7 `SLOT_AFFINITY` / `id_slot`, PX.6 `--cache-reuse` advice | no module or switch in src | M, M, S | uncached tokens a call; PX.8 only on PX.1's eviction share (decision gate) |
| AZ skeleton + slices; BB lead plans in parts; BE one container per run; BI rubric-graded candidates; BD two local tiers + model advice | all P1/P2, none built | M-L | measured long-context cost or a quality ceiling; BI after AY |
| AY bounded fix cycle steps 5-6 | step 5 deferred (memory pointer already answers a re-read), step 6 waits on measurement of 1-4 | S | after the AY switches' measurement |
| AQ repeated-read hypotheses; Pillar 10 code and test index; Pillar 9 context bus | gated on redundant-read measurement (M12) | M | M12 result |
| BH preference applied (model registry and measured edit preference) | registry done, applying the preference waits | S | group 2 measured |
| Part 4 backend enablers: `completed_with_gaps` in payload (field exists in `graph/terminal_state.py`; verify the payload), gate-deadline timestamps and NULL-timeout stall alerting, steering endpoint, per-stage token rollups | UI support | M | with WS |
| WB.1 work-plan module with capacity check | partly built; WB.2 refuted for one model | S | harder benchmark first |
| SP.2a library entry replays on an empty project; SP.6 per-role lessons | filed | S | recurring library failures |
| CM.2 ledger remainder (typed `known_trap`, `requirement`), CM.3-CM.5 | partly built behind DECISION_LEDGER | M | after the PREMIUM_PROJECT_INTELLIGENCE verdict |
| MT.8 per-tenant secrets seam (OpenBao later); SAP.6 SAP MCP and skills policy; OS.7 object-storage docs, OS.8 off-site mirror and lifecycle | proposed, no code | S-M | multi-tenant launch; an SAP customer; backup policy |
| Backing services (archive `plans/backing-services-plan.md`): service-pack catalogue in `stacks/services/`, broker, `net-floor` sidecar, per-run uid (A7), image pre-pull, Valkey swap; `files-api` and `jobs-api` as Measure families | products that need a database or queue of their own | L | after the release candidate (owner 11-10); needs section 4 items 3, 4 |
| Scaffolding SF.2b/2c/3 (harness-run generator, setup budget and rollback, patch on replay) | SF.2b parked on evidence | M | a custom family fails setup again |
| Part 12 refactor track (V), M-bash | by design last / only for models with no tool calling | L | never before the gate holds |

## 4. Waiting on the owner
| Decision or action | What starts it |
|---|---|
| KS.10: a free Stack Exchange key and a no-scope GitHub token on /admin (300 a day to 10,000; 10 searches a minute to 30) | the owner |
| HK research decisions: a stale-knowledge trap benchmark family; whether "Always" stops offering web tool schemas to a model measured never to call them (HK.11); product research for the product manager (HK.10) at all; a paid search key for production's general-web fallback (HK.12) | the owner |
| Set `NEAR_GREEN_REPLANNED_ONCE` off by default (it is on through `EXPERIMENTS_ON`; every measuring run is started with it off per run) | the owner's go-ahead |
| Hosted-model test (owner approved Claude Haiku 5.5, $30, $8 per-run ceiling): enter the Anthropic key and judgement model on the admin Settings page | owner enters the key; then hybrid runs (judgement on Haiku, build local), then full-Haiku, until about $25 is spent. Also decides Rust routing and the strong-model arm of LEAN_PROMPTS_FOR_STRONG_MODELS |
| Free Stack Apps key and a no-scope GitHub token on the admin page; optional Brave key | owner; starts WL.3 testing end to end |
| Rotate the operator login and move it out of tracked `docs/HANDOVER.md` | owner, before the first outside user |
| Cancel the owner's paused run `run-038f45bb`? (decision 2 of 11-10) | owner cancels it or allows the agent to; unverified whether still paused |
| Load a higher-bit Qwen3.6 build on :1234 to match :8888 (`iq4_nl` is loaded; readiness still advises higher) | owner |
| Name the Docker Hub login for the nightly image pre-pull | owner; starts backing-services pre-pull |
| Real scoped cloud credentials (S3, Azure, GCS, identity provider) | owner adds them through Connections when wanted |
| Licence-class opt-ins (SSPL, BUSL, RSAL; MongoDB, Redpanda, Redis 7.4+) are off | owner turns them on from settings when a brief needs one |

## 5. Parked (with the trigger that unparks it)
- Language sweep and release-candidate count: paused until the language rows and golden examples (deep review 1.7, 1.8) are built; both appear built in code (language table, golden examples per pack), so the trigger looks met: confirm and resume (unverified).
- Backing-services phases E-G (broker, socket proxy, `net-floor`, Keycloak/Kafka spikes): after the release candidate, at a run boundary, never during a Measure batch. Docker Desktop is already at 16 GiB.
- Redis to Valkey: after the release candidate; flush queue, swap image and healthcheck, run readiness.
- PX.8 snapshot side-car: on PX.1's measured eviction share.
- Tool masking (C3) and slot save/restore: on measured evictions; today 5 evictions.
- Q5 browser mutants: waits for the PREMIUM_DEEP_VERIFICATION verdict on MUTATION_GUIDED_TESTS.
- LR.44 hosted runs beyond the approved test: only when the owner instructs.
- `net-floor` sidecar with NET_ADMIN: after A8 spike and A7.

## 6. Rejected / not doing (do not propose again)
- Searching through a headless browser: slow, blocked by the same engines; a one-page render is allowed only to read a page the harness already chose (WL.6).
- Letting the model decide when to search (or offering web tools to every stage): measured, the local model called them 0 times in about 3,500 offers; every open-source harness leaves it to the model and it fails here. The harness decides (WL.4).
- Scraping general search pages (Google, Bing, Brave HTML, DuckDuckGo): blocked, CAPTCHA or rate-limited. Official APIs first.
- Capping the suite-review reply at 8,000 tokens: measured, a quarter of verdicts exceed it. The accepted form is a reply cap with salvage.
- Skipping the architect's second design pass when findings are contradictions: measured, only 3 of 9 serious findings were contradictions.
- Skipping a near-green sprint's first re-plan: the first re-plan beat the best attempt in 72% of cases.
- Reasoning caps as an accuracy trade (owner 10-23): replies are salvaged instead.
- Per-request sampling presets per family (M.3): sampling is the owner's setting, sent only when turned on per model (M11).
- File-granular revert (L.2), control-plane `response_format` (M.2), check memoisation (AC.3), compaction (O.4/Z; breaks the prefix cache), edit-format change (Y), automatic retention deletion (U.4, owner), tool masking as loop-stopper (AA.2).
- A peer mailbox, specialist debate rounds, broadcasting builders' reasoning, parallel builders coordinating by message: no effect or harm in the research; the write guards do it deterministically. Kill rule: an item that raises tokens per accepted criterion by more than 5% without lowering a defect metric goes off.
- Batching plan WB.3 (fixer bundle size by capacity: already capped at three) and WB.5 (plan batching: not supported by the data); WB.2 on Ornith (refuted for that model).
- Q3 Python dry run, Q4 stub leg, F6, E4: dropped in HR2 for evidence or superseded forms.
- Live co-editing beside agents that write the same files (CRDT, locks): conflicts; editing is turn-taking on a paused run only (UX.12-UX.16).
- In-browser runtimes (WebContainers) for the preview: JS and WASM only; the harness builds seven languages.
- Cross-run memory without approval: dropped once for prompt injection; lessons need approval.
- Any change to the owner's models or settings by the agent.
