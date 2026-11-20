Archived copy of the cloud end-of-run product reviews, exported 2026-11-20. New reviews go in this folder as files.

# Harness Product Review

Oct 20, 2026 · @Arun

Updated after each run. This revision follows run-8b0c94df, the first medium brief (a full-stack team task manager) on the local model alone, cancelled after 24 hours at 9 of 30 locked acceptance tests. The earlier columns stay for comparison.

## Latest run

**Newest (2026-10-25 07:10 JST): a command-line brief completed in 21 minutes with all 14 locked criteria passing, and the hidden tests still failed three of eight (run-62f596f4, wordstats-cli).** The earlier attempt on this brief (run-5a70a4a0) stopped at 4 of 14 criteria. Nine of its ten failing tests wrote their input file by a relative name in the test's own folder while the harness's `run_cli` fixture ran the program in a different folder, so no product could pass them (LF.271: the fixture now moves the test into the same folder). With that fixed the same model reached 14 of 14 in one sprint, and the keep rule for fixes that gain much and break only worker-written unit tests (NG.1) fired for the first time: a fix that made 4 tests pass and broke 1 unit test stayed, and the sprint was accepted.

- **But the independent suite was too weak.** The product counts words wrongly (the brief says a word is a run of letters, digits and apostrophes; the product's count differs on the hidden example), and `--json --top N` also prints the three counts, where the brief says only the top list. Both are written plainly in the brief's interface. The 14 tests QA wrote did not exercise them, so the harness accepted a product with three hidden failures (5 of 8). The release did flag the weakness: a deliberate change (`or` made `and`) went unnoticed by the suite, and five lines of the interface contract were not checked.
- **What this says:** the harness now finishes quickly and honestly, but its verdict is only as strong as the suite the same small model writes. Next: use the interface section's own examples and rules as test seeds (a check, without a model, that every sentence of the interface has a test that names it), and treat the mutation finding as a reason to send QA back before release, not only a note after it.
- **How others do it:** held-out tests written by a separate, stronger agent or by people are the usual way to keep self-grading honest; a cheaper complement is to make the specification itself executable, so each stated rule becomes a test by construction.

**Newest (2026-10-25 05:30 JST): gpt-oss-20b completed the larger tasks-api brief end to end, hidden 10 of 10, in 83 minutes (run-f52ee567).** Four samples of this model on this brief: 1/10, 10/10 (three hours, cancelled), 3/10 (cancelled), then this one, completed. The locked suite finished at 15 passed and 0 failed, and the release went ahead with the model's own failing unit tests named in the run's gaps, as designed.

- **What moved it from the earlier samples, in order of effect:** (1) the harness now reopens a locked suite whose tests carry a Python error in their own line (`json={{...}}`, a set holding a dict): 5, then 6, then 8 broken tests were found and repaired within minutes, where one run lost two hours on them; (2) a test whose name carries a per-run value (a random user name in a parametrized id) is now the same test on every run, which stopped seven good fixes being reverted for "breaking" it; (3) a fix that gains much and breaks only a worker-written unit test is kept (not yet fired); (4) a re-planned sprint is put back to its best product if the redraft left it clearly worse (not yet fired).
- **What it says about how to build the harness:** three of the four changes that mattered fixed the harness's measurement of the product, not the model: a suite with broken tests, a test name that changed, a gate that weighed what broke and not what was gained. The model's output was usable much earlier than the harness could tell.
- **Still open:** the spread between samples is large, so a single run proves little; the unit tests the model writes still fail and are released as a gap; redundant reads stay near 65%; Hono in TypeScript is a separate question (the next run tests it with all of these in place).
- **To add value next:** deterministic checks of the suite before the sprint (does every test file compile; do its literals mean what it intends), a fixer shown the failing line and the declared type, and a closed run-and-fix loop for workers.

**Newest (2026-10-25 02:25 JST): the larger tasks-api brief on gpt-oss-20b scored hidden 10 of 10, after three hours the harness spent on the wrong thing (run-c48266b8, cancelled).** Earlier today the same model scored 1 of 10 on this brief. This time the product was right (sprint 1 accepted, 12 then 14 of 21 criteria, the hidden tests all passed), but the locked suite read 14 passed and 7 failed for more than two hours: four re-plans, 62 defects left open, 18 reverted fixes. Looking at the seven failures: five were tests whose own line was `json={{"title": ""}}` (double braces, which Python reads as a set holding a dict) and raised `TypeError` before any request, so no product could pass them; one tested a path relative to the wrong folder; one reused names earlier tests had taken.

- **Changed, from this run:** the Python packs' own-code patterns now know `unhashable type`, so the harness reopens the locked suite for such a test as it already does for undefined names (LF.269). A fix that gains at least three tests and three times what it breaks, and breaks only worker-written unit tests, is kept instead of being reverted whole (NG.1, a switch): one fix here made 12 tests pass, broke 1 unit test, and was reverted.
- **What it shows about the harness:** the weakest link was the independent suite. It is written by the same small model, and a test bug locks in as a definition of done no product can meet. The harness checks tests for their own errors only for the patterns it knows. Next: look at the suite before the sprint, with a cheap deterministic parse of each test file (does it compile; do its literals mean what the test intends), and treat a criterion that fails identically for hours across all re-plans as a suspect test.
- **How others do it:** held-out tests written by a separate agent or by people are the usual defence against self-grading; the lesson here is that the held-out tests also need a check of their own.

**Newest (2026-10-24 23:20 JST): the same model on the same Python brief completed, hidden 9 of 9, and the release switch did what it was built for (run-f9b70fcf, notes-api).** Earlier today this product also scored 9 of 9 but the run ended as failed, because the model's own unit tests would not pass. This time the run reached the release with one of those unit tests still failing, and the release went ahead with a named gap in its record: "1 of the project's own unit tests still fail and ship failing (the locked acceptance suite passes; the fixes did not close them): test\_note\_create\_missing\_title". The locked suite finished at 18 of 18. It took 31 minutes, and the first 9 reached 17 of 18 criteria.

- **What the day's four Hono runs add:** hidden 1/9, 0/9, 0/9, 0/9 for this model in TypeScript, against 9/9 twice in Python. In each the harness did its part (pack, install, suite locked); the model's TypeScript did not build. The runs found five harness defects that were fixed (git bytes, the library pick, Node memory, nonexistent package versions, a file the runner would not collect) and two safeguards that were added (best attempt kept across a re-plan; release with named unit-test failures).
- **What stays unproven:** the best-attempt safeguard (KB.1) has not fired yet. In this run a re-plan dipped from 17 to 12 criteria and recovered by fixing, so there was nothing for it to restore.
- **To add value next:** a larger brief on the improved harness (tasks-api is running now), then a model of a larger size on the Hono brief, to separate the model's limit from the harness's.

**Newest (2026-10-24 21:00 JST): gpt-oss-20b on notes-api-hono with the new Hono pack, run-314376ee, hidden 1 of 9, stopped after 55 minutes.** The pack did what it was built for: the harness set the project up (the same stack failed in the earlier run because the model's setup stage invented a test API), and the first test round fixed a type error in one pass. Then two things went wrong, and the run shows how each is handled.

- **A pinned version that does not exist (fixed, LF.267):** a fixer added `async-mutex@^2.3.0`; every `npm install` failed and every later fix was judged against a product that could not install, so 11 fixes were reverted for "breaking" tests. The installer names the missing version, not the existing ones, so each rewrite guessed again. The harness now looks the package up in the registry and puts the real release at the front of the defect. The next fixer used it (`^0.5.0`), the install cleared, and seven other defects closed with it.
- **Workers rewrote the pack's contract:** drafting dropped the `createApp()` export the pack's guide names, and seven test files the same model wrote imported it. One restoring fix closed all seven. The model then could not make the behaviour pass: 1 of 18 criteria, and the escalation stopped the run because deferring 17 of 18 would leave more than half the product undelivered.
- **Read with the Python run:** the same model passed 9 of 9 on the same product in Python with its pack. So the difference sits in the language and its toolchain, not in the brief: the model got a working product in Python and not in TypeScript with Jest and ts-jest. One run each, so this is a pointer, not a measurement; the clean rerun now live is the second sample.
- **To add value next:** (1) keep the pack's entry file's exports as a contract the harness restores, as it already keeps runner configuration; (2) look up facts instead of asking the model for them (done for versions; the same for an import path or an exported name); (3) choose the pack's test runner for the model's strength, not only for the stack (Node's built-in runner needs no ts-jest); (4) the run-and-fix loop for workers.

**Newest (2026-10-24 19:50 JST): gpt-oss-20b on a small brief, run-ec0c9589 (notes-api, Python pack): hidden 9 of 9, and the run still ended as failed.** The product was right: 17 of 18 acceptance criteria passed, the 18th a flaw in the test itself that a dispute had already deferred. What failed was the project's own unit tests, written by the same model, which no fixer could make pass (one gave up, others were reverted for breaking tests that passed). The release gate held the product back for them; each hold sent the last sprint round again, each round ended in an escalation, and the escalation budget ran out. So the same model that scored 1 of 10 on the larger tasks-api brief scored 9 of 9 here: brief size, not the harness, set the result, but a harness rule threw a correct product away.

- **Changed (RL.1, a switch, on):** when the locked suite passes and only the project's own unit tests fail, and the sprint was already accepted with them open (or the release has held as often as it may), the product is released with the failing tests named as a gap in the run's record. A failing criterion, a suite that does not run, or an unready handoff still hold it back.
- **How others do it:** Benchmarks such as SWE-bench score a change on held-out tests the agent did not write (not checked again today; the earlier sections of this document cite the sources). The locked, independent suite is the held-out test here; the model's own tests are now evidence that is reported, not a gate that can discard the work.
- **To add value next:** show a fixer the failing line and the declared type, since it gave up on faults it could have read; give workers a run-and-fix loop inside their own conversation; keep a library of setups that replay on an empty project (the stored Hono entry could not), now backed by a Hono pack.

**Newest (2026-10-24 17:48 JST): the first gpt-oss-20b baseline, run-06546eb9, tasks-api, cancelled after 71 minutes, hidden 1/10.** The model is the owner's (openai/gpt-oss-20b on LM Studio, 131,072 window), diagnosed first (tier standard 0.778). The setup was a deterministic FastAPI pack, so the workers (per-file drafting, then fixers) wrote the whole product, which is the flow the owner asked to measure. Result: sprint 1 ran five attempts and closed none; 6 defects raised, 13 left open; locked suite 5 of 28; tool failure rate 15% (mean 5%); redundant reads 50% (healthy 8-19%). The Ornith runs where the setup agent wrote the product closed both sprints in about 30 minutes.

- **What the harness got right:** the engine's quirks were handled (named tool choice sent as required, LF.263), the suite was locked and reopened once when two tests could not pass, and fixers that could rewrite a whole file did close defects.
- **What failed, and why it is the model:** the fixers cannot repair a fault that spans modules. Twice the fix stage changed nothing and said the refactor was too complex; the localiser named the wrong files (a non-UTF-8 payload) when the failing setup was a database file in a temporary folder. This is the cross-file mismatch pattern per-file drafting produces, here on a weaker model.
- **One real harness bug found by the run (LF.264):** a file with a non-UTF-8 byte made `git diff` fail to decode, the error was not one the call sites catch, and the run failed mid-fix. All twelve git reads now decode with replacement; the run was resumed on the fix and then cancelled for the reason above.
- **Next:** a closed run-and-fix loop for the workers (each writer runs the tests and fixes inside its own conversation), a pack-first setup so a weak model never invents one, and a fixer that is shown the failing line and the declared type. Until then a model of this tier belongs on the setup-built flow.

The clean comparison run (run-cfb01bcc, 2026-10-24, tasks-api on Ornith, one harness version 57e55c04 and no mid-run deploys) scored 10/10 on the hidden tests, 6/7 on quality, with the locked suite at 35 passed and 0 failed, and cost clearly less than the first Ornith run: 155 active minutes against 226 (32% fewer), 735,000 output tokens against 998,000 (26% fewer), 121 model calls against 159, no defect left open against three, and 2 release gaps against 8. The model server stopped for two hours in the middle of it (07:28 to 09:33 JST); a watcher resumed the run in place within a minute of the model coming back, and that gap is not counted in the active minutes.

| Measure | First Ornith run (mixed versions) | Clean run | Qwen runs |
| --- | --- | --- | --- |
| Hidden tests | 10/10 | 10/10 | 10/10 |
| Quality tests | 7/7 | 6/7 | 6/7 to 7/7 |
| Active minutes | 226 | 155 | 81 to 98 |
| Output tokens | 998,000 | 735,000 | 458,000 to 545,000 |
| Model calls | 159 | 121 | 147 to 180 |
| Defects left open | 3 | 0 |  |
| Release gaps | 8 | 2 |  |

What made the difference is the reply ceiling of 24,000 tokens, set for this model from the measured tail (a few long turns held most of the output): nine replies reached it, all nine were answered from their own reasoning by reply salvage, and none was lost. The one failed quality test is the one that has failed on several runs and models: a title of only spaces was accepted. Nothing in the harness named that case, so the specification's error catalogue now says a blank required value is the same failure as a missing one (LF.255), and the suite writer is now told to assert only what the brief requires (LF.253). That rule was not in the clean run, whose release gaps fell from eight to two for another reason: it wrote a different suite (pytest, one over-assertion on list order instead of seven on error text). So the rule's effect is still unmeasured, and the next run measures it. Redundant reads rose to 56% of reads in this run, the largest repeating cost still unaddressed: the model re-reads files already in the stage's project memory.

run-2b891f3f (2026-10-23/24, tasks-api, the first run on Ornith-1.5-35B-A3B; harness 2744a74 to 57e55c04, so a mixed-version run) scored 10/10 on the hidden tests, 7/7 on quality, with the locked suite at 39 passed and 0 failed. It took 226 active minutes (about 340 on the wall clock; the rest was paused or rewound), 998,000 output tokens and 159 model calls, with the model busy 97% of the time. That is about two and a half times the earlier Qwen runs (81 to 98 minutes, 458,000 to 545,000 tokens). The release recorded 8 gaps it knew it had not proven: seven are locked tests that assert the exact text of an error body where the brief only requires the status code, and 21 lines of the interface contract were not checked.

Why it was slow is a property of the model, not of the harness: the median reply was 3,777 tokens, the same as Qwen's, but 22% of the replies ran 16,000 to 63,000 tokens and held 73% of all output. Turns that only read or list files cost 14,000 tokens each, more than the 10,500 of a turn that writes. The architect took 55 minutes against a median of 17 and the acceptance author 65 against 8.

| Measure | run-2b891f3f (Ornith) | Qwen runs |
| --- | --- | --- |
| Hidden tests | 10/10 | 10/10 |
| Quality tests | 7/7 | 6/7 to 7/7 |
| Active minutes | 226 | 81 to 98 |
| Output tokens | 998,000 | 458,000 to 545,000 |
| Model calls | 159 | 147 to 180 |

Seven harness defects were found and fixed while it ran, each by a test that fails on the old code: the settings page looked a diagnosed model up under a different name from the worker's (LF.245, LF.246); a specification revision was thrown away when one section came back as an empty list (LF.247) and failed to join when an empty section had no form to copy (LF.248); the harness's own questions about whether a write was allowed were counted as refused writes, 124 of them, so the first real refusal told the model to stop (LF.249); the ban on re-opening reasoning was sent in a form this model's server rejects, which lost the first reply cut at the new ceiling (LF.250); a harness scratch file was reported as a product defect (LF.251); and a test report was taken as the file to rewrite, twice (LF.252). Two of the seven came from the diagnosis work built the day before; the other five were old code that this model's replies happened to reach.

Two experiments came out of the run. Writing the acceptance suite in batches of criteria did not help: each turn spent about 30,000 tokens thinking before a plain directory listing, so more batches meant more turns, and the switch stays off. A reply ceiling of 24,000 tokens, set from the measured tail, does work with reply salvage; whether it holds quality is what the next clean run measures. A clean single-version run on the same benchmark (run-cfb01bcc) started at 05:48 JST for that comparison.

run-77f7752f (2026-10-23, 1246bb22 with LF.218-220) scored **10/10 hidden, 7/7 quality** - the best quality result yet - in 98 active minutes, with a real KPI regression on mutation score (0.333 against a 0.708 mean of the last 3): four success-flag mutants (`True` to `False`) and several `or`/`and` logic flips in `app.py`/`models.py` went uncaught by the locked suite. Not a harness bug - direct evidence for QM.2 (mutation-guided tests, built, still off): turning it on would have caught these as unit-test defects during the run itself.

This run also ran through a two-session conflict (03:27-04:57 JST): another Claude session believed itself the sole driver of the loop, deployed and scored a run concurrently with this one, and the collision produced a real bug (a shared Python runner left without pytest after a cut-off install scored a 10/10 product as 0/10 - fixed as LF.219) plus a duplicate, contradictory STATE.md narrative. Resolved by confirming via `ListAgents` that no other session was reachable, then reconciling the record into one consistent account rather than picking a side.

Gated run 1, the first measured run since the all-on move (run-f13f7438, 2026-10-22, frozen on 1246bb22), scored **10/10 on the hidden tests** in **59 active minutes** - the fastest of the three all-on runs yet (140, 108, then 59), with zero tool-call failures and zero replies lost to the output cap across the whole run.

| Measure | Shakedown 1 | Shakedown 2 | Gated 1 |
| --- | --- | --- | --- |
| Hidden tests | 10/10 | 10/10 | 10/10 |
| Quality tests | 7/7 | 6/7 | 6/7 |
| Mutation score | 0.6 | 0.625 | 0.5 |
| Active minutes | 140 | 108 | 59 |
| Tool-call failures | several | several | **0** |
| Replies lost to the output cap | 2 | 2 | **0** |

No KPI regression against the 5-run mean. One completion gap worth a closer look later: two source files (218 lines) were drafted but never wired into the running app - dead code the release correctly flagged, not a harness defect; the architect's or backend specialist's draft-then-refactor habit is worth watching across more runs before treating it as a pattern to fix.

LF.218 (localisation asked once per retry, not twice) was built during this run but not deployed - gated runs (MF.4) take no mid-run deploys; a bug found is filed for the next Fix batch instead.

The gate pair is done: both frozen all-on runs scored **10/10 on the hidden tests**, and gated run 2 (run-f13f7438, 2026-10-23) was the fastest tasks-api run yet - 59 active minutes, no reply lost to the output cap, no failed tool call.

| Measure | Gated run 1 (run-8cced4a9) | Gated run 2 (run-f13f7438) | Before the switches |
| --- | --- | --- | --- |
| Hidden tests | 10/10 | 10/10 | 10/10 when finished |
| Quality tests | 6/7 | 6/7 | - |
| Mutation score | 0.625 | 0.5 | - |
| Active minutes | 108 | 59 | 199-233 |
| Output tokens | 507,000 | 337,000 | 1,050,000-1,090,000 |
| Replies lost to the output cap | 2 | 0 | 4-6 |

What still costs quality: both products accepted a task title of only spaces (the one quality test they failed), and the locked suites noticed only half to two-thirds of deliberate small changes - the gap mutation-guided tests (built, off) is meant to close. What nearly cost the result: the hidden-test runner had been left without pytest by an interrupted install, and gated run 2 was first scored 0/10 as a false acceptance; the runner now checks pytest imports, and a run whose tests never ran is unscored rather than failed (LF.219).

Shakedown run 2, the second all-on run (run-8cced4a9, 2026-10-22), scored **10/10 on the hidden tests** in 108 active minutes - faster than run 1's 140, confirming the gain holds across a second run - with 507,000 output tokens and 2 replies lost to the output cap.

| Measure | Run 1 | Run 2 |
| --- | --- | --- |
| Hidden tests | 10/10 | 10/10 |
| Quality tests | 7/7 | 6/7 |
| Mutation score | 0.6 | 0.625 |
| Active minutes | 140 | 108 |
| Output tokens | 715,000 | 507,000 |
| Replies lost to the output cap | 2 | 2 |

Two bugs found during the run, neither changing its outcome or score: a product module imported by the wrong path read as an undeclared package (fixed live, LF.214 class), and the run page's sprint counter undercounted a sprint fast delivery opened with no model call, so a later sprint's header showed the wrong number (LF.217, UI only - the owner's rule is that UI bugs are not counted against a gate run). Both shakedown runs are now clean of outcome-affecting bugs, so the harness moved to gated runs: the SHA is frozen at the point both fixes deployed, and `run-f13f7438` is the first gated run on it, scored on hidden tests only with no mid-run deploys.

Also measured but not yet released: **mutation-guided tests** (QM.2), which turns a locked suite's own blind spots into unit-test defects for the testing role, settled deterministically by re-running the unit tests with the one change back in. Built and tested, behind `MUTATION_GUIDED_TESTS`, off - it has not yet run live.

Shakedown run 1, the first with all 24 group 2 switches on (run-bf8a972f, 2026-10-22), scored **10/10 on the hidden tests** in 140 active minutes, against 199-233 for the last three tasks-api runs, with a third fewer output tokens and 2 replies lost to the output cap instead of 4-6.

| Measure | All-on run | Last three runs |
| --- | --- | --- |
| Hidden tests | 10/10 | 10/10, 4/10 (cancelled), 10/10 |
| Active minutes | 140 | 199-233 |
| Output tokens | 715,000 | 1,050,000-1,090,000 |
| Replies lost to the output cap | 2 | 4-6 |
| Model calls | 247 | 266-277 |

What earned it: sprint placement put the restart criterion with the item routes, so sprint 2 passed on its first measurement (25/25); the dispute caught a locked test that contradicted the specification; localisation and the revert of fixes that broke passing tests fired as designed. What still cost time: the architect's three review rounds (56 model minutes, each revision rewriting about ten sections - now bounded, LF.215), two identical fast rewrites reverted for the same test (the rewrite never saw earlier attempts - fixed live, LF.216), and a docstring line read as an import. The open cost is replies that reason to the cap: llama.cpp has a per-request reasoning budget in recent builds, but a server-side `--reasoning-budget` overrides it and its defaults changed in 2026 ([llama.cpp reasoning budget](https://huggingface.co/datasets/echodict/llama.cpp/blob/main/common/reasoning-budget.cpp), [forge issue 54](https://github.com/antoinezambelli/forge/issues/54)), so the harness's probe has to measure it on this server before relying on it.

Measure pair 3, run 1 (run-7e5c11af, on fadd5a58 with Fix batch 2) scored **10/10 on the hidden tests**, the third full score in a row, in 199 minutes. Its defect-fix stages fell to 5 from 15-16 on 20dcdfbe: the start failure was raised as one defect (LF.172), not six to eight. The time went elsewhere: two locked acceptance tests could pass for no product (one assumed an empty store, one signed in as the wrong account), so the suite was disputed and repaired twice, and the sprint's milestone review sent it back once. Fix batch 3 (LF.181 to LF.183) targets both: every service suite's writer is told the store is shared by every test, and a fixer that names a locked test by its name now raises a dispute at once. Four replies were still lost to the length cap. Run 2 of the pair started at 12:24 JST; harness-written test reports for any finished run are now available on demand (`loop.sh documents <run>`, plan DT.1 and DT.6).

Measure pair 2 is done: both runs on 20dcdfbe scored **10/10 on the hidden tests**, against 0/10 for both on 039ad84 (run 2, run-403f7479, completed 08:57 JST on 2026-10-22). The price is fix-stage time: active minutes rose from 101 to 227, model calls by 61% and output tokens by 137%, because defects the old suite never saw are now found and fixed. Run 2's costliest defect was the product's own: an integer in a token's `sub` claim, which PyJWT 2.10+ refuses, blocked 8 criteria for about an hour. Five of its replies ran to the length cap with no answer (10% of output across the pair). Fix batch 2 (LF.171 to LF.180), with that PyJWT rule now in the Python guidance, was deployed at 09:00 JST, and Measure pair 3 started at 09:01; the AY switches are the first group 2 arm after it.

| Measure pair 2, arms (n=2 each) | 039ad84 | 20dcdfbe | Change |
| --- | --- | --- | --- |
| Hidden tests | 0/10, 0/10 | 10/10, 10/10 |  |
| Active minutes | 101 | 227 | +125% |
| Model calls | 194 | 312 | +61% |
| Defect-fix stages | 9.5 | 15.5 | +63% |
| Defects fixed | 1.5 | 3.5 | +133% |
| Output lost to the length cap | 0% | 10% |  |

Measure pair 2, run 1 (run-bf3f222f, on 20dcdfbe with Fix batch 1) scored **10/10 on the hidden tests** on 2026-10-22, after 0/10 twice on the frozen version before it. The specification and the drafted `start.sh` used the product's own `.venv`, and the suite now starts the service through `start.sh`, so the start failure was caught and fixed inside the run. It took 237 minutes, the model busy for 218: 185 model minutes went to 14 fix stages in sprint 1, at 92% reasoning, and sprint 2 came out green at drafting. Fix batch 2 (LF.171 to LF.177) targets that cost: one start defect instead of six, reverting a fix certain to fail, judging a defect by its own tests, and a fixer's test move out of the suite refused. Run 2 of the pair started at 05:19 JST on the same version.

| Fix-stage cost | Measure 2 run 1 |
| --- | --- |
| Model minutes in fix stages | 185 of 218 (wall 237 min), 151 calls, 92% reasoning |
| Fix stages | 14, sprint 1 only |
| Defects left open (KPI) | 10, against a 2-run mean of 3.5 |
| Replies lost to the length cap | 2 (6% of output) |

Measure pair 1 (MF.4: one frozen harness version, 039ad84, no deploys) scored 0/10 on the tasks-api hidden tests in both runs, while the harness's own suite passed every criterion. Both failures had one cause: the work orders rewrote the product's `start.sh` to a bare `python` that lacks the product's packages, and the acceptance suite started the service its own way, so nothing ran `start.sh`. With `start.sh` pointed at the product's `.venv`, both products score 10/10. Fix batch 1 (LF.167 to LF.170) was deployed at 01:10 JST on 2026-10-22, and Measure pair 2 started at 01:13 on that one version.

| Measure | run-aedcd228 (Measure 2) | run-650d812f (Measure 1) |
| --- | --- | --- |
| Hidden tests | 0/10; 10/10 with start.sh fixed | 0/10; 10/10 with start.sh restored |
| Locked acceptance suite | 21/21 criteria, 11 tests | 21/21 criteria, 67 tests |
| Unit tests | 63/63 | passing |
| Stack | FastAPI, 2 sprints | Flask |
| Wall time (min) | about 120, completed | 81, completed |
| Model calls | about 210 | 144 |
| Output reasoning share | 73% | not measured |
| Failed tool calls | 2.1% | not measured |
| Redundant reads | 73%; 24 of 142 tool-calling replies only re-read files the request held | not measured |

Earlier runs, before the Measure cycle:

| Measure | run-d48f049e (medium gate run 2) | run-b7a20bad (medium gate run 1) | run-01a1ab9c (medium findings run) | run-894282e3 (medium shakedown) | run-419b8ff6 (fast notes-api-hono) | run-606ff231 (thorough notes-api-hono) | run-c00868a9 (fast fullstack-bookmarks-py) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Hidden tests | none for this brief | none for this brief | none for this brief | none for this brief | 9/9 | 9/9 | 0/8 (no `start.sh`, the product never started) |
| Locked acceptance suite | 34/34 over 13 criteria; 59% of the product's lines unreached | 0/31; reached the product only in the last round | 62/62 over 13 criteria, all through the API; the page kept 1 of 10 contract checks | 0/25 at the cancel (the product did not start) | 32/32 | 11/11 | none locked |
| Unit tests | 30/30 (29 service, 1 page) | failing at the end | 118/118 (52 page, 66 service) | 2 files, both testing the unserved copy | none: the one written sat outside the runner's folder | none (a release gap says so) | none ran |
| Defects raised / fixed / reverted | 25 / 8 / 0 | 48 / 18 / 0 | 27 / 7 / 4 | 34 / 3 / 8 | not measured | not measured | not measured |
| Wall time (min) | 351, completed (2 rewinds) | 239, failed (11 rewinds) | 555, completed | 426, cancelled | 38 | 46 | 80, failed |
| Model calls | 470 | 419 | 1,203 | 700 | 98 | 131 | 221 |
| Output tokens (M) | 1.34 (75% reasoning; 22% in 10 replies cut at the cap) | 0.87 (56% reasoning; 10% in 3 replies cut at the cap) | 1.69 (67% reasoning; 24% in 20 replies cut at the cap) | 1.62 (74% reasoning; 47% in 38 replies cut at the cap) | 0.19 (63% reasoning) | 0.21 (58% reasoning) | 0.37 (78% reasoning) |
| Input from the cache | 74% | 66% | 71% | 63% | 59% | 58% | 78% |
| Failed tool calls | 7% | 8% | 5% | 17% | 1% | 5% | 15% |
| Redundant reads | 71%, mostly memory pointers | 36% | 33% | 71%, mostly memory pointers | 62%, nearly all memory pointers | 81%, nearly all memory pointers | 84%, nearly all memory pointers |

Its fixes were mostly about making drafted files install and fit. They covered tool arguments written in tag form (LF.108), a specification that requires a setting at startup (LF.111), each package's manifest named and a failed install raised (LF.112, LF.113, LF.115), call budgets and lost replies counted across a compaction (LF.114, LF.116), test bugs read from the test's own source (LF.117), and a unit failure's cause taken from the whole output (LF.118).

## Features to improve

**From the Ornith run (2026-10-24).**

- **Reasoning is a per-turn cost, so a model that thinks at length pays it on every turn, whatever the size of the job.** Splitting the work did not cut it. What cuts it is limiting the tail of single turns: a per-model reply ceiling chosen from the observed tail, with reply salvage answering a cut reply from its own reasoning (built as WB.9; `loop.sh scan` suggests the value). Still to try: a turn-aware effort for turns that only read, which were 35% of all output.
- **The first turn of a stage reads what the request could have held.** The acceptance author spent 14,000-token turns deciding which spec lines to read for error messages. Putting the error catalogue and function contracts into its opening request would remove those turns.
- **The locked suite over-asserts.** Seven of the release's eight gaps are tests that assert the exact error text where the brief gives only the status code. The writer should assert only what the brief or interface contract states, and assert exact text only where one of them gives it.
- **The setup stage still writes the whole product** despite the instruction not to, as on three earlier runs; the later review catches it, but the stage's minutes are spent.
- **The plan check can loop on a justification it rejects:** the lead declined carried-forward work as 'no test requires it' three times, each rejected, about 12 minutes, then the plan was dispatched with the problem noted.

The biggest gain left is what the suite measures, not how fixers work. The findings run converged on every test it had, yet its page fails the interface contract, because every acceptance test went through the API. The first five rows are this run's; the rest keep the earlier proposals, and the status column says what is built and what waits for the gate runs.

| Feature | What the runs showed | Change | Status |
| --- | --- | --- | --- |
| The way a person starts the product | Both Measure runs passed 21/21 criteria inside and 0/10 hidden: the work orders rewrote start.sh to a bare python without the product's packages, and the suite started the service its own way | The suite starts a service through its start.sh (LF.168); the architect is told the setup's start.sh already works (LF.169) | Deployed 2026-10-22 01:10 JST; Measure pair 2 measures it |
| Re-reading what the request holds | 24 of 142 tool-calling replies did nothing but read files the project memory held: the lead's first three and every review's first move, each a model call with its reasoning | The opening request ends by naming the files the memory holds, fixed for the visit so the prompt cache holds (LF.171) | Built, Fix batch 2 |
| A whole re-plan for one review finding | A sprint with every criterion green was sent back for one adopted database retry; the lead, drafting, the work order and all four reviews ran again, about 25 minutes | With the criteria green, a milestone finding goes to a targeted fix, and only the reviews whose area the fix touched run again | Proposed, Fix batch 2 |
| Group 2 behind switches | Fix stages took 43 of 97 model minutes on Measure 2 (87% reasoning, up to 42 calls a defect) | Localise first, verify after each write, a 60-call cap per defect, code-graph neighbourhoods, lessons from recorded defects, release audits: each behind its own switch | Built 2026-10-21/22, off; measured one subsystem at a time after Measure pair 2 |
| Modules nothing reaches | The service runs entirely from one 586-line main.py that redefines its models, schemas, auth and routes; the planned models, schemas, database, auth and three router modules (809 lines) import each other but nothing imports them. The page runs from one App.tsx ("In a real app, these would be imported from './pages/LoginPage'"); its pages, components and contexts (1,074 lines) are unreached. 59% of the product is islands, and every test passed | A check of the import graph from each entry point (the served page's script, the service's start module), through the per-language import rules the language service already has; a source file no entry reaches is a defect naming the module that duplicates it, raised at the CI gate and at release | Built 2026-10-21 (LF.120) |
| Constraints no test starts | The compose file points the service at PostgreSQL through asyncpg, which no manifest declares, and main.py builds a synchronous engine, so the shipped stack would not start; alembic is declared with no migration; reminders were never built. The release review said the Docker constraint was met because the files exist | The release review checks a brief constraint by what runs: the driver a configured database URL names is declared, a declared migration tool has a migration, and each brief feature names the criterion that proves it | Proposed |
| Sprint panel during a re-run | While attempt 3 passed everything, the run page still read "Failed: exhausted remediation attempts, 1 open", which was attempt 2's record | A live run's current sprint shows the attempt under way, with its live defects, as In progress | Built 2026-10-21 (LF.119) |
| Files drafted apart that do not fit | 61 files drafted in 8 minutes, one call each; 33 imports named things their modules never defined (\`get\_db\`, \`get\_settings\`, \`TaskCreate\`, default imports of named exports), and the product took three attempts to start | A contract of each module's exported names, made from the specification before any file is drafted and given to every draft that imports it (CM.2 with EF.11); the language service checks the drafts against it before the first round | Group 2 (CM.2, EF.11) |
| Certain causes behind symptoms | Rounds raised "the suite fails" while the language service knew the file and line; merged together, one fixer rewrote four files and each round met the next missing name | Findings stay one defect per file, the module that lacks a name is the file to fix, a fix is settled by asking the service again, and a round that finds the product not starting raises the service's findings (LF.96 to LF.105) | Built 2026-10-20 |
| Planning time | The lead used 34 model minutes, 87% reasoning; three replies were lost at the 30,000-token cap and a re-plan read one file a call for 25 minutes | Thinking off for the rest of a planner's visit after its first lost reply, and a cap on a planner's reading (M.4); the owner's reply ceiling is the other lever | Proposed, owner's call |
| Pages the acceptance suite never opens | All 62 acceptance tests used the API. The page's labels are not tied to their inputs and its views are not routes, so 9 of 10 page lines of the interface contract failed at release; only a release note said so | Builders are shown the interface contract (EF.11); each page criterion gets a test that opens the page; a contract line the last test round fails becomes a defect, not a release note | Proposed, group 2 |
| Security fixes that stop the product starting | The security review asked for the signing secret to come from the environment; the product then refused to start without it, two fixes were reverted and the sprint ran out of re-plans | The review is told what the building stages already were: a secret has a development default or is generated at first start (LF.90) | Built 2026-10-20 (LF.90) |
| Tool-list changes and the prompt cache | 117 cache misses followed a change to the offered tools; 65 times a tool was withheld mid-stage | Keep the offered tools fixed for a stage and refuse a withheld one when it is called (masking), so the cached prefix survives | Proposed |
| Knowledge newer than the model | A password library and its hashing dependency broke every hash after a major release; fixers read it as a version mismatch for rounds | Web search through a SearXNG service and a library's official MCP server (read-only tools), each with a share per stage | Built 2026-10-20, unmeasured |
| Rewind instead of restart | Four rewinds kept 9 hours of work through 32 harness fixes; listing the rewind points still runs out of memory on a long history | Rewind by checkpoint id (LF.89); a points listing that never reads the history whole | Built; listing open |
| Compaction keeping the request | 7 of 8 summaries read "too long to summarize" and replaced the stage's request; all 6 compacted fix stages failed, one editing the copy nothing serves | The summary message carries the stage's whole opening turn and the files it wrote; the summariser is handed the latest work, so it is never empty. Checked by replaying a live fixer's conversation | Built 2026-10-19 (LF.36), deployed; unmeasured live |
| Refusing looks once reading is withheld | 49 of 70 refusals were of what the memory never shows (an installed .venv, a built dist, a database); an empty folder was refused 4 times running, then the stage repeated one reply about ten times | A look is refused only when the stage already holds what it shows; an empty folder lists | Built 2026-10-19/20 (LF.35, LF.37) |
| A start failure and its symptoms | A build that did not start raised every lost acceptance test as "removed or renamed", queued ahead of the start failure | With a start failure recorded, lost acceptance tests are not raised as regressions; the one start defect stands for them | Built 2026-10-20 (LF.38) |
| Replies cut at the length cap | 47% of all output tokens sat in 38 replies that hit the cap with no tool call; fix stages were 81% reasoning | A reasoning policy per stage (M.4), judged on the gate runs | Group 2: waits for the gate runs |
| Served code versus drafted code | The plan put the app in `frontend/` and `backend/` beside the template's served `src/` and `main.py`; fixes landed in both copies for 20 hours | The plan names the served files; the specification is sent back when it never names them; the unserved copy is reported to every fixer and at release, and ranks last in the project memory | Built 2026-10-18/19 |
| Fixers that read without writing | 123 model calls and one edit in 47 minutes; 118 tool calls and no edit; 47% of all reads returned nothing new | After 12 model calls with no change, the tools that only look are withheld and the fixer is told to write; its change is measured and undone if wrong | Built 2026-10-19, unmeasured |
| A server the sandbox lacks | The specification named PostgreSQL; three fixes ended "changed nothing, environmental constraint" | Every stage is told the data store here is the embedded file under `DATA_DIR`; every fix request for a service says a missing server is no reason to change nothing | Built 2026-10-18/19 |
| Measurement at settlement | A fix was closed as fixed after rewriting a probe script or a unit test; the next round found it again | A fix for a criterion never targets a test file or a scratch file; a criterion measured green needs no named regression test; a stage that spends its calls is recorded from its writes, not restarted twice | Built 2026-10-18/19 |
| Grouping failures behind one cause | 13 defects for one unserved stub; 10 for one broken sign-in | Criteria that fail the same way on the same page, or at one layer the whole product meets, are one defect for one fixer (14 became 8 in the last round) | Built 2026-10-18 |
| Reasoning share | About 92% of fix stages' output tokens are reasoning; 35% of all output sat in replies that ran out of room | A probe measures whether the server shortens replies when asked to think less; a per-request change waits for that and an A/B on the baselines | Probe built; A/B waits |
| Refused `python -c` | 35 refusals in one run, each a round trip | Option: the harness writes the snippet to a recorded scratch file and runs it | Owner's call |
| Budgets across restarts | A token ceiling restarted at zero after every deploy | The transcript seeds the total when a worker starts | Built 2026-10-19 |
| Stuck-stage detection | Planner repeated one tool 27 times; a withheld tool was still called | Distinct-call counting, answer-only after a withheld tool is called again, refusal of tools not offered, held-back reads counted | Built 2026-10-15/18 |
| Tool-call parsing for weak models | 32% of acceptance-author calls malformed; invented tool names | Lenient JSON repair and name mapping; the KPI counts unknown names | Built; grammar-constrained decoding not tried |
| Specification size and cost | A 205 KB specification read in windows 18 times; 127 model minutes to write | Written in parallel parts; the excerpt a stage gets keeps every section; the memory holds an outline of a large document | Built 2026-10-18 |
| Acceptance-test writing | 149 min and 182 calls on one run | Draft the suite from the criteria with a template per tier; the model fills assertions | Proposed |
| Stack setup | Setup proof failed twice and was handed to agents | Cache proven setups per stack and reuse them | Proposed |
| Review loops | A passing sprint sent back twice | Fast sends back once; a send-back must name a failing test or a criterion | Built |
| Two runs on one model server | Each call went from 40 s to 5 min | Fan-out capped at the server's slot count; readiness names the slots | Built 2026-10-18 |
| Model fitness check | A 1-bit model passed `ready` and then looped | `ready` probes tool calling and command execution; a low-bit build is flagged | Built 2026-10-18 |

## How other harnesses handle it

**More research (2026-10-24), on splitting work and limiting thinking.** Anthropic's guide says a chain makes each call an easier task and trades latency for accuracy, and to start simple and add structure only where it demonstrably helps. Cognition reports that parallel writers make conflicting implicit decisions; what works for them is writes kept single-threaded, a reviewer with a clean context, and a manager that splits big work with heavy context engineering. Agentless matched agent systems on SWE-bench Lite with a fixed pipeline of localise, repair in small edits and validate, at a fraction of the cost. ReWOO plans once and does not re-send history on each step, with reported token cuts of 64 to 80% (summaries disagree). For overthinking, ThoughtTerminator reminds a model of its remaining budget and forces an answer at the limit, and the ICML 2026 'Token Tax' paper found larger reasoning budgets raised cost over 110% on three 7 to 8B open models with negligible gain. The llama.cpp server takes a per-request reasoning budget in recent builds, with a server flag overriding it and hang reports on builds after April 2026. None of this measures splitting code-writing stages for small local models, which is why the harness tested it on its own benchmark before adopting it.

Others mostly solve the same problems with one general mechanism where this harness has grown a rung per incident. Two additions from this run: how harness studies classify fix failures, and how they ground "done" in an external check rather than the model's report.

| Challenge | This harness | Others |
| --- | --- | --- |
| Code nothing uses | No check: tests measure behaviour, so 1,883 unreached lines passed review | [Knip](https://knip.dev/) finds unused files, exports and dependencies by walking imports from entry points it infers per framework; vulture does the same for Python names. A [Microsoft ISE post](https://devblogs.microsoft.com/ise/verification-driven-tooling-prompts/) on agent-built dead-code checks warns that framework-invoked code (route handlers, registries) needs exclusions, and makes each detection class a tested contract |
| Files that fit each other | Each file drafted from the specification alone; mismatches found by the language service after drafting | [CodeTeam](https://arxiv.org/abs/2606.22082): a lead turns the design into a machine-checkable contract of file ownership, public interfaces and dependencies before developers implement under a dependency-aware scheduler. [Contract-Coding](https://arxiv.org/pdf/2604.13100) argues for contract-driven orchestration over conversational routing for repository-level generation |
| A green suite with a broken page | 62 of 62 API tests passed while the page's inputs had no accessible names; the contract probe at release found it and nothing acted on it | Playwright's planner, generator and healer agents work against the live page and its accessibility tree, so their locators are role- and name-based; axe-core scans catch unnamed controls that behaviour tests miss ([Playwright 2026 overview](https://qaskills.sh/blog/whats-new-playwright-2026), [TestMu on axe-core](https://www.testmuai.com/blog/playwright-web-accessibility-tests/)) |
| Changing tools without losing the cache | Tools are withheld by changing the offered list; 117 cache misses followed such a change | A change to the tool set invalidates the cached prefix ([Don't Break the Cache](https://arxiv.org/pdf/2601.06007)); harnesses keep the definitions fixed and mask callability outside the prompt ([Mask tools instead of removing them](https://agentpatterns.ai/context-engineering/mask-tools-instead-of-removing/)) |
| Security fixes by an agent | A security finding becomes a work order, measured by the same suite as any fix | GitHub's coding agent runs CodeQL, secret scanning and dependency review before a person sees the change ([SSOJet survey](https://ssojet.com/blog/ai-agent-security-qa-skills)); one study found iterative AI refinement raised critical vulnerabilities, so each fix is tested before it is kept ([Agentic remediation](https://softwareanalyst.substack.com/p/agentic-remediation-the-new-control)) |
| Keeping the task through compaction | Now: the stage's opening turn is carried word for word into every summary, with the files it wrote (LF.36). Before, deepagents' default replaced it with an empty summary | [OpenHands](https://docs.openhands.dev/sdk/guides/context-condenser): the condenser always keeps the first events, the system prompt and initial user messages, and summarises only the middle. [Compaction showdown](https://codex.danielvaughan.com/2026/04/10/context-compaction-showdown-coding-agents/): Gemini CLI keeps 30% of the tail verbatim; Claude Code and OpenCode clear old tool output before summarising. [deepagents #2389](https://github.com/langchain-ai/deepagents/issues/2389): the default summary drops file paths, errors and pending work; a nine-section prompt was proposed, and a custom summary prompt is the supported route |
| Loops of actions, not tokens | Repeat notes, withheld tools and an answer-only rung; a stage still repeated one reply about ten times before the rungs ended it | [Qwen agentic template for llama.cpp](https://huggingface.co/Moore2877/Qwen-Agentic-Chat-Template-llamacpp): a no-progress detector (the same result 6 times) and a ping-pong detector (the same call against the last two turns, 4 times) escalate to a demand for a materially different action. Samplers such as DRY catch only verbatim token loops, not repeated actions |
| Fixes that do not converge | Reverts, grouping, measurement at settlement, and now a write-after-12-calls rule; the medium run's fixers under-fixed and re-read | [HarnessX](https://arxiv.org/pdf/2606.14249) classes SWE-bench failures: incomplete fixes 62%, wrong diagnosis 19%, budget exhausted only 4%; it applies the gold tests first and blocks test-file writes. The lesson matches this run: the failure is under-fixing, not the budget |
| Harness versus model | One harness, one local model | A [2026 landscape review](https://learn.traeai.com/t/ai-engineering/phases/15-autonomous-systems/09-coding-agent-landscape) reports the same model at 43.2% in SWE-agent and 59.8% in Cline's scaffold; the edit-verify loop is worth tuning as much as the model |
| Trusting the model's "done" | A defect closes only when its own tests measure green after the fix; a stage's claimed changes are checked against write receipts | [Externally grounded verification](https://arxiv.org/pdf/2607.25152) in long-running loops: self-evaluation mistakes stagnation for progress; SWE-bench grades by running the tests, never by the report |
| Tool surface | Fifteen tools with guards per tool | [mini-SWE-agent](https://learn.traeai.com/t/ai-engineering/phases/15-autonomous-systems/09-coding-agent-landscape): bash only, linear history, about 100 lines, reported above 74% on SWE-bench Verified with a strong model. With a weak local model this harness goes the other way, doing the gathering itself |
| Loops and stuck agents | Many hand-built rungs (repeat notes, withheld tools, answer-only), each added after a run | [OpenHands](https://docs.openhands.dev/sdk/guides/agent-stuck-detector): one detector for 5 patterns with fixed thresholds, on by default. [Stuck-loop recovery](https://agentpatterns.ai/loop-engineering/stuck-loop-recovery/): watch a progress metric, then escalate nudge, replan, stronger model, context reset, human |
| Codebase context | Project memory: whole files up to 60k characters, served code first | [Aider](https://aider.chat/docs/repomap.html): a tree-sitter repo map of signatures ranked by PageRank, sent with every request |
| Weak-model tool calls | Repair after the fact (lenient JSON, name mapping) | [Local harness plans](https://github.com/Anharmoniclabs/NESSA/issues/3): grammar-constrained decoding, native tool templates, fewer tools; quant quality checked first |
| Long runs across sessions | Graph checkpoints, orphan recovery, decision log, Sprint Record, budgets that survive a restart | [Anthropic](https://anthropic.com/engineering/effective-harnesses-for-long-running-agents): an initializer writes a feature list with pass flags; each session does one feature, tests, logs progress, commits |
| Role pipeline | Product manager to architect, reviews, sprints, work orders | [MetaGPT](https://www.modern-datatools.com/tools/metagpt): fixed procedures per role producing PRD and design documents; strongest on greenfield CRUD apps |

Two ideas carry over. First, replace the growing set of per-incident rungs with one progress detector: a stage whose last N calls changed no file and surfaced no new fact is stalled, whatever tool it used; this run's write-after-12-calls rule is a first instance. Second, classify every failed fix the way HarnessX does (under-fix, wrong diagnosis, no edit, bad anchor, budget) in the KPI file, so the next change targets the largest class instead of the latest symptom. I found no published source on the third problem, a specification naming a server the sandbox lacks; the embedded-file default is this harness's own answer.

Environment setup is the hard part for everyone. [EnvBench](https://arxiv.org/abs/2503.14443) finds the best approach configures 6.69% of Python repositories and 29.47% of JVM ones. [Repo2Run](https://arxiv.org/abs/2502.13681) reaches 86% on 420 Python repositories by building, running the unit tests and revising its Dockerfile from that feedback until the whole pipeline runs. This harness gives its setup two attempts and, until today, fed back only the output's tail; feeding back the line that names the error is the same loop at smaller scale.

The Measure runs' false acceptance is the failure other tools guard with a start-and-smoke check before "done". [TestSprite's agent workflow](https://docs.testsprite.com/cli/getting-started/quickstart-for-agents) has the agent run the cheapest covering test against the running app and report passed, failed, blocked or inconclusive. [OpenReplay's smoke-test essay](https://blog.openreplay.com/smoke-tests-agents-writing/) (2026-09-23) argues the check must start the product the way it ships, because missing environment and setup failures never show against a mock. LF.168 applies that here: the suite starts a service through the product's own `start.sh`, the way the hidden tests and a person do.

## Adding value

**Added 2026-10-24.** Three ideas follow from the Ornith run. First, make the reply ceiling follow each model's measured tail automatically, so that a heavy-thinking model is held to a few long turns without anyone setting it. Second, report an improvement line at every audit, not only a defect line: tokens a call by stage against recent runs, the longest replies, the redundant reads. That is now `loop.sh scan` and `loop.sh patterns`. Third, tell the suite's writer to assert only what the brief requires, which would turn several release gaps into passes and make locked suites easier to satisfy for any model.

The product's promise is a build that is measured, not described. The run page now carries that: the criteria ledger with each test's result, a Changes view of every commit, what the release did not prove, steering with an acknowledgement, and a lessons panel. Three directions add more value than another guard.

1. **The planned structure, delivered as one program.** Gate run 2 passed every test with 59% of its code unreached: the fixers made a working copy in two files and left the planned modules behind. A reachability check turns "all green" into "all green and every planned module in use", and tells the next fixer which copy is real. Paired with the module contract (CM.2, EF.11), the drafts should fit well enough that no fixer needs a second copy.
2. **A product someone can use, not only an API that passes.** The findings run delivered a service that passes every test and a page whose sign-in fields a screen reader cannot name and whose views no link can reach. A release that names "the page keeps 1 of 10 contract lines" as a defect, with a fixer sent to it, turns the contract the planners already write into delivered value. An accessibility scan of the rendered page in the same step costs one command.
3. **A progress contract per stage.** Each fix stage states, before it starts, which test it will turn green; the harness measures that test and nothing else decides. The run page shows the contract and the result side by side. This turns 25 fix stages into a readable list of promises kept or not.
4. **Classified failures in the KPI.** Every failed fix tagged under-fix, wrong diagnosis, no edit, bad anchor or budget. Across runs the largest class names the next change, and the owner can see whether a change moved it.
5. **Baselines before features.** The owner's two baseline runs (fast `notes-api-hono`, then fast `fullstack-bookmarks-py`) on this code are the only way to tell which of the twelve fixes from this run mattered. Nothing in the fix loop should change again until they have run.
6. **A summary that says where the stage stands.** With the request now kept, the summary itself is the next gap: a structured one (what was asked, files changed, errors met, what is left) in place of free prose, as deepagents #2389 proposed. A fixer resumes from "two of three files written, the build fails on a missing package" instead of reading the workspace again. Its value shows in the gate runs' redundant reads after a compaction.

The open owner decisions that change value most: whether refused `python -c` snippets become a recorded scratch run (saves about 35 round trips a run), and whether the reasoning probe may use the model server between runs.

## Sources

The run's own records: `data/kpi/run-8b0c94df-eff4-47f2-82c8-0ad06b7c5285.json`, `docs/monitoring-handover.md` §0.2 (2026-10-18 and 19), and the ledger in `docs/improvement-plan.md` (Appendix 3 rows).

- [HarnessX: A Composable, Adaptive, and Evolvable Agent Harness Foundry (arXiv 2606.14249)](https://arxiv.org/pdf/2606.14249), the failure classes
- [When Do Agent Loops Mistake Stagnation for Progress? (arXiv 2607.25152)](https://arxiv.org/pdf/2607.25152), externally grounded verification
- [From Question Answering to Task Completion: A Survey on Agent System and Harness Design (arXiv 2606.20683)](https://arxiv.org/pdf/2606.20683)
- [The Autonomous Coding Agent Landscape (2026)](https://learn.traeai.com/t/ai-engineering/phases/15-autonomous-systems/09-coding-agent-landscape), the SWE-agent versus Cline figures and mini-SWE-agent (secondary)
- [OpenHands stuck detector](https://docs.openhands.dev/sdk/guides/agent-stuck-detector), [Stuck-loop recovery](https://agentpatterns.ai/loop-engineering/stuck-loop-recovery/), [Aider repo map](https://aider.chat/docs/repomap.html), [Anthropic on long-running agents](https://anthropic.com/engineering/effective-harnesses-for-long-running-agents), [MetaGPT](https://www.modern-datatools.com/tools/metagpt), [NESSA local-harness plans](https://github.com/Anharmoniclabs/NESSA/issues/3)

Environment setup, read 2026-10-19: [EnvBench (arXiv 2503.14443)](https://arxiv.org/abs/2503.14443), [Repo2Run (arXiv 2502.13681)](https://arxiv.org/abs/2502.13681). Baselines: `data/bench/run-419b8ff6-….json`, `data/bench/run-c00868a9-….json` and their KPI files in `data/kpi/`.

The 2026-10-20 update: `data/kpi/run-894282e3-a188-4d10-8ead-72ddb889935e.json`, `docs/improvement-plan.md` Appendix M (LF.35-LF.38), and the pages opened for it - [OpenHands context condenser](https://docs.openhands.dev/sdk/guides/context-condenser), [Context compaction showdown](https://codex.danielvaughan.com/2026/04/10/context-compaction-showdown-coding-agents/), [deepagents issue #2389](https://github.com/langchain-ai/deepagents/issues/2389), [Qwen agentic chat template for llama.cpp](https://huggingface.co/Moore2877/Qwen-Agentic-Chat-Template-llamacpp).

The 2026-10-22 update: `data/bench/run-650d812f-e521-42cd-abdf-a8509facb3e6.json`, `data/bench/run-aedcd228-e168-4387-94bb-6edf95885849.json`, `docs/STATE.md`; [TestSprite quickstart for agents](https://docs.testsprite.com/cli/getting-started/quickstart-for-agents), [Smoke Tests and Why Agents Keep Writing Them](https://blog.openreplay.com/smoke-tests-agents-writing/).

The landscape figures are from a secondary write-up and are marked so; the two arXiv papers were read for their stated numbers only.

Added 2026-10-24: [Anthropic, Building effective agents](https://www.anthropic.com/research/building-effective-agents); [Cognition, Don't Build Multi-Agents](https://cognition.ai/blog/dont-build-multi-agents) and [Multi-Agents: what is working](https://cognition.com/blog/multi-agents-working); [Agentless](https://arxiv.org/html/2407.01489v2); [ReWOO](https://arxiv.org/pdf/2305.18323); [ThoughtTerminator](https://arxiv.org/html/2504.13367v1); [Token Tax (ICML 2026)](https://icml.cc/virtual/2026/67957); [llama.cpp reasoning budget](https://github.com/ggml-org/llama.cpp/pull/25961). The ReWOO, ThoughtTerminator and Token Tax figures come from secondary summaries and are marked so.

## Run run-1722a1ee (Hono on Node-native TypeScript, arm run 1), 2026-10-25

**Result.** Hidden 0 of 9; the run stopped at 19:45 JST (escalation: more than half undelivered, after three sprint attempts). Locked suite 2 passed, 22 failed. Tool-call failure rate 34% against a 5-run mean of 16%, 8 fixes reverted against 3.2, 26 defects left open against 10.2. This is the sixth run on this stack with this model (gpt-oss-20b): five on the Jest pack scored 1/9, 0/9, 0/9, 0/9, 0/9. One sample of the arm; judge the arm on three.

**What the harness got right.** Two harness faults were found and fixed during the run. (1) The team's own start script ran a module that defines the app and never listens; Playwright's web-server timeout was read as a suite that proved nothing, and QA was sent back five rounds in twenty minutes for a file it does not own (LF.276 reads the timeout as the product's defect; LF.277 has each service pack write and keep its own start script). (2) Relative imports without the .ts extension (WM.3, adds them for Node). After the fixes the product started and listened.

**What it did not fix.** The model kept writing names that do not exist: a `json` export from `hono` and an `expect` export from `node:test`. The language-service gate rejected every rewrite (8 reverts), so no fix survived. The harness named the package's real exports 24 times (WM.1); the model ignored them. The `module_exports` tool was available and called 0 times in 149 tool calls. Telling this model the facts is not enough; it needs the loop closed around it.

**Features to improve.**

- A compile-and-fix loop for weak tiers (step C): a fixer's rewrite is typed against the compiler before it is accepted, and the compiler's own messages, with the exports list, go back for up to three tries inside the one fix. Today the gate reverts the whole rewrite, and the next fixer starts from the same defect text.
- Make the facts unavoidable instead of optional: put the real export list of every package a file imports at the top of the drafting and fix request, rather than a tool the model may skip.
- The harness-owned files (start script, runner config) should be written before the first measurement of a stage, so a stage that rewrites one is not measured on the broken copy.
- Weak-tier fixers fail on multi-file faults; pass the failing line and the declared type with each defect.

**How others handle it.** SWE-agent (Yang et al., 2024, arXiv 2405.15793) puts a linter inside the edit command: a syntactically invalid edit is rejected with the linter's message and the agent retries at once, which the authors measured as a gain. Aider runs the project's linter and tests after each edit and feeds failures straight back to the same model call. Both close the loop inside the step, rather than reverting after it. Not re-researched this run; these are the references the plan already cites.

**Value to the product.** A service that starts from a single script, with a typed check on every file before the suite sees it, is what a customer can run. The two start-path fixes apply to every service pack, not only Hono.

**Next.** Run the arm twice more on the deployed harness (WM.4, LF.276, LF.277), then ask the owner whether to build step C.

## Run run-3af73c9e (Hono on Node-native TypeScript, arm run 2), 2026-10-25

**Result.** Hidden 9 of 9, the first pass on this stack with this model after six runs at 0 to 1 of 9. Released 21:15 JST after 80 minutes; locked suite 19 passed, 1 failed (AC-13, deferred). The arm run 1 failure to start was the harness's: with LF.276/277 in, this run's product started from its first round and the criteria passed went 12, 12, 14, 17 of 18. Mutation score 0.25 against a mean of 0.54: the suite is weak, so the 9/9 is better evidence about the product than about the suite.

**What worked.** The arm (no Jest, no compiler step), the pack-written start script, the extension repair (WM.3), the revert gate and best-attempt undo. Tool-call failure rate fell from 34% to 20%.

**What still wasted time.** (1) AC-13: QA's locked test is titled "returns 400" but asserts exactly 422, while the criterion allows 400 or 422; the product was right, every fixer was reverted, and four sprint attempts (about 35 minutes) ended with AC-13 deferred. (2) Every sprint plan went back to the lead three times for naming the specification, which lives in the workspace docs (fixed, LF.279). (3) A fixer flipped `./app.ts` to `./app.js` and was told its tests still failed (fixed, LF.278). (4) 67% of reads were redundant.

**Features to improve.** A deterministic QA-review check that a test must not pin one status code when its criterion allows two, and that a test's title and its assertion agree. A fixer that is reverted on the same locked test twice should hand that test to the dispute path at once instead of a new sprint attempt.

**How others handle it.** Test-first agent setups (for example the SWE-bench style "fail-to-pass" and "pass-to-pass" split) treat a failing test that a reference solution also fails as a bad test, and drop it; the harness's dispute path is the same idea but runs only after the sprint attempts are spent. Not re-researched this run.

**Next.** Run 3 of the arm (started 21:20, on LF.278 and LF.279), then decide with the owner whether step C is still needed: one pass in two runs does not yet say the arm is reliable.

## Run run-bd665b9a (Hono on Node-native TypeScript, arm run 3), 2026-10-25

**Result.** Hidden 9 of 9 again; locked suite 12 passed, 0 failed, released 22:05 JST after 45 minutes, with 5 gaps recorded (AC-15, the start-script criterion, shipped deferred as "no automated test can verify start.sh"). The arm now reads 0, 9, 9 of 9 against 1, 0, 0, 0, 0 for the Jest pack with the same model; the one zero was the run in which the start-path faults were fixed mid-run.

**What the run showed.** The first 25 minutes read 0 of 18 criteria because the product did not start: the model imported a name that does not exist in a Node built-in (`promises` from `node:fs/promises`) after a path Hono does not export (`hono/middleware`). Fixers were shown only the runtime crash, one fault at a time, while `tsc --noEmit` listed 14 errors in the same files and the harness's language-service pass reported none of them. Once the product started, the criteria passed rose 5, 17 and 17 of 18 within eight minutes, then a bad rewrite dropped it to 0 and the best-attempt undo restored 16.

**Features to improve.** (1) When the product does not start and the pack has a typecheck command, append the compiler's errors to the start defect, so a fixer sees every missing name at once. This is the light form of the compile-and-fix loop and would have cut the first 25 minutes. (2) The language-service pass misses "has no exported member" on Node built-ins that `tsc` reports; teach the hint list about `node:` modules from the installed type files. (3) A criterion whose evidence is a script or file (AC-15) should be tested by a harness-written check, not left untested and counted as a known gap in every run.

**How others handle it.** SWE-agent puts the linter inside the edit tool and rejects an invalid edit with the linter's message, so the agent never leaves a broken file; Aider feeds lint and test output straight back to the same call. Both give the model the whole list of errors, not one at a time. Not re-researched this run.

**Value to the product.** Every service pack now writes and keeps its own start script, so the customer's way of starting the product is the one the harness tests.

**Next.** Decision for the owner: the arm is at two clean passes of two clean runs; make it the default for Hono, and build (1) as a measured switch.

## Run run-da181ab6 (Hono on Node-native TypeScript, run 4), 2026-10-26

**Result.** Hidden 9 of 9, yet the harness stopped the run as failed after 111 minutes: locked suite 5 passed, 20 failed, 50 defects left open (mean 14). The product passed every hidden test; the suite QA locked did not match it. Arm record: 0 (mixed), 9, 9, 9 of 9.

**What the run showed.** The harness's own measurement was the failure, not the product. QA's locked suite was reopened four times (4, 9, 2 tests that cannot pass), grew from 12 to 25 tests, and still measured 6 of 18 criteria for over an hour while the model's fixers rewrote working code to satisfy tests that were wrong. The same pattern as AC-13 in run 2 (a test pinning 422 where the criterion allowed 400 or 422), at a larger scale. The product was reported as 6 of 18 and passed 9 of 9 hidden.

**Features to improve.** (1) Measure the suite against something independent before the build starts: the harness already knows a locked suite must pass a reference product; for a small model with no reference, run the suite against the first drafted product and treat tests that fail with a 404 or a connection error on every route as the product's (not started), and tests that fail with a wrong status on a correct route as suspect. (2) Stop the build loop when criteria passed has not risen for two fix rounds and the fixers' changes are being reverted: today the run continued 60 minutes at 6 of 18. (3) A locked test whose title and assertion disagree, or that pins one status where the criterion allows two, goes back to QA at the review, not to a fixer.

**How others handle it.** Benchmarks such as SWE-bench validate their tests against a known-good patch before a task is used, and drop tests that a correct solution fails; the harness has no known-good patch, so it needs the cheaper check in (3) and the stall rule in (2). Not re-researched this run.

**Next.** Run 5 starts on LF.280, LF.281 and LF.282 (bootstrap kept, compiler errors in the start defect, `node:` exports checked).

## Run run-e87f05e1 (Hono on Node-native TypeScript, run 5), 2026-10-26

**Result.** Hidden 8 of 9; released 00:55 JST after 34 minutes, the fastest run on this stack. Locked suite 7 passed, 2 failed, 11 gaps recorded; the harness marked it FALSE ACCEPTANCE because it finished a product that fails a hidden test. The miss is `DELETE /notes/:id` returning 204, which the release itself listed as deferred (AC-5 deferred at the escalation, AC-12 as a gap). Arm record: 0 (mixed), 9, 9, 9, 8 of 9.

**What worked.** The compiler's missing-name list in the start defect (LF.281) fired in its first live run, and with the package-path hint (deployed 00:21) the product first started within about 17 minutes of the run, against 25 to 35 in runs 3 and 4. The kept `src/main.ts` (LF.280) removed the host typo class. The best-attempt undo restored 7 passing tests after a bad rewrite.

**What it shows.** The deferral is honest, and the release says so (it lists the unproven criterion); the false acceptance is the harness reporting a deferred, known-failing criterion as a completed run. A deferred criterion that the hidden tests name should be what keeps a run from reading as complete. Whether to hold a release for a deferred delete endpoint is a policy choice: today the run stops after two escalations to avoid an unbounded loop.

**Features to improve.** After the escalation defers a criterion, run one cheap final attempt aimed at the deferred criterion alone, with the compiler's errors and the route list in view, before release. DELETE was a missing handler; a fixer given only that, and the contract, is the case the single-call rewrite handles well.

**Next.** Run 6 on the same harness for a second clean sample of LF.280-282.

## Run run-3e3fc698 (Hono on Node-native TypeScript, run 6), 2026-10-26

**Result.** Hidden 9 of 9; released 01:54 JST after 56 minutes; locked suite 19 passed, 1 failed (AC-18, deferred); 8 gaps recorded. Arm record: 0 (mixed), 9, 9, 9, 8, 9 against 1, 0, 0, 0, 0 for the Jest pack with the same model, so the arm became Hono's default (LF.283).

**What the run showed.** Attempt 1 read 0 of 18 for three rounds (the product did not start); the redraft after the re-plan started it and the criteria passed went 1, 16, 16, 17 of 18 within 25 minutes. The persistence criterion (AC-17) and the start-script criterion (AC-15) were again untestable by QA, which reopened the suite twice for them. AC-15 has been the unprovable criterion in runs 2, 3, 5 and 6.

**Features to improve.** (1) A harness-written check for start-script criteria (the pack writes the script and keeps it, so the harness can run it and answer the criterion itself): removes AC-15 from every service run. (2) A restart check for persistence criteria: the harness stops and restarts the service on the same data directory and reads the notes back. (3) When attempt 1 reads 0 of 18 for three rounds, the redraft after the re-plan is where the product finally started; offering the compiler's list at the first round (LF.281) should bring that forward, which run 6 did not show, since its attempt 1 still started late.

**How others handle it.** Agent harnesses that grade by hidden tests (SWE-bench style) never ask the model to prove a criterion that needs the environment; the harness proves it. Not re-researched this run.

**Next.** A tasks-api run (Python) to check that the changes made for this stack (start script in every service pack, the project contract applied before a fixer's check) did not regress other packs.

## Run run-64003f38 (Hono on Node-native TypeScript, run 7, the default arm), 2026-10-26

**Result.** Hidden 9 of 9 and the harness agrees: locked suite 19 passed, 0 failed, completed in about 30 minutes, the fastest run on this stack. 15 gaps recorded (AC-2 listed as open at lock time). Arm record: 0 (mixed), 9, 9, 9, 8, 9, 9. The first run with the Native-TS pack chosen by default and the compiler's errors in the start defect from the start: the product started within 8 minutes and all 18 criteria passed from the eighteenth minute.

**What the run showed.** After the product was done, the run spent the remaining time on a unit test the model wrote itself (tests sharing a temporary folder, `loadNotes` on malformed JSON), re-planning the sprint twice with all 18 acceptance criteria green. The re-plan limit, not the evidence, was what ended it. LF.284 (`SETTLE_WHEN_ACCEPTANCE_IS_GREEN`) now sends a sprint with a fully green suite and only unit tests open to the escalation after one re-plan; shipped after this run finished, so run 8 is its first run.

**Features to improve.** (1) The model's own unit tests are the new weakest link on this stack: they fail on shared state between tests. Giving each unit test its own temporary directory in the pack's smoke test and guide is a one-line pack change. (2) A unit test that fails beside a green acceptance suite is a known issue the release already records (RL.1); nothing else should depend on it.

**Next.** Run 8 on LF.284; then the stall rule for a suite that does not rise (not built, awaiting the owner).

## Run run-ba177ced (Hono on Node-native TypeScript, run 8), 2026-10-26

**Result.** Hidden 8 of 9; completed in 46 minutes; locked suite 10 passed, 0 failed, flagged FALSE ACCEPTANCE; 11 gaps. The miss is `test_notes_survive_a_restart` (404 after a restart): the product kept its notes in memory. Arm record: 0 (mixed), 9, 9, 9, 8, 9, 9, 8.

**What the run showed.** The suite was green and the product lost its data. QA marked both persistence criteria (AC-6, AC-17) as "cannot be verified in the current test harness as the server runs once per suite" and the release shipped them deferred, which is why the harness cannot see the one fault the hidden test checks. The same excuse appeared in at least five runs; in run 5 the hidden miss was a different deferred criterion (DELETE). A criterion QA declares unprovable is where the hidden tests find faults.

**What was built (LF.285).** Every Node-run service pack now writes and keeps `acceptance/service.cjs`, a helper that starts the project's own `start.sh` on a free port and a data folder the test names, and the QA guide says a restart criterion is tested with it, not deferred. The helper was run for real in a test (start, write, stop, restart on the same folder, read it back; a fresh folder reads nothing).

**Features to improve.** (1) Treat a deferred criterion QA called unprovable as a harness gap to close: list the deferred criteria with their reasons at lock time and at release, and for each class (restart, start script) provide the capability rather than accept the deferral. (2) Python and other non-Node services have their own conftest; the same restart capability should be added there when a run shows the same excuse.

**How others handle it.** Agent benchmarks that grade by hidden tests give the agent the same environment the grader uses; here the grader restarts the service and QA could not. Not re-researched this run.

**Next.** Run 9 on LF.285.

## Run run-44044cb4 (Hono on Node-native TypeScript, run 9), 2026-10-26

**Result.** Hidden 8 of 9; released 07:25 JST after 64 minutes; locked suite 13 passed, 3 failed; 11 gaps; FALSE ACCEPTANCE flagged. The miss is `DELETE /notes/:id` answering 500 (AC-5 and AC-12 shipped deferred). The persistence test passed this time: QA wrote `persistence.spec.js` with the restart helper (LF.285), the product kept its notes, and the hidden restart test passed, where run 8 failed it. Arm record: 0 (mixed), 9, 9, 9, 8, 9, 9, 8, 8.

**What the run showed.** The first 55 minutes read 0 of 18 criteria, the slowest start of any run since the arm began, from three faults in sequence that the compiler could have named at the first round: a changed `tsconfig.json` (so `tsc` printed only a configuration error and the fixers saw no compiler list), a router given to `app.use` instead of `app.route` (every request threw), and the health route mounted at `/health/health` (the readiness request got a 404). The first two are fixed in general (the pack keeps `tsconfig.json`; the compiler list keeps argument and overload mismatches, product files first, LF.281); the third is the model's, and the harness's start defect already says the request was answered 404 and the route is not served where the suite asks. Once the product answered, criteria passed went 13, 15, 15 and the escalation accepted the sprint.

**What is left.** DELETE answered 500 in this run and was deferred in run 5 as missing: twice the hidden miss is the same endpoint. A 500 has a cause in the service's own output, which the harness reads for Python services (LF.274) and does not for Node ones: Playwright prints it in the run's console, not in a file the failing test can quote.

**Features to improve.** Give the Node service packs the same service-log capture, so a test that met a 500 carries the error the service printed; this needs the web server's output kept in a file without losing the start-crash text the harness reads from the console. Not built.

**Next.** notes-api-js, another Node service pack, to see LF.277 and LF.285 on a pack they also touch.

## Deep review of the harness, 2026-10-26 (owner request)

**Data used.** The 19 scored runs since the model change (2026-10-25 06:41 to 2026-10-26 07:54 JST): hidden scores against the harness's own verdict, the defect ledger (338 defects), output tokens and wall time by stage family, 922 failed tool calls, mutation scores, completion gaps, the KPI ledger, the QA suites in the last five Hono workspaces, and the code of the acceptance, fix and planning paths. An independent code review runs beside this and is appended when it lands.

### 1. Where the harness stands

| Measure | Value over the 19 runs |
| --- | --- |
| Hidden score | 9/9 or 10/10 in 12 runs; 8/9 in 3; 7/8, 3/8, 3/10, 0/9 once each |
| Harness verdict agrees with the hidden tests | **12 of 19**. 4 runs scored 9/9 and the harness stopped them as failed (locked suite 3 to 8 of 10 to 28 passing); 5 runs were released and failed a hidden test (false acceptance) |
| Output tokens by stage | defect fix **41%** (2,989 calls), QA suite 18.6%, drafting 10.7%, architect 7.5%, lead 7.2%, specialists 6.4% |
| Wall time by stage | defect fix 17%, drafting 15%, QA suite 13%, lead 12%, specialists 8.5%, acceptance review and dispute 10% |
| Fix attempts (ledger) | 32 fixed; 92 reverted (every one an agent-loop fixer); 172 left open with own tests failing; 220 left open at exhaustion; 40 changed nothing. Single-call rewrite fixers: 21 fixed, 0 reverted |
| Defects by source | acceptance suite 238, test round 61, language service 22, cross-file 8, mutation 7 |
| Mutation score of the locked suite | median 0.5; two runs of 17 at 0.83 or above |
| Failed tool calls | 922: ambiguous or missing edit anchor 295, write outside own files 119, syntax 108, missing name at write 99, harness-owned file 68 |
| Context per call | fixers 33k to 44k input tokens a call, QA 25k to 43k, drafting 2k to 8k; prefill-to-decode ratio 47 to 83; redundant reads 55% to 79% |

The product is now usually right. The harness's own measurement is what is most often wrong, and the fix stage is where most tokens go for the least return.

### 2. Findings, ranked by value for effort

**F1. The locked QA suite is red for its own reasons, and the harness cannot tell.** Four 9/9 products were stopped as failed. In the last two, every failing assertion was `Expected: 201 Received: 400` or `200/404`: QA called Playwright's `request.fetch(url, { body: ... })`, and that API takes `data`, so the service received no body. The suites also started their own service with the restart helper in most tests (13 of 10 tests' worth of calls in one suite, 9 in another), which the helper's guide invited by saying "write through baseURL with fetch". The live run shows the same pattern. Change: (a) a deterministic review check that a `request.*` call with a `body:` option cannot pass, with the correction; (b) the restart guide names the helper for the restart criterion only and the `request` fixture with `data` for everything else; (c) at lock time, run a harness probe of the product's own contract (POST then GET on the specification's first endpoint) and treat a suite that fails every write while the probe succeeds as suspect, sending it to QA before any fixer runs. Small; the first two today.

**F2. The fix stage spends 41% of tokens to fix 15% of what it is given.** Agent-loop fixers were reverted 92 times and fixed 11; the single-call rewrite fixer fixed 21 and was never reverted. A round dispatches one fixer per defect, serially, 10 to 16 a round at about 3 minutes each, often all aimed at one file. Change: rewrite-first for a defect localised to one file; the agent loop only when the rewrite fails; group defects by localised file into one fixer; and do not dispatch fixers at all while the suite is suspect (F1c). Expected: the fix stage's time and tokens roughly halved.

**F3. Deferred criteria are where the hidden tests fail.** Of 5 false acceptances, 4 shipped the failing behaviour as a deferred criterion (DELETE twice, persistence, DELETE again). Change: one final single-call rewrite aimed at the deferred criterion alone, with the compiler's errors and the route list, before release.

**F4. Reasoning effort is the server's, and one setting change made replies ten times longer.** The harness sends no `reasoning_effort`. Change: send it per stage for models that take it (low for drafting and fixers, medium for the architect and QA), measured as an arm. This is also the lever the work-batching plan wanted.

**F5. Planning churn.** The lead's plan is sent back two or three times per sprint; a re-plan redrafts files that pass tests (RD.1: three products wrecked in one night, undone by the best-attempt gate at a round's cost each); plans assign UI/UX and documentation work orders to a service. Change: a plan check that refuses roles the stack has no surface for; a redraft that leaves files whose tests pass untouched.

**F6. The suite's own strength.** Mutation median 0.5. For `http_api` products the specification already holds paths, status codes and shapes; the harness can generate skeleton tests per criterion from that table and have QA fill values only. This also removes the `body:`/`data` class and the AC-13 "400 or 422" class at the source.

**F7. Edit-tool ergonomics.** 295 refusals for an anchor that does not match or matches several times, in 20 runs. Change: when the anchor matches exactly once after whitespace normalisation, apply it; when it matches several times and the model gave a line hint, apply at that line; otherwise the present refusal.

**F8. Context cost.** Fixers carry 33k to 44k input tokens a call (the product's whole API, the shared facts, the failure output, the ledger), and more than half of reads re-read a file already in the context. Change: send the API section once per stage and refer to it; put the file digest in the request so the model does not read it again. Prefill is the local server's cost; model-busy share is already 0.62 to 0.98.

**F9. Ledger blind spot.** The ledger records a defect's one-line description and outcome, not what each fixer was shown, so "why did the second try succeed" cannot be answered from data. Change: record a fingerprint and a 300-character summary of the fix request with each attempt.

**F10. Operational hygiene.** The restart helper leaked 130 services and took the worker down (fixed today, LF.288); the worker runs one pool process with no memory watchdog; `loop.sh score` with a short run id exits 0 and prints nothing; the run status timestamp lags the worker. Change: a memory and orphan check in `loop.sh ready`, and `score` refusing a short id.

**F11. Browser family.** fullstack-bookmarks 3/8: locators by `data-*` attributes nobody sees, two UI tests reclassified. The page-selector contract shared between QA and the drafted page (on the candidate list since the start of this session) is the fix; the service families do not need it.

### 3. What is working and should stay

The start-path fixes (kept `start.sh`, `main.ts`, `tsconfig.json`; the compiler's errors in the start defect; builder facts) moved the product's first start from 25 to 60 minutes to about 10. The revert gate and best-attempt undo protected every run that reached a good product. The stall rule and the settle-when-green rule ended runs that would have cycled. The Native-TS arm is 9/9 on 9 of 11 clean runs. The Python, Express, CLI and library families all passed on the same harness.

### 4. Order of work proposed

1. F1 (a) and (b) now; F1 (c) behind a switch. 2. F2 rewrite-first and group-by-file, behind a switch, measured on two Hono runs and one tasks-api. 3. F3. 4. F4 as an arm. 5. F7 and F9 (small). 6. F5, F6, F8, F11 as measured arms in that order.

### 5. Independent code review (a fresh reader of the control flow, same day)

A second reviewer read the graph, acceptance, fix, tool and model layers without seeing the findings above. Its points, checked against the code where cited:

- **The suite is run two or three times on an unchanged tree per round** (`ci.take` after every fix, then `acceptance_for_round`, then the unit tests again on the fast path). `suite.last_result` already keeps a git fingerprint; returning the saved result when nothing changed saves one or two suite runs a round and one per fix. Low risk; the harness already classes a flip on the same tree as instability.
- **The redraft after a re-plan rewrites every planned file unconditionally** (`draft_work_orders`, no "exists and passes" gate), which is why the best-attempt undo fires and costs a round each time; on one model the "different model for this attempt" ladder changes nothing. Skip files present at the best commit. This is F5's RD.1 with the exact mechanism.
- **A repair may drop an assertion**: `tests_a_repair_would_drop` compares test names only. Count assertions per repaired test old against new, and send back a repair that removes one or removes a literal the criterion text states (the wordstats tie case). Small.
- **A "too specific" pre-lock check**: a 3+-word string literal or a 4xx code asserted by a test whose criteria text does not contain it, advisory, capped at 6.
- **The dispute's per-file re-run runs every acceptance file** though `each_file` takes `naming`; one-line fix.
- **The per-defect probe is duplicated** (once per candidate, again in `_fix_one`) and runs even when the tree is unchanged.
- **Reply pacing after a slow cut-off applies only to llama.cpp** (`max_retries == 0` set only for `speaks_llama_cpp`); LM Studio gets three identical retries. Set it for any local OpenAI-compatible server.
- **Batch measurement labels never count as "measured since"** (`passing_since_reported` regex takes `_\d+`, batches are `_batch`), so in parallel mode a defect fixed as a side effect is never closed without a fixer.
- **Three rungs of fix escalation collapse to one on a single-model deployment**; make the last rung mean "defer this defect".
- **Release with a "disputed suite" gap when the stall fires and every failing locked test has been blamed by two or more fixers with repairs spent**, instead of failing the run: the highest-value and highest-risk item, which only the hidden tests can judge.
- Dead or duplicated code: an orphaned docstring under `MAX_SPECIFICATION_REPAIRS`; `test_and_triage_node`'s docstring after code; `_fix_one`, `defect_fix_worker_node` and `defect_fix_gather_node` duplicating agent construction and settlement; `what_the_files_already_prove` computed twice with the same arguments; three copies of "start the sprint over" (escalation, re-plan, release).
- Latent bugs: `cannot_pass` bound only inside a branch; `contract.enforce` inside the fixer's test check can write files after the instability fingerprint was taken; a dispute raised from the earlier-fix check skips the unstable defect for the rest of the round.

Taken together with section 2: the memoised suite run, the no-redraft-of-passing-files rule, the assertion-drop check and the batch-label fix are small and safe enough to go first; the "disputed suite" release needs an arm and the hidden tests as judge.

## Runs of 2026-10-27 (gpt-oss-20b, notes-api-hono, fast delivery)

| Run | Harness | Hidden | Locked suite | Wall time | What decided it |
| --- | --- | --- | --- | --- | --- |
| run-155772c1 | builder facts, fetch-body check, MEASURE\_ONCE | 9/9 | 16/3 (3 deferred) | 40 min | the saved suite run was reused 6 times |
| run-d2a086bd | mixed from 02:34 (START\_PROBE) | 9/9 | 17/0 | 56 min | 0/18 for 40 min (`/health` 503 without a data folder), then the start probe's output reached the fixers and the product passed in about 10 min |
| run-eabc53e3 | clean | 9/9 | 9/1 (2 deferred) | 33 min | a re-plan wrecked 8 tests to 2 and the undo put 6 files back, because the first keep-the-best rule kept only 1 file |
| run-fed7ffd6 | mixed (LF.298-301 deployed into it) | 9/9 | 17/0 | 61 min | the product did not start for 25 min, the suite was repaired twice, and 4 of 5 fixes in one attempt were reverted |

Four runs in a row reach 9/9 on the hidden tests. Wall time, not correctness, is now the gap. Two causes cost the most time:

- runs where the product does not start;
- fixes that break what passed.

### What run-fed7ffd6 showed, and what was fixed

- **The harness repaired imports only when it measured.** The drafted tests imported `../src/datastore.js` where `datastore.ts` exists. The two testing work orders then spent 55 calls, 30 of them refused, on writing a `.js` re-export and editing files they did not own. **LF.298** (`EXTENSIONS_BEFORE_A_RUN`) makes the same repair before every command a stage runs, and the command's result says it did.
- **The start defect dropped the one error that mattered.** The service crashed with `does not provide an export named 'Note'`, an interface imported without `type`. The compiler reported it as TS1484, but the defect's compiler list kept only another error. **LF.299** keeps TS1484/1485.
- **One false-red test was not seen.** `expect(response.status).toBe(201)` compares a function with 201 and fails on every product. **LF.300** counts it among the tests that cannot pass, so QA repairs it before a fixer is charged with it.
- **Three fixes in a row declared `const body` twice in one handler.** The write guard used only the TypeScript parser, which does not report this, and `node --check` on a `.ts` module skips function bodies. Each fix was reverted for breaking 25 tests. **LF.301** strips the types the way Node does and checks the JavaScript at the write. Syntax Node cannot strip, such as `enum`, is named too.
- **The refined re-plan rule (LF.295) fired.** It left 2 files exactly as the best attempt had them (14 of 17 passing), and the next round reached 18 of 18.

### Features to improve next

1. **Fast delivery rewrites whole files from the failure (deep-review item F2).** Four of five fixes in one attempt were reverted. Each was a whole-file rewrite that lost a working part, which the revert gate then had to restore. Next, behind a switch: an anchored edit first, with a whole-file rewrite only when the file is small or the edit cannot apply. Fixes should also be grouped by file, so two defects in `app.ts` are one change.
2. **Unit tests that the same model wrote.** The run released with 3 of its own unit tests failing, including "a corrupted file should give an empty data set". The acceptance suite and the hidden tests agreed the product was right. A unit test that disagrees with a passing locked suite should go back to its author, as acceptance tests already do, rather than to a product fixer.
3. **The service's first write failed in the fixer's own probe.** The code wrote `NOTES_FILE.json` under a data folder that did not exist. The start probe already starts the service; a probe that also makes one write request would find this class of fault before the suite does.
4. **The release's "interface contract" check disagreed with the hidden tests.** It reported that AC-1 POST was not kept. Either that check is reading a contract line it cannot parse, or it is too strict. It should be audited before it is trusted as a release gap.

### How other harnesses handle the same problems

- **Checking on every edit.** In 2026 the common practice is to type-check and lint on every edit and give the agent the error: an LSP diagnostics loop, Pyrefly wired into Claude Code through hooks, and a six-layer lint harness for TypeScript monorepos. The shared principle is that a bug class that can be caught mechanically never reaches review. The harness now does this for Node-run TypeScript (LF.301) and already refuses writes that add errors the language service is sure of. It refuses at the write rather than only reporting afterwards; I found no other harness described as doing that as standard practice.
- **Wrong oracles in generated tests.** Recent work finds that about half of generated tests fail, mostly because the expected value is wrong, not the code. The leading approaches have three steps: generate, validate the oracle against execution or mutants, and repair rather than discard (YATE, AugmenTest, Nexus). The harness's "tests that cannot pass" checks are the rule-based half of this. The missing half is checking the oracle against mutants: does a locked test fail on a mutated product and pass on the real one? The mutation score the harness already computes at the end could gate the suite at lock time instead.

### Adding value to the product

- **Time to green.** Four 9/9 runs took between 33 and 61 minutes. A per-run "minutes lost to start failures / to reverted fixes / to suite repairs" line in the run summary would show the owner where each run's time went. The data is already in the defect ledger.
- **Release notes from the record.** Each run now knows which criteria were proven, which were deferred, and which unit tests ship failing. Putting these in the shipped README as a known-limitations section would give the product's user the same honesty the Sprint Record gives the owner.

Sources: [Six-layer lint harness](https://understandingdata.com/posts/six-layer-lint-harness-case-study/), [LSP diagnostics loop](https://noqta.tn/en/blog/lsp-diagnostics-ai-coding-agents-feedback-loop-2026), [Type errors for agent-assisted development (PyCon DE 2026)](https://pycon.de/archive/2026/talks/type-errors-for-better-agent-assisted-development/), [Sentry: guardrails over prompts](https://workos.com/blog/sentry-greg-pstrucha-stop-prompting-agent-guardrails), [LLM test generation with newer models](https://arxiv.org/pdf/2601.09695), [Nexus: test oracle synthesis](https://arxiv.org/pdf/2510.26423), [AugmenTest](https://conf.researchr.org/details/icst-2025/icst-2025-papers/25/AugmenTest-Enhancing-Tests-with-LLM-driven-Oracles), [YATE](https://www.emergentmind.com/topics/yate).

## run-3fb91b4f (2026-10-27 04:38-05:50 JST): hidden 9/9, locked 17/0, 72 min

This run was mixed: LF.302 and LF.303 were deployed into it. Its time went in two blocks:

- **About 30 min on a suite no product could pass.** QA rewrote three working `data:` bodies as `json:`. Playwright's `request` fixture has no `json` option (only `route.fulfill` has one), so those requests sent no body. AC-1, 13, 16 and 18 were charged to the product, and six fixers in a row failed or were reverted. **LF.302** catches the `json:` option. At the next round the suite was sent back with the exact lines, and QA's repair took it to 18 of 18.
- **About 30 min with acceptance green.** The suite stayed at 18 of 18 for four rounds while fixers worked on the model's own unit tests: an error handler answering "Internal Server Error" where its test wanted an empty body, and a loader that logs a parse error. Settle-when-green missed these because it only recognised its own wording, "The unit tests fail.". **LF.303** also counts a defect that carries the failing unit-test command and names no criterion. The escalation accepted them as known issues.

**The release check was also wrong twice.** The interface contract gave false gaps on both of the last two runs. **LF.304** reads a contract line quoted whole and no longer fails `POST /notes -> 201` for the 422 a bare request rightly gets.

### What to improve next

1. **The suite is weak.** The mutation score was 0.33: 2 of 3 deliberate changes went unnoticed (`===` made `!==` in the error handler, `||` made `&&` in the service). The earlier recommendation applies with more weight: run the mutation pass at lock time, and send each surviving mutant back to QA as "no test holds the product to this line".
2. **Stop fixing unit tests the model wrote when they contradict a green suite.** Two runs in a row spent half their time here. Settle-when-green now ends it at the sprint's re-plan. Doing it at the round instead, and routing the disagreeing unit test to its author rather than to a product fixer, would save most of that half.
3. **Repairs that are spent leave a known-bad test locked.** The release listed `ac18.spec.js` line 17 (a fetch-style `body:`) as locked while still open, because the repairs were used up. A mechanical repair, `body: JSON.stringify(x)` becoming `data: x`, needs no model and could be applied whenever the review names it.

### How other harnesses handle it

Mutation-gated test generation is the field's current answer to weak generated tests. The oracle is checked against mutants, and a test is kept only if it fails on a mutant and passes on the original (AugmenTest, YATE; see the sources above). The harness already computes the mutants at release, so moving that step to the lock is a change of timing, not new machinery.

## run-5422d5df (2026-10-27 06:02-07:50 JST): FAILED, hidden 0/9, 100 min

The first failure after six 9/9 runs, with one cause from start to end. The first draft wrote `export async function createApp()`. The harness's kept `src/main.ts` serves `createApp().fetch`, which is undefined on a Promise, so the service listened and answered 500 to every request, `/health` included.

Four sprint attempts, three redrafts and 10 reverted fixes followed. Each step below was deployed into the run and none brought the model to drop the `async`:

- **LF.305:** the compiler error sits in a kept file, so the defect now says that file stays and what it uses must change.
- **LF.306:** the pack guide says the factory is never a Promise.
- **LF.307:** the note names `createApp` in `src/app.ts`, so the fixer rewrote the right file.
- **LF.308:** one fix did bring the product up (+15 tests, -8 unit tests) and was reverted by the 3× net-gain ratio. A fix that gains locked acceptance tests and loses only unit tests now stays.

**What closed it: LF.309.** The pack's own start file now awaits the factory (`const app = await createApp();`, valid top-level await in an ES module), so either form is served. Started that way, this run's own product answered `/health` with 200 and `POST /notes` with 201.

### The lesson for the harness

When a small model keeps producing the same shape, the harness should accept the shape if it is harmless, rather than argue with the model. Guidance, defect text and file pointers each cost a round and did not change the output. Making the harness's own code tolerant took one line. The same applies elsewhere: anything a kept file calls should be called in a way that tolerates both the sync and async form, and both default and named exports where the language allows it.

### How other harnesses handle it

Harnesses that scaffold a project, such as framework CLIs and app generators, keep their entry point generic (an `await` on the factory, or a framework adapter that accepts either form) so generated code cannot break the bootstrap. Agent harnesses that rely only on prompts to keep a contract report the same "guidance ignored" failures. The common answer is mechanical guardrails over prompts, as in the Sentry talk cited above.

### Value

A product that never starts is worth nothing, and this run spent 100 minutes proving it. A **start-path tolerance audit** of every pack's kept files, asking which reasonable shapes of the product's code would break the kept bootstrap and making the bootstrap accept them, would remove a whole class of total failures for every stack.

## run-bc9ee5f4 (2026-10-27 07:53-08:16 JST): hidden 9/9, locked 14/0, 23 min

The fastest run of the series, and the first with the tolerant start file (LF.309) in from the start.

- **The product started first time.** It went from 0 to 7 to 17 of 18 criteria in three test rounds, within 12 minutes.
- **Mutation score 1.0:** all 3 deliberate changes were caught, against 0.33 two runs earlier.
- **No KPI past 1.5× its five-run mean.**

The one problem was a loop, which ended on its own before the fix landed. AC-15 ("start.sh starts the service...") had no test in the locked suite; QA had judged it untestable through the request fixture but did not defer it. Each round raised it as a product defect, the dispatch closed it at once because none of its tests failed, and the sprint was planned again. That made four rounds and a re-plan in two minutes before the escalation accepted the sprint with AC-15 deferred.

**LF.310** sends a due criterion with no locked test back to QA from the round, so QA writes the test or defers it. It no longer goes round as a product defect.

### What to improve next

- **The start-script criterion is the harness's to prove, not QA's.** The kept `start.sh` and the start probe (LF.297) already start the service the suite's way, with `PORT` and a fresh `DATA_DIR`, and check `/health`. A criterion about how the product starts could be marked "proven by the harness's start check" from the probe's result, instead of asking a small model to write a process-spawning test.
- **An untested criterion should not lock.** The review locked the suite with AC-15 open. A gap with no test, like a suite that proves nothing, should hold the lock until QA writes the test or defers it with a reason.

### Trend

Since LF.298 the start-path fixes have removed the cause of the one 0/9 run, and the clean runs are getting shorter: 61, 72 and 100 min (failed), then 23 min.

## run-3e25eca8 (2026-10-27 08:17-08:50 JST): FAILED, hidden 5/9, 33 min

Two harness gaps, each now closed:

1. **A missing export was hidden.** The draft wrote `export default function createApp(storageService)`, so the service could not load. The pack-contract check said exactly that ("`src/app.ts` no longer exports `createApp`"), but the defect merge put it under the vaguer "The unit tests fail". **LF.311** makes the pack-contract finding lead a merged defect. A fix restored the named export, and the product reached 6 of 18 criteria.
2. **Re-plans wrecked a weak best twice.** At 4 of 11 tests, two re-plans in a row redrafted every file and each fell to 0. Keep-the-best (LF.295) applies only above half the suite. The undo put the 4-test product back each time, which is why the hidden score is 5/9 rather than 0, and the escalation stopped the run. **LF.312**: from the second re-plan on, a best product above zero keeps its files.

### What to improve next

- **Escalation should release the best product, not stop.** It stopped a run whose best attempt passed 5 of 9 hidden tests. Releasing it with the failing criteria recorded as gaps would have shipped a partial product honestly, and it is what the owner can use. This is the "release with a disputed suite" item from the deep review in a simpler form: release-the-best when the stall rule fires and the best is above zero.
- **A tolerant start file for exports.** LF.309 made the start file accept an `async` factory. Accepting a default export too (`import * as entry` and taking `createApp ?? default`) would have avoided round one. A factory that takes arguments cannot be bridged, so it stays a defect.

### Scoreboard since 2026-10-27 00:50 JST

8 runs: six scored 9/9, one 5/9 (this run) and one 0/9. Most runs now lose their time on the start path and to re-plans; the fixes from this session (LF.298-312) target exactly those.

## run-d6946351-508d-43f0-9f24-375c2bf6a112 (notes-api-hono, gpt-oss-20b, 2026-10-27)

**Result:** hidden 9/9, locked suite 10/1, mutation 0.917 (11 of 12 caught). It took 124 min wall, of which 92 were active and 32 were lost to the Docker Desktop outage. Mixed versions: `d4b8b8df` → `23de6286` → `d11c7c98`. It was the first run with LF.313: the start file accepts the named or the default `createApp`, and the product started.

**What went wrong:**

- Sprint 1 was re-planned three times, and attempts 3 and 4 changed nothing.
- The model's own unit tests spawned child processes with a relative `cwd` (`'notes-api'`, `'..'`) that did not exist from where the tests ran. Node reports that as `spawn /bin/sh ENOENT`.
- Two fixers read this as "no shell in this environment" and stopped.
- The harness already adds a "this path exists here; check the working directory" note to a stage's own commands. It did not add it to the harness's own unit-test run, which is what the defect was made from. **Fixed in LF.316.**
- AC-15 (start.sh honours PORT and DATA\_DIR) shipped deferred. Its locked test ran `main.ts` directly, so a broken start.sh would pass.
- Four lines of the interface contract were left unchecked because they read "200 or 404". The contract checker accepts only its three fixed forms, not alternatives.
- The acceptance authors spent 48 of 132 calls on failed edits: a find text that did not match exactly (×12), writes outside the acceptance suite, and JS syntax errors in the spec.

**Improvements, in order of value:**

1. *Unit tests that cannot run where the harness runs them.* Beyond LF.316, check a test that spawns a child for its `cwd` at write time, as the import-extension check already does, so the mistake never reaches a test round.
2. *Contract alternatives.* Parse `A or B` status lines as a set, so the release check covers them instead of listing them as gaps.
3. *Start-script criterion.* Let the harness prove "start.sh honours PORT/DATA\_DIR" itself, by starting the product the way START\_PROBE already does. A criterion the harness can measure should not depend on a model-written test.
4. *Edit misses.* After an exact-match miss, return the nearest matching lines with their exact whitespace. Most of the ×12 misses were whitespace and comment drift.

**How other harnesses handle it:**

- SWE-agent's and OpenHands' editors show the file region around a failed `str_replace`, so the model sees the exact text.
- Aider re-tries a failed SEARCH block with fuzzy matching and shows the closest lines.
- OpenHands and Codex run tests inside the same container image the agent works in. Their "missing binary" errors are therefore real, while ours here was a false alarm that needed the note.

**Added value:** the admin page (LF.315) now lets the owner turn any of the 54 switches on or off, each with its explanation, without a redeploy. That makes switch ablations a settings change instead of a compose edit.

**Scoreboard:** 9 runs on notes-api-hono: seven scored 9/9, one 5/9 and one 0/9.

## run-baa1e7ac-0c05-4802-961d-e654ea9c1a45 (notes-api-hono, gpt-oss-20b, 2026-10-27)

**Result:** hidden 9/9, locked suite 14/0, mutation 0.75. 112 active minutes, 460 model calls. Mixed versions: `6fd0a863` and then six deploys (LF.317–LF.322), with two rewinds. KPI flag: 15 fixes reverted, against a 5-run mean of 2.8.

**What went wrong, in order:**

1. *Gutted suite (LF.317/318/319).* The product was not built yet, so QA wrote nine tests as empty `test.skip` stubs ("skipped due to incomplete implementation") and the review locked them.
   - The repair guard, which refuses a repair that deletes tests it was not sent for, protected the stubs' names.
   - The dispatch re-measure counted "skipped" as "passed", so every one of those defects closed without a fixer, and sprint 1 was re-planned twice with nothing fixed.
   - Three fixes, each shown failing on the old code first: skipped tests prove nothing; a stub may be removed but a kept test may not be turned into one; a stub counts only for a criterion with no other test that runs.
   - Deploying LF.317 without LF.318 failed the run at 13:14, and a rewind recovered it. Lesson: deploy coupled fixes together.
2. *Five minutes lost per fixer write (LF.320/321).* With the product not starting, each write's check ran every acceptance file and waited out a 60 s server timeout per file.
   - LF.320 stops after the first file that shows the product never started.
   - LF.320 never fired live, because the probe limit (60 s) equalled the suite's server wait, so the sandbox killed each run before the runner could say why.
   - LF.321 gives a probe the pack's server wait plus 15 s. Probes now take seconds.
3. *Four reverted fixes from one mistake (LF.322).* `import type { NoteStore }` followed by `new NoteStore(...)`: Node strips the import, so start-up throws a ReferenceError. TS1361/1362 were not on the language service's "certain" list, so the write was not refused.
4. *The escalation released with 8 failing unit tests.* Every acceptance test passed and only the model's own unit tests failed, and the last fix broke 22 tests and was reverted.

**Improvements, in order of value:**

1. *Catch broken writes before a test round.* Every one of the 15 reverts was a product that no longer started. A start probe after each product write in a fix stage would catch the crash at the write, the way SWE-agent's lint-on-edit does. START\_PROBE already exists; run it per write when the change touches the start path.
2. *Contract alternatives (second run in a row).* "200 or 404" lines are still left unchecked at release. Parse `A or B` as a set of allowed statuses.
3. *Suite authoring before the product exists.* Tell QA explicitly that a test is meant to fail until the product exists, and refuse `test.skip` at write time, not at the review.
4. *Redundant reads at 68%.* The highest seen. The memory digest is not reaching the acceptance stages after a rewind; worth measuring per stage.

**How other harnesses handle it:**

- SWE-agent and OpenHands run a linter on every edit and reject an edit that introduces errors, which is the class LF.322 closes.
- Aider runs the test command after each change and feeds back the first failure.
- None of them hold a separately authored acceptance suite, so the gutted-suite failure is ours alone. The closest analogue is SWE-bench's FAIL\_TO\_PASS / PASS\_TO\_PASS split: tests must be seen failing first, and a skipped test is not counted.

**Added value:** the admin page lets the owner switch individual guards off for an ablation. A natural next step is a per-run "what fired" panel beside each switch, built from `loop.sh effects`.

**Scoreboard:** 10 runs on notes-api-hono: eight scored 9/9, one 5/9 and one 0/9.

## run-3143cf16-3425-41c1-bb0b-f7ee42436683 (notes-api-hono, gpt-oss-20b, 2026-10-27)

**Result:** hidden 9/9, locked suite 14/2, mutation 0.75. 120 minutes, 756 model calls (the most yet). Mixed versions: `df415f6a` → `6af8f2de` (LF.323/324, rewound to its test round) → `9fcad759` (LF.325). KPI flags: 13 fixes reverted (mean 5.4) and 40 defects left open (mean 13.2). AC-6 and AC-17 (persistence) shipped deferred; the hidden tests passed them anyway.

**What went wrong:**

1. *Correct tests charged as broken (LF.323).* The product served no routes, so `res.json()` on its text `404 Not Found` threw a JSON `SyntaxError`. The JavaScript pack read every `SyntaxError` as the test's own bug and reopened the suite for 14 correct tests. Fixed and rewound within the first 40 minutes.
2. *QA asked to fix a product file (LF.324).* A refused write still counted as "touched", so QA was asked to fix the product's missing import and spent 16 refused writes on it.
3. *A real test bug outlived the suite's repair budget.* The persistence test called `.status()` on a native `fetch` response, and QA's two repairs did not fix it. The harness correctly stopped charging that test to the product, but:
   - the testing role's own finding about the spec file still reached fixers (fixed in LF.325);
   - AC-6 and AC-17 kept being raised as "the suite says this does not work yet" and drove three more re-plans (attempts 2–4), for criteria no fix could prove.
4. *A fixer bent the product to suit the model's unit tests.* It wrapped `createApp().request` so the unit tests could call `.status()`. From then on the unit and acceptance tests disagreed about the response shape, and most of the 13 reverts were fixes caught between them.

**Improvements, in order of value:**

1. *Defer a criterion whose only test is beyond repair, at once.* Raising it every round cost three re-plans and about an hour. This is the next fix to build.
2. *A product change made to satisfy a unit test should not alter the shape of the product's interface.* The interface contract could be checked after each fix, not only at release.
3. *Give a test repair more time when it is a known pattern.* The fetch `.status()` bug is mechanical: the harness could rewrite `fetch(...)` to the `request` fixture, or hand QA the exact line and form, instead of spending its budget.
4. *Redundant reads stayed at 63% all run.* The worst in this series. It needs a per-stage breakdown.

**How other harnesses handle it:**

- SWE-bench-style evaluation separates FAIL\_TO\_PASS tests from PASS\_TO\_PASS tests. A test that is wrong is fixed or removed before a product is measured, never chased by product fixes.
- OpenHands and Aider have no locked suite, so their agents rewrite tests freely. That trades our integrity for speed; our deferral path is the middle ground and needs to engage sooner.

**Added value:** today's fixes (LF.316–325) each come with a test proven failing first. A weekly "fixes and their effect" view built from `loop.sh effects` on the admin page would show the owner which guards earn their keep.

**Scoreboard:** 11 runs on notes-api-hono: nine scored 9/9, one 5/9 and one 0/9.

## run-d147c547-c89b-4988-b9eb-bcc12df598ad (notes-api-hono, gpt-oss-20b, 2026-10-27)

**Result:** hidden 9/9, locked suite 12/0, mutation 0.833. 44 minutes and 273 model calls, against 112–120 minutes and 460–756 calls for the two runs before it. No KPI past 1.5× its 5-run mean. Versions: `9fcad759` → `f5956e68` (LF.326, deployed during its first acceptance stage).

**What worked:**

- The suite was written as 11 spec files with no skipped stubs, and locked on its first review.
- The first test round closed 14 criteria by measurement, and AC-6/AC-17 (persistence) passed this time.
- None of today's guards had to step in on a crash-at-start, a gutted suite or a false reopen.

**What cost time:**

1. *One re-plan of a fully green product.* After attempt 1 every acceptance test passed and the only open defect was the model's own unit tests ("Note 1 not found"). Settle-when-green applies only from the second exhaustion on, so the sprint was drafted again (about 7 minutes) before the escalation accepted it with the unit tests recorded. Proposed to the owner: apply it on the first exhaustion when the suite is fully green.
2. *Redundant reads at 73%.* Still the largest steady waste.
3. *Release gaps:*
   - Four contract lines with a path parameter (`/notes/:id`) were not checked at release.
   - The suite missed `>` → `<=` in the error handler.
   - A CommonJS `test-setup.js` sat in an ES-module package.

**Improvements, in order of value:**

1. Settle a fully green sprint on the first exhaustion. That would have made this a \~37-minute run.
2. Let the release's contract check probe routes with a parameter by creating the resource first, so the contract check covers the main CRUD routes.
3. Redundant reads: break them down per stage, then find where the memory digest is not reaching.

**How other harnesses handle it:**

- Aider and Claude Code stop when the user's tests pass. They do not redraft working code for an unrelated failing test, which is the behaviour settle-when-green moves toward.
- SWE-bench grades only FAIL\_TO\_PASS and PASS\_TO\_PASS, so a candidate's own extra tests are never a reason to reject it.

**Added value:** today shows the loop working. Each guard added this morning (LF.316–326) was measured against a live failure, and the first run with all of them from the start was the fastest clean run of the day.

**Scoreboard:** 12 runs on notes-api-hono: ten scored 9/9, one 5/9 and one 0/9.

## run-512dcf5c-fd3d-4ccf-bba0-a43318194742 (notes-api-hono, gpt-oss-20b, 2026-10-27)

**Result:** hidden 9/9, locked suite 16/0, mutation 0.917. 42 minutes and 197 model calls: the best run of the day on every measure. Versions: `f5956e68` → `ab63a233` (LF.327) → `bdcfe346` (LF.328). One KPI flag: one model error (mean 0).

**What happened:**

- The suite locked on its first review, and the first two rounds closed 13 criteria.
- The persistence test (AC-6/AC-17) called `fetch` with a `data:` body, which `fetch` does not send, so the product answered 400. The dispute caught it, QA repaired it, and the suite relocked.
  - That was the second run in a row with a `fetch` test written in the request fixture's style. LF.328 now catches both forms before the suite locks.
- Attempt 2 ended with the suite fully green and only the model's own unit tests failing (a `FileStore` test passing a non-string path). LF.327, approved by the owner today, sent it straight to the escalation, which accepted it with the unit tests recorded. Without LF.327 the sprint would have been planned again.

**Improvements, in order of value:**

1. *Redundant reads at 81%.* The highest of the day, and now the largest steady waste on every run. Next step: a per-stage breakdown (`loop.sh reads`) to find which stages re-read files the memory already holds, then enforce it.
2. *The model's own unit tests fail at release on most runs.* Either let the testing role delete a unit test that contradicts a green acceptance criterion, or drop failing model-written unit tests from the release with a note.
3. *Contract lines with path parameters are still unchecked at release.*

**How other harnesses handle it:**

- Context-efficient agents such as SWE-agent's ACI and Claude Code show file windows and keep a file-state cache, so a re-read of an unchanged file is answered from memory.
- Our memory digest exists, but the 81% rate says stages still ask for files the digest already holds. Refusing such reads outright, as the read guard does after N attempts, could start at the first repeat.

**Added value:** the day's arc on one model and one brief:

| Run | Minutes | Model calls |
| --- | --- | --- |
| run-baa1e7ac | 112 | 460 |
| run-3143cf16 | 120 | 756 |
| run-d147c547 | 44 | 273 |
| run-512dcf5c | 42 | 197 |

All four scored 9/9, so twelve fixes, each proven by a failing test first, cut the cost of the same result by about two-thirds.

**Scoreboard:** 13 runs on notes-api-hono: eleven scored 9/9, one 5/9 and one 0/9.

## run-33773efc-0824-4025-b2ff-776c56c2b80b (notes-api-hono, gpt-oss-20b, 2026-10-27)

**Result:** hidden 9/9, locked suite 15/0, mutation 0.833. 68 minutes and 299 model calls. Versions: `bdcfe346` → `e056c719` (LF.329, rewound to its test round) → `364fd2d9` (LF.330) → `3cdc1e75` (LF.331). KPI flag: identical calls 6.3% (mean 2.4%).

**What went wrong:**

1. *My own check sent QA to break correct lines (LF.329).* The spec named a fixture response `getResp` in one test and a `fetch` response `getResp` in another. LF.300 and LF.328 judged the name file-wide, so the correct `fetch` code was flagged, QA changed a correct `createResp.status` to `createResp.status()`, and the suite never locked.
   - Fixed by judging each read by the assignment before it, then rewound.
   - Lesson: a pattern check on names must be scoped to the assignment it reads.
2. *The product never started for three attempts (LF.330/331).* Two health handlers built their answer and returned nothing (`c.body(...)` / `c.text(...)` with no `return`). `@hono/node-server` then failed every request with `res.body.getReader is not a function`, which names neither.
   - The fixers fixed one handler and missed the other.
   - The compiler had the real reason all along ("Type 'void' is not assignable to type 'HandlerResponse'"), but the harness passed on only its first line, "No overload matches this call".
   - LF.330 puts the rule in the Hono guides. LF.331 passes each compiler error's innermost line to fixers.
   - The product started and went 15/0 within minutes of LF.331.

**Improvements, in order of value:**

1. *Run `tsc` on every fix's files and refuse a write that adds a TS2769/TS2345 on a route registration.* Today's three start failures were all visible to the compiler before anything ran.
2. *Identical calls doubled (6.3%).* Mostly fixers re-running the same edit. The existing repeat guard could cut in one call earlier for edits refused for the same reason.
3. *A start failure that repeats across attempts should be named as such in the re-plan's brief:* "the product has not started in any attempt; the start error is X".

**How other harnesses handle it:**

- SWE-agent's linter gate and Aider's lint-then-test loop show the full compiler diagnostic, with its elaboration, on every edit. Our first-line truncation was the gap.
- OpenHands keeps the last error in view across turns, which is closer to improvement 3.

**Added value:** today's 16 fixes (LF.316–331) all came from live failures, each with a test proven failing first. Five runs in a row scored 9/9 on this brief.

**Scoreboard:** 14 runs on notes-api-hono: twelve scored 9/9, one 5/9 and one 0/9.

## run-59aa4eb9-1341-4a76-9777-bcd5f1f6e2d3 (notes-api-hono, gpt-oss-20b, 2026-10-27)

**Result:** hidden 9/9, locked suite 24/0. **37 minutes**, 219 model calls: the fastest run of the day. Versions: `3cdc1e75` → `47db1283` (LF.332). KPI flags: mutation 0.583 (mean 0.817) and 2 model errors (mean 0.2).

**What happened:**

- Attempt 1's draft wrote Express-style `import { Router } from 'hono/router'` and never started. Two fixes were refused or reverted for importing a `Router` from `hono`.
- The re-plan's draft started (19 of 24), and the suite went 24/0 within 12 minutes. LF.327 then settled it on the first exhaustion, with only the unit tests open.
- LF.332 ("Hono has no `Router`") went in mid-run, too late for that draft, so whether it helps will show on the next run.

**The mutation drop:** 5 of 12 changes survived, against a mean of 2–3.

- The suite missed:
  - `true` → `false` in `app.ts` line 26;
  - `||` → `&&` in a title check (`notes.ts` line 40);
  - `===` → `!==` at `notes.ts` line 88;
  - `||` → `&&` in the store (`noteStore.ts` line 47).
- QA wrote 24 tests, the most so far, yet several only confirm the happy path. More tests did not mean stronger tests.

**Improvements, in order of value:**

1. *Mutation-guided tests (QM.2, built and still off).* This run is the case for turning it on: each survivor named above is a test QA could add, phrased as a criterion's edge case ("a title of only spaces is refused").
2. *Measure LF.332 on the next run:* did the first draft use `new Hono()` per area?
3. *Model errors (2).* Check whether they were server errors from LM Studio or malformed replies. They cost no visible time, but the trend is worth watching.

**How other harnesses handle it:**

- Mutation testing as a test-quality gate is rare in agent harnesses. Meta's ACH (mutation-guided test generation) is the closest published practice.
- Our QM.2 follows that idea, which is a differentiator.

**Added value:** six runs in a row at 9/9 on this brief, the last three at 42, 68 and 37 minutes. Test quality (mutation) is now the axis to improve, not reliability.

**Scoreboard:** 15 runs on notes-api-hono: thirteen scored 9/9, one 5/9 and one 0/9.

## run-d1884e46-be04-434a-8b8b-ac9ac711bfd1 (notes-api-hono, gpt-oss-20b, 2026-10-27)

**Result:** hidden 9/9, locked suite 17/0, mutation 0.917. 53 minutes and 298 model calls. No KPI past 1.5× its mean. Versions: `47db1283` → `dd4d35d7` (LF.333).

**What happened:**

- *LF.332 measured:* the first draft used `new Hono()` and no `Router`. The product started on its first draft, unlike the run before.
- *LF.333 caught on its first round:* both AC-15 tests read `request.baseURL`, which the fixture does not have, and `process.env.PORT`, which only the server has. The new check reopened the suite at once.
  - QA's repair fixed the `baseURL` read but kept a `process.env.PORT` fallback.
  - With the repair budget spent, LF.326 deferred AC-15 instead of re-planning for it. The hidden tests passed it anyway.
- *The DELETE bug* (204 answered 404, then 500): the fixers struggled until the re-plan, and the last attempt's fix put it right. LF.327 then settled the green sprint on its first exhaustion.

**Improvements, in order of value:**

1. *Give a repair the exact replacement.* A check that knows the fix could hand QA the replacement line itself (`async ({ request, baseURL }) =>`), so one repair round suffices. Today a repair round fixed half of the problem.
2. *A DELETE answering 204 needs `c.body(null, 204)` in Hono.* `c.body('', 204)` throws. That is stack knowledge for the Hono guide, though the guide is at 2,980 of 3,000 characters, so it needs trimming first.
3. *Redundant reads at 56%.* The re-read proposal is still waiting for the owner.

**How other harnesses handle it:**

- Linters with autofix (ESLint `--fix`, ruff) apply the known fix instead of describing it. A check that knows the exact replacement could do the same for the suite, inside QA's repair, as a suggested edit.

**Added value:** seven runs in a row at 9/9, and mutation is back up to 0.917. Each of today's new checks fired on a real case within a run or two of being written.

**Scoreboard:** 16 runs on notes-api-hono: fourteen scored 9/9, one 5/9 and one 0/9.

## run-befbd51e-c9ef-435d-8499-8011fc6aee31 (notes-api-hono, gpt-oss-20b, 2026-10-27)

**Result:** hidden 9/9, locked suite 10/0, mutation 0.75. 48 minutes, 280 model calls. Versions: `dd4d35d7` → `8451870c` (LF.334/335, the owner's two approved proposals). KPI flags: 3 fixes reverted (mean 1) and 24 defects left open (mean 9.4). For the first time today, no failing unit tests shipped.

**What happened:**

- Sprint 1 took four attempts.
  - The first product served no `/health` (404: the route was not registered on the served app).
  - Then fixers spent two stages, one stopped at the 60-call cap, on a false belief that `sqlite3` cannot be imported as an ES module. It loads fine.
  - The suite was repaired twice: once for real test bugs, and once on a likely false "the runner never ran it" read from a partial report right after a reverted fix. That one cost about 2 minutes and is open for investigation.
- *LF.334 and LF.335 are live,* but this run cannot judge them.
  - The mutation probe needs a green suite with only unit tests open, and the suite went green only in the last round.
  - The first-re-read answer cannot be told apart in the audit's re-read count, which no longer counts it. Model calls (280) are within today's range.

**Improvements, in order of value:**

1. *A fixer's false environment claim* ("cannot import X") should be checked by the harness at once: run `node -e "import('X')"` and hand back the result. The harness already corrects "no shell here" (LF.316); the same pattern fits module claims.
2. *"Never ran it" read from a partial report:* measure it from the suite's own full run only, never from a run cut short by a reverted fix. To investigate on the next occurrence.
3. *Measure LF.334/LF.335 over the next three runs:* mutation score, model calls, and whether the probe fired.

**How other harnesses handle it:**

- OpenHands and SWE-agent let the agent run a quick check itself, which our sandbox also allows. The gap is that a small model asserts the environment is broken instead of checking. Self-verification prompts ("check before concluding"), as in Reflexion-style agents, are the usual answer, and the harness can do it for the model.

**Scoreboard:** 17 runs on notes-api-hono: fifteen scored 9/9, one 5/9 and one 0/9. Eight in a row today.

## run-6929d37b-62ef-4905-a388-fb24dce491bc (notes-api-hono, gpt-oss-20b, 2026-10-27/28)

**Result:** hidden 9/9, locked suite 11/2, with AC-15 and AC-16 deferred (both passed the hidden tests). 110 minutes and 514 model calls. Versions: `8451870c` → LF.336 → LF.337–343 → LF.344. KPI flags: mutation 0.583, fixes reverted 6 (mean 1.6), defects left open 29 (mean 12).

**First measurements of tonight's batch:**

- *LF.334 mutation-guided tests fired for the first time today.* 3 of 4 deliberate changes went unnoticed. The testing role wrote unit tests for all three, and the harness proved each one fails with the change and passes without it.
  - The release mutation score (0.583) counts only the locked acceptance suite, so those unit tests do not show in it. That is a measuring gap, added to the backlog as B11.
- *LF.337 last try at deferred criteria fired at release on AC-15.* The rewrite did not pass it without breaking another test, so it was put back as designed.
- *LF.339/342 fixer fingerprints* are in the ledger, once per fixer.
- *LF.344 found live:* a fixer's camelCase probe file (`tmpCheckMultiple.js`) had a whole fix reverted.
- Not yet exercised: LF.338 (edit anchors), LF.340 (release contract alternatives), LF.341 (import claim), LF.343 (corrected lines).

**What cost time:** the product did not start through attempt 1. A handler returned a plain object, which LF.336 now covers in the guide. Then update and delete stayed red through three re-plans, with one defect left open after 119 model calls under the per-defect call cap.

**Improvements, in order of value:**

1. *B11:* the release mutation score should count the unit tests too, or report suite and unit separately, so QM.2's work is visible.
2. *A defect that survives three re-plans should be deferred earlier, at the second.* The hidden tests passed both of these anyway, so the extra re-plans bought nothing.
3. *Reverts (6):* mostly fixes that stopped the product starting. B6, the compiler gate on route handlers, is the candidate if LF.336 does not cut them on the next runs.

**How other harnesses handle it:**

- Meta's ACH counts the generated tests in its mutation score, which is the B11 shape.
- SWE-bench-style harnesses grade on the target tests only, so extra re-plans spent on criteria the target already accepts are wasted, as here.

**Scoreboard:** 18 runs on notes-api-hono: sixteen scored 9/9, one 5/9 and one 0/9. Nine in a row.

## run-b75438d4-eea6-4078-931f-09ca07ebeb43 (notes-api-hono, gpt-oss-20b, 2026-10-28)

**Result:** hidden 9/9, locked suite 25/0, nothing deferred, no failing unit tests shipped. 71 minutes and 226 model calls. Mutation: 0.75 by the suite alone, 0.833 with the unit tests (B11, new). Versions: `04d03951` (LF.316–344 from the start) → `b3368037` (LF.345, measuring only) → `7330fa89` (LF.346). KPI flag: identical calls 6.6% (mean 3.4%).

**What happened:**

- Attempt 1 never started. `healthRouter.get('/health')` was mounted with `app.route('/health', ...)`, so it served `/health/health`, and two rounds of fixes missed it because they were told only that the route was not served.
- *LF.346* (the start check now lists the routes the app serves) went in at the re-plan. Attempt 2's first fix corrected both routers: 22/23, then 25/25 after QA repaired AC-15.
- *LF.334 mutation probe:* 1 of 6 deliberate changes went unnoticed. The testing role wrote a unit test that the harness proved catches it, and the release-time score with unit tests rose to 0.833 (B11 made that visible).
- *LF.327* was not needed: the suite went fully green, with nothing open.

**Improvements, in order of value:**

1. *Identical calls (6.6%), the second run with it flagged.* Mostly QA repeating an edit refused as ambiguous (`const created = await createRes.json();` appears in every test). Answer that refusal with the line numbers of each match *and* a ready `replace_lines` call for the first one, so the next call can only be different.
2. *Name a route the start check lists that doubles its own mount* (`/health/health`) as the likely cause, not only as a list item.
3. *B12 stays held:* this run deferred nothing, and LF.337's last try has not yet saved a criterion. More runs needed.

**How other harnesses handle it:**

- Framework-aware agents (Rails/Django dev tools, `next build` route reports) print the route table at start. That is what LF.346 adds, and it closed this run's start failure in one fix.

**Scoreboard:** 19 runs on notes-api-hono: seventeen scored 9/9, one 5/9 and one 0/9. Ten in a row.

## run-8d3b5844-4e07-46d8-a387-68dc0b1da58a (notes-api-hono, gpt-oss-20b, 2026-10-28)

**Result:** hidden 9/9, locked suite 11/0. **31 minutes**, 211 model calls, no KPI past 1.5× its mean. Mutation 0.667, both suite-only and with the unit tests. Versions: `7330fa89` → `2570c1a0` (LF.347, during architecture).

**What happened:**

- The product started on its first draft, the first time in three runs.
- Two rounds closed the suite to 11/0, with two defects closed by measurement and no fixer.
- LF.327 then escalated with only a unit test open, and the escalation released it.
- *LF.334's probe ran at the last round:* its finding (`createNote.ts`: `===` made `!==` goes unnoticed) became a completion gap, because the sprint had no fix round to spare.

**Improvements:**

1. *Run the mutation probe earlier:* at the first round where the due criteria pass, not when the rounds are nearly spent. That way its findings get a round. Today it ran in the round that settled the sprint.
2. *The one shipped failing unit test was `test/app.test.ts` as a whole file* (a load error). A file that fails to load could be named as such in the release note, not as a test.

**Scoreboard:** 20 runs on notes-api-hono: eighteen scored 9/9, one 5/9 and one 0/9. Eleven in a row.

## run-3f097c14-bdb5-4194-a48b-ccd1aebcab52 (notes-api-hono, gpt-oss-20b, 2026-10-28)

**Result:** hidden 9/9, locked suite 17/0, mutation 0.917. About 50 minutes from the first start; the KPI shows 25 because it counts from the rewind. Versions: `2570c1a0` → `d551b22c` (LF.348/349, paused, deployed and rewound to its test round) → `7db2c343` (LF.350).

**What happened:**

- The suite reached 17/0 within 20 minutes.
- Then a model-written unit test that never settles (the promise-based `sqlite` wrapped in callbacks) held each `npm test` for the sandbox's full 5 minutes. The harness ran it four times in one round with no fix between: 20 minutes on an unchanged product. Three fixes followed:
  - *LF.348:* every Node test-runner script gets `--test-timeout=20000`, from the next scaffold on.
  - *LF.349:* the harness's unit run of an unchanged product stands, as the suite's already did (MEASURE\_ONCE).
  - *LF.350:* the product fingerprint is of its files, not the commit id. The harness's own record commits had made an unchanged product look new, so LF.349 alone still re-ran.
- After the rewind, the round finished in minutes, and LF.327 settled the sprint with only the unit tests open (5 failing tests in that one file shipped as known).

**Improvements:**

1. *The live run could not get LF.348:* the native Hono pack does not keep its `test` script, so the harness never puts the timeout back. Keeping it, as the CLI and library packs do, would also stop a model from changing how its unit tests are run.
2. *The mutation probe changed `sqlite3/index.js`,* a folder the product itself vendored. A package directory beside the product should be left out of the probe's sources.

**Scoreboard:** 21 runs on notes-api-hono: nineteen scored 9/9, one 5/9 and one 0/9. Twelve in a row.

*Correction:* improvement 1 above is wrong. The native Hono pack does keep its `test` script (`kept_scripts`), so the harness put LF.348's timeout back into the live project before each of its own runs from the 03:29 deploy on. Nothing to build there.

## run-799b0a77-213e-4604-9e6d-5df35b20a90c (notes-api-hono, gpt-oss-20b, 2026-10-28)

**Result:** hidden 9/9, locked suite 15/0, mutation 0.917. 53 minutes and 308 model calls. KPI flag: 36 defects left open (mean 12.6). Shipped with 19 of the model's own unit tests failing. Versions: `7db2c343` → `5e1fef8b` (LF.351) → `e212af75` (LF.352).

**What happened:**

- `POST /notes` answered 500 through attempt 1, and nine fixers changed nothing or chased the tests. The server had logged the error, but no fixer saw it.
  - *LF.351:* each failing criterion's defect now carries the server's logged errors.
  - *LF.352:* a logged frame that throws its own error in place of the one it caught is named. Here `catch (_) { throw new Error('Internal server error') }` hid that the constructor made the data folder's parent, not the folder.
- Attempt 2's fixers fixed the persistence on their own before LF.352's note fired, so its effect is not measured yet.
- Attempt 3 closed the validation criterion (AC-13/AC-18), and LF.327 settled with only the unit tests open.

**Improvements:**

1. *19 failing unit tests shipped.* The model's unit tests and the product disagree after the fixers changed the product. The release already names them. A second-attempt redraft could leave out unit test files whose every test fails, so the escalation is not their story.
2. *Defects left open (36):* most were the pre-LF.351 rounds' blind fixers. Measure again on the next runs.

**Scoreboard:** 22 runs on notes-api-hono: twenty scored 9/9, one 5/9 and one 0/9. Thirteen in a row.

## run-f523de50-8e50-486a-beee-abffe56d13b5 (notes-api-hono, gpt-oss-20b, 2026-10-28) — FAILED

**Result:** hidden **5/9**, locked suite 13/26, mutation 0.25. 144 minutes, 555 model calls, 18 fixes reverted, 41 defects left open. The streak of thirteen 9/9 runs ends. Versions: `e212af75` → LF.353 (rewound) → LF.354–358 deployed into it.

**What happened:**

- The first try failed at the suite: five `<x>_spec.js` files the runner never collected. LF.353 now renames them, and the run was rewound.
- The second suite locked with 39 tests. One of them, AC-7's "every response is `application/json`", looped over the endpoints and expected JSON on `DELETE /notes/1`. The brief says DELETE answers 204, with no body.
- Every fix that made delete correct broke that one test and was reverted: eight times, over four attempts.
  - The dispute for a test two reverted fixes broke was never held: its gate asked about the failing tests, which were already repaired. *LF.356* fixed that gate.
  - Then the suite was past its overall repair limit, so no judgement could happen at all. *LF.357/358* now keep a fix whose only casualty is such a test.
  - These fixes went in during attempts 3 and 4, and the right shape of fix never came again.
- The stall rule escalated and the run stopped. Delete, persistence, and three more criteria are wrong in the shipped product.

**Improvements, in order of value:**

1. *B14: catch the contradiction before the suite locks.* A test that reads a body or a content type from a response the interface contract says is 204 contradicts the contract. A static check, among `tests_that_cannot_pass`, could send it back at the review, before any fixer runs.
2. *The suite's overall repair limit (4) ran out on early, mechanical repairs* (renames, fetch shapes). Mechanical corrections the harness makes itself (LF.353) should not count against it.
3. *Rewinds reset files but not lessons.* When the second suite was drafted, the AC-7 shape could have been flagged from the first.

**How other harnesses handle it:**

- SWE-bench-style setups never let the agent's own tests decide acceptance. Our locked suite is model-written, which is its strength (independent of the builder) and its risk, as here.
- Tying it to the brief's own contract (B14) is the middle ground.

**Scoreboard:** 23 runs on notes-api-hono: twenty scored 9/9, two 5/9 and one 0/9.

## Run run-27bce4ec — notes-api-hono, gpt-oss-20b (2026-10-28 07:39–08:17 JST)

**Result:** hidden 9/9 in 38 minutes, mutation 0.667 (0.75 with unit tests). The locked suite finished 13/14: AC-6 (persistence across a restart) shipped deferred. Eleven of the product's own unit tests shipped failing.

### What went wrong, and what was built

- **The harness's own guidance caused a broken test.** The restart guide showed only `const { startService } = require('./service.cjs')`. In a project Node loads as an ES module, QA wrote it inside a test, where `require` is not defined. Then the review's correction hint pointed QA at the wrong import, and QA kept the line through three rounds. **LF.360**: the check now names the exact correction: delete the line when its names are already imported, otherwise write the `import` at the top. **LF.361**: the guide loads the helper the way the file loads `@playwright/test`.
- **A restart test that can never pass.** AC-6 wrote its record through the suite's shared server, then restarted a service on a fresh, empty folder and read from it, so it got a 404 on every product. **LF.361**: `tests_that_restart_on_data_they_never_wrote` adds it to the tests that cannot pass, so the suite is repaired instead of the product being charged.
- **Stale unit tests pulled fixers the wrong way.** The unit tests called the factory as it was before a fix made it async. Two fixers changed the product to suit them, broke 3 and then 7 passing acceptance tests, and were reverted, which cost two sprint attempts. **LF.362**: a unit-test fix reverted for breaking the locked suite is told the unit tests are out of date. It should change them, keep their names, and leave the product alone.
- **Release notes repeated wrong reviewer guesses.** The completion gaps list eight "locked with this still open" notes claiming that main.ts never supplies a store. The product passed 13/14, so they were wrong. The next improvement is to drop review notes the final measurement contradicts.

### How other harnesses handle this

- Research in 2026 treats stale and breaking tests as a measured failure mode of coding agents ("Breaking, Stale, or Missing?", arXiv 2605.06125). It separates tests that fail after a change from tests that pass but no longer check the new behaviour. This harness's stance matches that research: the locked, spec-first acceptance suite is the oracle, and a team's own tests give way when the two disagree.
- Spec-first suites catch seeded bugs that code-first suites miss (ELEKS: 22 of 60 code-first suites passed on seeded bugs, against 0 of 60 spec-first). Some tools keep the acceptance criteria away from the coding agent entirely (qikly). The harness already separates the roles: QA writes from the brief, and the suite is locked.
- Agent-as-a-judge review of generated tests (Grindr) and oracle-signal taxonomies for agent-written assertions ("All Smoke, No Alarm", 2026) point to the next step: judge unit-test assertion strength, not only pass or fail.

### More value next

1. Drop locked-with-open review notes that the final measurement contradicts, so the release report stays trustworthy.
2. When the acceptance suite is green and only unit tests fail, schedule one unit-test-only fix with the out-of-date framing from the start, rather than waiting for a revert.
3. Feed assertion-strength signals (mutation results per test) back to QA, so weak tests are strengthened before the lock.

**Scoreboard:** 24 runs: 21 at 9/9, 2 at 5/9, 1 at 0/9. Next run: run-35ce828d, started 08:27 JST on 1dd60f91 (LF.316–362).

## Run run-35ce828d — notes-api-hono, gpt-oss-20b (2026-10-28 08:27–09:07 JST)

**Result:** hidden 9/9 in 40 minutes. The locked suite passed 23/23 with nothing deferred. Mutation score 0.917, the best so far. Four of the product's own unit tests shipped failing, and they were wrong tests.

### What went wrong, and what was built

- **A green suite was reopened twice for nothing (LF.363).** A defect's re-measure ran one suite file, and that file's report replaced the whole suite's. The round then reused the saved measurement (MEASURE\_ONCE) with that partial report: 10 tests where 13 had run. It read the other three as "never run" and sent the suite for repair. Each repair cost about 10 minutes and one of the four repairs allowed. Fix: a per-file run puts the suite's report back, and a reused measurement whose report counts differ from the saved run measures again.
- **A real unit-test failure was closed every round without a fixer (LF.364).** The unit tests were named "AC-1 CreateNoteTest", so the re-measure at dispatch ran the acceptance files of those criteria instead of the unit tests. The acceptance files passed, so the defect was closed. That also explains the previous run's 11 failing unit tests. Fix: a failing unit run is re-measured by the unit tests alone.
- **Wrong unit tests pulled fixers toward the product (LF.365).** The failing tests asserted a key order, a count that other tests' data changed, and an empty 404 body the interface does not give. When the locked suite is fully green, the unit-test defect now says from the start that the unit test may be what is wrong. The fixer should correct it to the specification, keep its name, and change the product only for a failure the specification backs.
- **The dispute reached the right outcome for the wrong reason.** The QA lead ruled the specification's 415 tests "cannot pass" because the implementation answered 200. The suite kept them, so there was no harm, but a dispute ruling should cite the specification, not the current implementation.

### How other harnesses handle this

- Cached test results are trusted only while their inputs hold. qa.tech's agent cache never stores failed runs and refetches when the page changes. Skyvern falls back to the agent and regenerates the cache when cached code breaks. The lesson for MEASURE\_ONCE is the one LF.363 applies: a reused result must also check that its own artefact is unchanged, not only the product.
- Saving each run's output to its own file, and keeping it, avoids both re-runs and clobbering (the clawdbytes "tee to disk" pattern). Some reporting skills mark results stale after a time limit. A next step here is to keep the suite's report under a per-run name, so no partial run can ever stand in for it.
- JetBrains' TeamCity setup for evaluating agents rebuilds only what changed and caches the rest. That matches the harness's fingerprint approach, now extended to the report itself.

### More value next

1. Keep each suite measurement's report under its own name (B18), so that reuse never depends on a shared path.
2. A dispute ruling that cites the implementation's behaviour as the reason a test "cannot pass" is checked against the specification first.
3. Measure LF.363–365 on the next runs. The goal is no needless repairs, unit defects reaching fixers, and no wrong unit tests shipped failing.

**Scoreboard:** 25 runs: 22 at 9/9, 2 at 5/9, 1 at 0/9. Next run: run-683a23ed, started 09:19 JST on 7788c76a (LF.316–365).

## Run run-683a23ed — notes-api-hono, gpt-oss-20b (2026-10-28 09:19–09:48 JST)

**Result:** hidden 9/9 in 29 minutes, among the fastest runs. The locked suite passed 16/16 and AC-15 shipped deferred. Mutation score 0.583, down from a five-run mean of 0.734. Four unit tests shipped failing.

### What worked

- **LF.364 and LF.365 fired live.** The failing-unit-tests defect reached fixers instead of being closed on acceptance files. The fixers were also told the unit test may be what is wrong, since the suite was fully green.
- **LF.366 was not needed in the end.** The suite was sent back with the exact corrected `request.baseURL` lines before LF.366 landed, and QA applied them this time. The automatic correction stays as the backstop for when QA does not.

### What can be improved

- **Unit-test fixes still change the product.** Both unit-test fixers edited `noteService.ts` and `app.ts` despite the note, broke 20 and then 6 other unit tests, and were reverted. The next step (B20) is that a unit-test defect beside a fully green suite first goes to a stage that may change only test files. The product is not touched until a test shows that the specification backs the failure.
- **The mutation probe ran out of rounds.** It fired in round 1 and raised three surviving mutants. Two fixes did not kill theirs ("the unit tests still pass with the change"), and the third had no round left. The mutation score fell to 0.583. The probe needs its own small budget once the suite is green, so it does not compete with defect fixes for the sprint's last round.

### How other harnesses handle this

- Mutation-guided test generation is now a common research pattern. AdverTest (2026) pairs a test-writing agent with a mutant-writing agent. STING (2026) accepts a new test only if it passes on the real product, fails on at least one surviving variant, and stays stable under behaviour-preserving changes. MuMuTestUp separates uncovered mutants (needing coverage) from surviving mutants (needing stronger assertions). The harness's "asked again after the fix" check matches STING's second criterion. Adding the first and third criteria, and the uncovered/surviving split, would sharpen what each mutation defect asks for.
- None of these papers report a fixed iteration budget, so a separate small mutation budget is this harness's own design choice to measure.

### More value next

1. B20: when the suite is fully green, send unit-test defects to a tests-only stage first.
2. Give the mutation probe its own round budget, and tell each mutant fixer whether its mutant was uncovered or surviving.
3. Keep measuring LF.363–366. So far there have been no needless suite repairs since LF.363.

**Scoreboard:** 26 runs: 23 at 9/9, 2 at 5/9, 1 at 0/9. Next run: run-b5a777f6, started 09:55 JST on 1951ddb (LF.316–366).

## Run run-b5a777f6 — notes-api-hono, gpt-oss-20b (2026-10-28 09:55–10:27 JST)

**Result:** hidden 9/9 in 32 minutes, including a pause and rewind. The locked suite passed 18/18 with nothing deferred. Mutation 0.833 (0.917 with unit tests). For the first time today the full review path ran before release: security review, the specialists' advice reviews, and the milestone review.

### What went wrong, and what was built

- **The dispute judged by the code, and this time it mattered (LF.368).** Attempt 1 ran out of fixes with 9 of 18 locked tests failing because the product returned `createdAt`/`updatedAt` on a note the brief defines as exactly `{id, title, body}`. The QA lead's dispute then set the AC-1 and AC-2 tests aside "because the implementation includes createdAt and updatedAt", and QA began loosening the suite to match the product. The prompt already said the code is not the standard; nothing checked the answer. Now a reason whose cause is what the implementation returns keeps the test locked and the product keeps the defect, while a reason that the test asks for what the criterion does not is still accepted. The run was 25 minutes old, so it was paused, the fix deployed, and the run rewound to the dispute. The re-made ruling kept the tests, the sprint was re-planned, and attempt 2 went 18/18.
- **What worked.** LF.364/365/367 together: the one unit-test failure in attempt 2 reached a fixer and was fixed in the product (a DELETE returning a body); the mutation probe raised two gaps and closed one by adding a test. The remaining gap (`||` made `&&` at a validation branch) ran out of tries, which is B21's case again.

### How other harnesses handle this

- Spec-grounded judging is the common answer to a judge anchoring on the output. LMR-BENCH's judge compares an implementation against the specification and a golden reference and classifies deviations; PRDBench scores agent work against a structured requirements document with a criteria scheme under the agent-as-a-judge paradigm. Practitioner guides note that supplying the judge an expected reference makes verdicts more consistent. Surveys document single-judge biases but none measured anchoring on implementation output specifically; LF.368's mechanical check on the reason's causal clause is this harness's own answer and is worth keeping even if the dispute prompt is strengthened.

### More value next

1. B21: a separate small round budget for mutation gaps once the suite is green; two of three runs today left one gap with no round to spare.
2. B18's second half: each suite measurement's report under its own name.
3. Measure LF.368 across the next runs: how many dispute reasons it holds, and whether any legitimate test-overasks reason is wrongly held (the log line names each).

**Scoreboard:** 27 runs: 24 at 9/9, 2 at 5/9, 1 at 0/9. Next run: run-0be12bd7, started 10:36 JST on 6f610a87 (LF.316–368).

## Run run-0be12bd7 — notes-api-hono, gpt-oss-20b (2026-10-28 10:36–11:36 JST)

**Result:** hidden 9/9 in 60 minutes, two pauses and rewinds included. The locked suite passed 9/9 with nothing deferred, the restart criterion among them. Mutation 0.75. One wrong unit test shipped failing. This run surfaced four harness problems, all fixed into it.

### What went wrong, and what was built

- **A 13.5-minute model reply (reply ceiling).** An agent-loop fixer's call returned 79,469 tokens: 2.5k of reasoning and then "END.FINISHED.No further output." repeated for 66,000 characters. Across the last six runs (1,479 calls) the 99th-percentile reply is 3.7k tokens and the largest legitimate one 4.1k. The reply ceiling was set to 12,000 through the existing `loop.sh ceiling` path (a per-request harness parameter with reply salvage; the server is untouched). No reply has hit it since.
- **Three fixes committed with an import the checker had flagged (LF.370).** Each rewrote a route importing `{ StorageService }` from a module that exports only a default instance. The language service reported TS2614 with the exact hint, but the write guard excused every "has no exported member" finding as "the other file may not be written yet". That is right while work orders run side by side and wrong in a fix stage. The excuse now holds only while the named module does not exist or a planned work-order file is still unwritten; otherwise the write is refused with the checker's hint. No fix was reverted in attempt 3 against five in attempt 2.
- **The dispute re-worded the same product-behaviour reason after each fix (LF.369, LF.371).** LF.368 held reasons that named "the implementation". This run's judge wrote "the product never loads the existing notes.json" (a verb the pattern lacked) and, after the rewind, "StorageService.load() is never called" (the product's own symbol as subject). The predicate now decides whatever the subject. Each fix was deployed and the run rewound to the dispute; the third ruling kept the restart test, and the fixers then implemented load-on-startup. Two attempts earlier, loosening the test would have shipped a product that loses data on restart.
- **Still short.** One unit test (a helper declared out of scope) shipped failing after two rewrites, and the mutation gap's fixer circled for 36 calls and was reverted. B20/B21 remain the right next steps.

### How other harnesses handle this

- The literature agrees that a judge's rationale is the weak point, not its verdict format. "Gaming the Judge" (2026) rewrote agents' reasoning while holding actions fixed and raised judges' false positives by up to 90%; the authors argue a judge must tie claims to observable evidence. Agent-as-a-Judge (2026) calls plain LLM judging "linguistic plausibility without verification" and proposes executable verification. The Verdict library composes judges from reasoning, verification and aggregation units. LF.368–371 are this harness's verification unit for the dispute: the ruling is checked against what kind of evidence it cites, and a ruling grounded in the product's behaviour is not a ruling about the test.
- The remaining gap is that the check is a pattern over wording. The evidence-grounded form would be: a disputed test is set aside only when the judge quotes the criterion text and names what the test asks beyond it; a ruling that cites no criterion text is returned for one more try with that requirement.

### More value next

1. B23: the dispute's ruling must quote the criterion it judges against; a ruling with no quoted criterion is asked once more, then held.
2. B21: a separate small round budget for mutation gaps (fourth run today to leave one for lack of a round).
3. Measure LF.370 and the ceiling over the next runs: reverts for "no longer starts", and replies cut at 12k with salvage.

**Scoreboard:** 28 runs: 25 at 9/9, 2 at 5/9, 1 at 0/9. Next run: run-88eaaede, started 11:46 JST on 7548dbda (LF.316–371, ceiling 12k).

## Run run-88eaaede — notes-api-hono, gpt-oss-20b (2026-10-28 11:46–12:28 JST)

**Result:** hidden 9/9 in 42 minutes. The locked suite passed 16/16 with nothing deferred. Mutation 0.5, the day's lowest. Six fixes reverted and twelve defects left open, both about double the five-run mean. The first run with LF.369–371, LF.370 and the 12k reply ceiling from the start: no dispute set a test aside, no fix was committed with a flagged import, and no reply looped.

### What went wrong

- **A revision turned a green suite red (B24).** The suite was 16/16 after 15 minutes and the full review path ran. The milestone review returned five real findings (persistence not atomic, validation middleware never mounted, directory mode). The revision work order for them touched 13 files and broke 12 of the 16 passing tests: the redrafted routes threw `Cannot read properties of undefined (reading 'send')`. The CI gate reported every regressed test and handed them to the fix rounds, which is what it is built to do, but twelve per-defect rewrites could not reach a root cause in the routing layer: four were reverted, the attempt exhausted, and only attempt 3's re-plan restored the product. About 20 minutes and all the mutation rounds went on recovering from the revision.
- **Scratch files in a product commit (B25).** The revision batch committed five `tmp-inline-*.cjs` one-liners a stage had run; later commits removed them, but they entered the product's history.
- **Mutation gaps for the sixth run today** were raised and left open for lack of a round (B21).

### How other harnesses handle this

- Checkpoint-and-rollback is now standard in coding-agent harnesses, usually as a shadow git repository snapshotted before each writing tool call: Hermes Agent (`/rollback`, whole tree or a single file, the rollback itself undoable), Cline's shadow-git snapshots, Aider's real commits with `/undo`, Claude Code's prompt-linked checkpoints. AgentRewind (2026) argues the conversation and the filesystem must roll back together so the agent does not keep a memory of changes that no longer exist.
- None of them gates the rollback on a test regression; that is left to the person. This harness already has the better trigger: the CI gate measures the batch against the last green state. B24 is the missing half: when a batch turns a mostly-green suite mostly red, revert it to the measured-green commit and redraft with the regressed tests and the batch's own diff named, exactly as `after_a_fix` does for a single fix. The revert must also reset the stage's memory of the batch (AgentRewind's point), which the harness's rewind already does at the stage level.

### More value next

1. **B24, next:** revert-and-redraft for a batch that regresses more than half of a green suite's passing tests; design first, since it changes routing after `ci_gate`.
2. B25: exclude `is_scratch` names from the batch commit, or remove them after the command.
3. B21 and B23 after that.

**Scoreboard:** 29 runs: 26 at 9/9, 2 at 5/9, 1 at 0/9. Next run: run-bc7c108f, started 12:35 JST on 7548dbda.

## Run run-bc7c108f — notes-api-hono, gpt-oss-20b (2026-10-28 12:35–13:44 JST)

**Result:** hidden 9/9 in 69 minutes, 14 of them dead. The locked suite passed 21/21 with nothing deferred. Mutation 0.5. Twelve unit tests shipped failing.

### What went wrong, and what was built

- **The worker was OOM-killed mid test round (LF.375).** At 13:12 the Celery pool process was SIGKILLed at the container's 8 GiB limit, and the run sat "running" for 14 minutes while the periodic orphan check reported a live task. Cause: the unit tests post megabyte bodies to the product's *default* data directory on every round; `data/notes.json` had reached 205 MB for 24 records, and the service parsed all of it per request inside the same container. The acceptance configuration already starts the service with a fresh `DATA_DIR`; the unit command had none. Now every test-category command gets a fresh directory under the project's git-ignored `test-results/` in the pack-declared variable, unless the caller set it. The run was recovered by an immediate deploy whose restart ran orphan recovery.
- **A new check fired, then needed a correction (LF.373, LF.374).** A test that reads `start.sh` and asserts its text cannot pass: the harness keeps that file. The first version also reopened a *green* suite for a passing, vacuous version of that test and cost a repair and three QA rounds; it now counts only a failing test.
- **Three mutation gaps, two judged equivalent.** The "judged equivalent" closure worked twice (`>` to `<=` on a branch the current implementation cannot reach), which is the right outcome; the third gap outlived the rounds again.
- **Still short.** Twelve unit tests shipped failing after the last fix was reverted for breaking 43 others; the escalation path ("every acceptance test passes and only the unit tests fail") closed the sprint correctly.

### How other harnesses handle this

- Memory kills are a known sandbox failure, and the literature's point is that a single container budget is the wrong granularity: AgentCgroup (2026) argues per-tool-call cgroup budgets because demand fluctuates per call, while NVIDIA's OpenSandbox guide distinguishes a killed child (`oom_kill > 0`, sandbox alive) from a group kill that takes the whole cgroup. This harness already reads `memory.events` at restart (`_worker_ran_out_of_memory`); the gap is doing so between restarts (B26) and bounding what a test run can grow, which LF.375 does by isolating its data.
- None of the sources isolate test data per run; it is this harness's own measure, and it mirrors what its acceptance configuration already did.

### More value next

1. B26: the periodic orphan check treats a pool-process kill as orphaning its rows and recovers at once.
2. A per-tool-call memory watch: read the cgroup's `memory.peak` after each sandbox command and name the command that approached the limit, so the next kill is explained before it happens.
3. B21 (mutation budget) and B23 (dispute must quote the criterion) remain.

**Scoreboard:** 30 runs: 27 at 9/9, 2 at 5/9, 1 at 0/9. Next run: run-f9e8735b, started 13:45 JST on e0eadeb9 (LF.316–375).

## Run run-f9e8735b — notes-api-hono, gpt-oss-20b (2026-10-28 13:45–16:00 JST)

**Result:** hidden 9/9 in 135 minutes (86.5 active), the day's longest run. The locked suite passed 15/15 with nothing deferred; mutation 0.583 (0.667 with unit tests); seven unit tests shipped failing. Eight fixes (LF.376–383) were built from it, most of them deployed into it.

### What went wrong, and what was built

- **A green suite was reopened twice before any round (LF.377).** A right test reading a missing `Location` header produced `TypeError: expect(received).toMatch … Received has value: undefined`, and the harness read the `TypeError` as the test's own bug. A matcher given nothing by the product is now the product's defect.
- **Two reverts for one wrong import, two fixers that gave up on "the environment" (LF.378, LF.379).** An installed package's missing export is now refused at the write with the checker's hint; inline `node -e` code written as a module now runs from a `.mjs` file instead of a `.cjs` file that cannot `import`.
- **Two sprint attempts on a 500 nobody could see (LF.380–382).** POST answered 500 and the service logged nothing: the product's eight `catch` blocks returned JSON without writing the error. LF.380 told fixers the handler hid the cause; they ignored it. LF.381 named the eight lines and handed the file to the fixer; the log then read `undefined.storage`. LF.382 named the contract break behind it: `createApp(storage)` takes a parameter the kept start file never passes. Its first round raised it, and one fix took the suite from 7/15 to 15/15.
- **The contract fix was not believed (LF.383).** The contract defect was judged by unrelated failing unit tests and left open, so attempt 2 was spent over a green suite; it is now settled by the check that raised it. A rewind to replay the round came one second too late (the verdict was written before the rewind point), so the handover now says to rewind to before the wrong verdict.

### How other harnesses handle this

- The swallowed-500 case is a known observability gap. New Relic's documentation notes that a 500 set from a caught exception carries no stack trace because no exception reached the agent; Future AGI's harness guide gives the same fix as LF.380–381 (record the exception inside the `except`). Tool vendors answer it from outside the code: AgentSensor intercepts dev-server crashes with source-mapped traces, and Lightrun's runtime sensor lets an assistant query the running service. One study finds agents recover observability artifacts at the source level but miss the diagnostic semantics, so generated code needs explicit instrumentation checks, which is what `where_errors_become_5xx` is.
- A stronger, still general next step for this harness: wrap the service the suite starts so an unhandled or caught-and-answered 5xx is logged by the harness itself (a request-level hook in each service pack's start file), instead of relying on the product to log.

### More value next

1. Deep-review plan item 9 (agent-loop fixers capped at 16 calls, surrender returns the defect to the rewrite path): 34 defects left open this run, most by loops that gave up.
2. A request-level 5xx log in each service pack's kept start file, so the next swallowed error is visible at the first round, not the third.
3. Plan item 5 (fingerprint-guard every closure): the suite count was briefly read from a reverted fix's measurement again.

**Scoreboard:** 31 runs: 28 at 9/9, 2 at 5/9, 1 at 0/9. Next run: run-f37ca8de, started 16:05 JST on 5ad49d7 (LF.316–383). Sources: [New Relic: 500s without stack traces](https://docs.newrelic.com/docs/apm/agents/apm-no-stack-traces.md), [Future AGI: agent harness silent failures](https://futureagi.com/blog/agent-harness-silent-failures/), [AgentSensor](https://mcpservers.org/servers/arif-js/agentsensor), [Lightrun: why observability isn't enough for coding agents](https://lightrun.com/blog/ai-observablity), [Verify observability in agent-generated code](https://agentpatterns.ai/verification/verify-generated-code-observability/).

## Run run-f37ca8de — notes-api-hono, gpt-oss-20b (2026-10-28 16:05–16:52 JST)

**Result:** hidden 9/9 in 47 minutes (46 active), with no fix reverted, against seven on the run before. The locked suite passed 11/11 with nothing deferred; mutation 0.583 (0.667 with unit tests). The first run with the whole LF.376–385 set, and LF.384 (a 16-call cap on fix stages) and LF.385 deployed into it.

### What worked

- **The fix-stage cap held from the moment it landed.** Only one fix stage exceeded 16 calls (30, from 16:23 to 16:30 JST, before the 16:33 deploy); every stage after it stayed under, median five calls. No fix was reverted and no criterion was deferred.
- **Three mutation gaps were closed as "judged equivalent"** with a reason that names why the branch cannot be reached in the current code, and one by a test that notices the change. The probe finished inside the sprint for the first time today.
- **LF.385 fired on its first chance.** A restart test read `process.env.DATA_DIR`, which the suite gives only to the server it starts; its fixer said as much ("unable to ensure DATA\_DIR is propagated") and the next review sent it back to QA with the pattern that works. The run's dispute correctly set aside a test that spawned `node` itself.

### What can be improved

- **The QA lead's open findings at lock are a list of real gaps the suite never checks:** list ordering, restart preserving titles and bodies, start through `sh start.sh`, `Content-Type` on success. Four of them, every run. These are exactly deep-review plan item 16 (contract-line coverage at review); the evidence now favours building it next.
- **Agent-side efficiency KPIs regressed** (tool failures 25%, redundant reads 26%, identical calls 4.7%), mostly in the QA repair cycles; plan item 10 (targeted QA repair instead of a full re-author) addresses that directly.

### How other harnesses handle this

- Fixed step caps are the baseline; the 2026 evidence favours stopping on lack of progress. A June 2026 write-up on early termination for Codex CLI reports 31.8% lower cost with a 2.7% higher resolution rate, the stop firing on only 9–14% of issues; a semantic early-stopper for iterative loops cut tokens 38% against a fixed `max_iterations` at equal quality, while a judge-gated variant cost more than it saved; BAGEN's "this looks impossible" stop saved 28–64% of tokens on failed rollouts for a 1–4% success drop. AWS's agentic guidance pairs a hard cap with confidence-based termination. LF.384 is the hard cap; the no-progress stop (12 identical calls) is already there, and the plan's next half sends a surrendered defect back to the cheap rewrite path rather than another loop.

### More value next

1. Plan item 16: contract-line coverage at the suite review (the four open findings every run).
2. Plan item 10: targeted QA repair of only the named tests.
3. Plan item 9, second half: a fix stage that ends with nothing changed returns its defect to the rewrite path.

**Scoreboard:** 32 runs: 29 at 9/9, 2 at 5/9, 1 at 0/9. Next run: run-280ad6d0, started 16:55 JST on 99449cec (LF.316–385). Sources: [Early termination for coding agents (Codex CLI, EET)](https://codex.danielvaughan.com/2026/06/21/early-termination-strategies-coding-agents-codex-cli-cost-efficiency-eet-agentstop-hooks/), [semantic early stopping, 2606.27009](https://www.emergentmind.com/papers/2606.27009), [BAGEN budget awareness, 2606.00198](https://www.emergentmind.com/papers/2606.00198), [AWS agentic AI lens: bounded iteration](https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentperf02-bp01.md), [When should an agent stop](https://pub.towardsai.net/when-should-an-agent-stop-the-anatomy-of-termination-17644145309a).

## Run run-c9584d38 — notes-api-hono, Qwen3.6-35B-A3B MTP (2026-10-28 17:25–18:22 JST)

**Result:** hidden 9/9 in 57 active minutes, the first run on the owner's new model. The locked suite passed 16/16, AC-15 shipped deferred, mutation 0.583. Escalated after attempt 4 with only a stack-mismatch defect open.

### The new model, measured

| Measure | Qwen3.6 (this run) | gpt-oss-20b (today's ten runs) |
| --- | --- | --- |
| Model calls | 109 | 93–555 (median about 220) |
| Output tokens per call | about 3,200 (345k / 109) | about 550 |
| Prompt-cache share | **64%** | not reported by LM Studio |
| Tool-call failure rate | **8.6%** | 17–25% |
| QA authoring tool failures | 0 of 20 | about a quarter |
| Reverted fixes | 7, all one cause | 0–18 |

It writes about six times more per call and needs about half the calls, makes a third of the tool errors, and its cache share is the first real one this loop has measured. The deep diagnosis predicted its two weak spots correctly: it does not heed a refusal (the architect repeated a refused package lookup) and it answers in text when a schema is merely offered (forced for it already).

### What went wrong, and what was built

- **It writes `vitest` tests out of habit (LF.386, LF.388).** The pack's kept unit command runs `node --test`; the drafter imported `vitest` in two test files and added it to the manifest. The cross-file check then said "package.json installs vitest", and seven fixes in four attempts removed it from the manifest alone, broke the 19 tests that still imported it, and were reverted. A test importing another runner is now refused at the write with the `node:test` correction (LF.386), and the mismatch defect names the importing files and hands them to the fixer (LF.388). The seven reverts all came before LF.388 reached the run.
- **A third restart-test shape (LF.387).** The test wrote through the suite's own server and read the note back from a fresh service; the QA lead named it at the lock, and LF.361 missed it because only the two-service shape was checked. LF.385–387 are three variants of one mistake; a fourth would argue for rewriting the restart guide rather than another check.
- **One runaway reply** of 32,768 tokens in a consult (3 minutes, nothing kept). No reply ceiling yet: one correct architect reply was 22,810 tokens.

### How other harnesses handle this

- Community reports agree the model is a step up for local agentic coding (73.4 SWE-bench Verified and 51.5 Terminal-Bench 2.0 by the published card, cited secondhand), and that tool calls depend on the right parser: vLLM needs auto tool-choice with the `qwen3_coder` parser or calls silently fail. Here the server's Hermes parser passed every tool probe. Qwen recommends keeping thinking on for agentic work with `preserve_thinking`; this harness carries reasoning itself, and the measured 3,200 tokens per call is that thinking. Anecdotally, lower quantisations loop or cut off mid-generation and Q5 is the sweet spot, which is worth checking against the one runaway seen here.

### More value next

1. Measure thinking off for routine edit stages against thinking on (output tokens per call, fixes per run), and bring the numbers to the owner before changing anything the harness sends.
2. Plan item 16 (contract-line coverage at review) and plan item 10 (targeted QA repair) remain next in the plan.
3. If restart tests fail a fourth way, rewrite the restart guide around one worked example.

**Scoreboard:** 33 runs: 30 at 9/9, 2 at 5/9, 1 at 0/9. Next run: run-1f70c434, started 18:26 JST on c4f11015 (LF.316–388), Qwen3.6. Sources: [Qwen3.6-35B-A3B: the local model that changes the agentic cost equation](https://codex.danielvaughan.com/2026/04/16/qwen36-35b-a3b-local-agentic-coding-breakthrough/), [Serving Qwen3.6-35B-A3B with vLLM and tool calling](https://dev.to/lavellehatcherjr/serving-qwen36-35b-a3b-with-vllm-and-building-a-coding-agent-with-tool-calling-2kob), [Benchmarking local coding LLMs](https://dev.to/kuroko1t/benchmarking-local-coding-llms-11-realistic-tasks-232-runs-and-the-bugs-my-bench-found-in-my-46pl), [Qwen3.6-35B-A3B review](https://www.buildfastwithai.com/blogs/qwen3-6-35b-a3b-review), [community note on quantisation](https://reddit.sentinel-team.org/posts/1temio0/snapshots/2026-05-23T00%3A36%3A34.219378Z).

## Run run-1f70c434 — notes-api-hono, Qwen3.6-35B-A3B MTP (2026-10-28 18:26–19:28 JST)

**Result:** hidden 9/9 in 61 active minutes, with **no fix reverted, nothing deferred, and no KPI regression**. The locked suite passed 23/23, mutation 0.75 (0.833 with unit tests). The cleanest run of the day.

### What worked

| Measure | This run | First Qwen3.6 run | gpt-oss-20b runs today |
| --- | --- | --- | --- |
| Tool-call failure rate | **2.1%** | 8.6% | 17–25% |
| Prompt-cache share | **74%** | 64% | not reported |
| Reverted fixes | **0** | 7 | 0–18 |
| Model calls | 133 | 109 | median about 220 |
| Fix rounds to green | 2 | 4 attempts | 2–3 attempts |

- The draft broke the pack's contract (it renamed `createApp`). LF.382's check raised it at the first round, the second fixer restored it, and all 23 tests passed on the next measurement. The "does not start" defect then closed itself on that measurement.
- No unit test imported `vitest`, so LF.386 had nothing to refuse and LF.388 nothing to name: this draft followed the pack's `node:test` guide.
- A mutation gap was judged equivalent, and correctly: the planted change was to a variable written and never read (the routes keep their own id counter).

### What can be improved

- The QA lead's open findings at lock again name real gaps the suite never checks: the initial store being empty, 404 bodies, and "nothing was stored" assertions that search for markers rather than counting. This is plan item 16 (contract-line coverage at review), now the clearest next step on either model.
- One unit test shipped failing, and one mutation gap ran out of rounds (B21).

### How other harnesses handle this

- The 74% cache share comes from llama-server's per-slot prompt cache: it keeps the previous request's KV in the slot and prefills only the new suffix, and assigns a new request to the slot whose prompt is most similar (`--slot-prompt-similarity`). Agent workloads share a long prefix and then diverge, which is the case it serves well. `--cache-reuse N` additionally reuses chunks after an earlier part of the prompt changes. A user report suggests more distinct prompt families than slots defeats reuse; with two slots and one run, that limit is not reached. Plan item 14 (a byte-stable stage prefix) is what raises the share further.

### More value next

1. Plan item 16: contract-line coverage at the suite review.
2. Plan item 10: targeted QA repair of only the named tests.
3. Measure thinking off for routine edit stages against thinking on, before proposing a change to what the harness sends.

**Scoreboard:** 34 runs: 31 at 9/9, 2 at 5/9, 1 at 0/9. Next run: run-b4f264fe, started 19:35 JST on c4f11015, Qwen3.6. Sources: [llama.cpp: KV cache reuse with llama-server](https://github.com/ggml-org/llama.cpp/discussions/13606), [prefix caching (same-slot KV reuse)](https://llama-cpp-ex.hexdocs.pm/007-prefix-caching.html), [llama.cpp slot pinning](https://cdn.jsdelivr.net/npm/pi-reasoning-zip@0.7.1/docs/llama-cpp-slot-pinning.md), [Liquid AI: llama.cpp chat deployment](https://docs.liquid.ai/deployment/on-device/llama-cpp/chat).

## Run run-b4f264fe — notes-api-hono, Qwen3.6-35B-A3B MTP (2026-10-28 19:35–21:13 JST)

**Result:** hidden 9/9 in 98 active minutes over four sprint attempts. The locked suite passed 16/16, nothing deferred, one fix reverted, tool failures 3.9%, cache 69%. Mutation 0.417 for the suite alone (0.667 with unit tests), below the five-run mean.

### What happened

- **An intermittent crash cost two attempts.** The service wrote every save through one fixed temp file, `notes.json.tmp`; two saves at once raced, the second `rename` hit `ENOENT`, the rejection went unhandled, and Node exited mid-suite. The same product measured 15/16 in one round and 6/16, then 3/16, in others. The harness bundled the failures by root error and carried the stack trace, but each fixer still worked on a criterion; the race was fixed only by the revision.
- **The dispute caught a real test bug.** AC-9 asserted an empty store after AC-1 had created a note in the same shared data directory; it was set aside and repaired, and the suite relocked green.
- **The milestone review caught what the suite missed.** `PUT /notes/:id` answered 200 with the new note but saved the original array, so every update was lost on the next read. AC-4 checked only the response. The revision fixed it; a hidden test that reads after an update would otherwise have failed.
- **Both mutation gaps of attempt 3 were closed with real tests** (each fails on the planted change and passes without it).

### What can be improved

1. **A crash mid-suite should be one blocking defect.** A start failure already becomes one "the product does not start" defect; a service that exits while the suite runs (the runner's `[WebServer]` output ends in an uncaught exception, later requests are refused) should become "the product crashed while the suite ran", with the trace, ahead of every criterion it took down.
2. **The release contract check could not read 16 of the interface-contract lines** (`AC-1 POST /notes { title: string, body: string } -> { id: number, ... }`): it reads statuses, not bodies. Contract-line coverage at review (plan item 16) and a body-shape form of the contract would have caught the PUT persistence bug as a contract gap.
3. **Inter-test data dependence** (AC-9) was found by the dispute, not by a check (plan item 20).

### How other harnesses handle this

- Property-based contract testing from a machine-readable schema is the established answer to "the response looked right but the state is wrong": Schemathesis generates inputs from an OpenAPI or GraphQL schema, uses the contract as the oracle, and in stateful mode chains calls (create, then read back), which is the PUT-then-GET check this suite lacked. A Claude Code skill wrapping it exists, but adoption is low and nothing documents it inside an agent harness. The general lesson for this harness: the interface contract it already writes should carry body shapes and be executed as calls chained the way the criteria read, not only as status checks.

### More value next

1. The crash-mid-suite rule (one blocking defect with the trace).
2. Plan item 16 with body shapes: each contract line exercised, writes read back.
3. Plan item 20: a static check for a test reading data it did not create.

**Scoreboard:** 35 runs: 32 at 9/9, 2 at 5/9, 1 at 0/9. Next run: run-32568792, started 21:16 JST on c4f11015, Qwen3.6. Sources: [Schemathesis (PyPI)](https://pypi.org/project/schemathesis/), [Schemathesis paper, arXiv 2112.10328](https://arxiv.org/pdf/2112.10328.pdf), [What is Schemathesis](https://apidog.com/blog/what-is-schemathesis/), [Schemathesis property-based API testing guide 2026](https://qaskills.sh/blog/schemathesis-property-based-api-testing-guide-2026), [Schemathesis skill for agents](https://skillselion.com/skills/aeondave/malskill/schemathesis).

## Run run-32568792 — notes-api-hono, Qwen3.6-35B-A3B MTP (2026-10-28 21:16 – 10-29 00:08 JST)

**Result:** hidden 9/9 in 142 active minutes over three sprint attempts, the longest Qwen3.6 run. The locked suite passed 11/11, nothing deferred, mutation 0.75 (0.833 with unit tests), cache 66%, tool failures 4.6%. Seventeen fixes were reverted, almost all in attempt 1, before the root cause was named. Five harness fixes were built from it (LF.390–393 and the rewind).

### What went wrong, and what was built

- **The product never created its data directory (LF.390).** The suite's kept configuration hands the service a fresh `DATA_DIR` path; every first write failed `ENOENT` and every request answered 500. The packs' data guide never said the directory may be missing; it now does, and the first redraft after the change called `mkdirSync(..., { recursive: true })` and went from 3 to 10 of 11 tests. Hidden tests that start the service on a fresh folder benefit directly.
- **Two fix-stage replies of 28k and 23k tokens took eight minutes (LF.391).** Fix-stage replies are now capped at 12,000 tokens; other stages keep their length (an architect's correct specification reply measured 22,810).
- **A test read `created.body.id` (LF.392).** On Playwright's response `body()` is a method giving bytes, so the id was `undefined` and two attempts of fixes went on a test no product passes. The check that already caught uncalled `.status` now catches `.body.<field>` with the correction `(await res.json()).<field>`; after a pause, deploy and rewind, it sent the test back to QA at once.
- **A paused stage kept running for five minutes (LF.393).** Its agent loop runs in a thread the stopped task does not end; it called the model beside the rewound run and could have written into the restored workspace. A stopped run is now marked in the process that stopped it, and every model call checks the mark.

### What can be improved

- **The milestone reviewer asserted an API that does not exist.** It required Hono's `bodyLimit` as a constructor option and called the code's comment "factually incorrect"; in Hono the limit is the `hono/body-limit` middleware. Had the run gone on, a revision would have chased it. The harness already has a `module_exports` tool and installed packages to check against.

### How other harnesses handle this

- The evidence favours a deterministic check against the installed or versioned API surface over another model's judgement. A DocAware study grounding a model in version-specific documentation raised F1 from about 71% to 87% (recall 76% to 99%); the Hallucination Inspector (EASE 2026) checks API code against a symbol table built from the official specification and beat LLM-as-a-judge baselines; a verified-reasoning study caught unwarranted assumptions about library functions by treating them as uninterpreted. HalluJudge flags review comments not grounded in the code (67% agreement with developers). For this harness: a review finding that names a package's API should be checked against what the installed package exports before it becomes a defect, the same way LF.341 checks a fixer's "cannot import X" claim.

### More value next

1. A review finding naming a package API is verified against the installed package (`module_exports`) before it is raised.
2. Plan item 16 with body shapes, still the clearest lever on the hidden score.
3. The restart guide's worked example, if a fourth restart-test variant appears.

**Scoreboard:** 37 runs: 34 at 9/9, 2 at 5/9, 1 at 0/9. Next run: run-12540387, started 00:15 JST on 1584efde (LF.316–393), Qwen3.6. Sources: [Systematic review of code hallucinations (2511.00776)](https://arxiv.org/pdf/2511.00776), [Towards verified code reasoning (2509.26546)](https://arxiv.org/pdf/2509.26546), [HalluJudge (2601.19072)](https://arxiv.org/abs/2601.19072v1), [Hallucination Inspector artefact](https://zenodo.org/records/19633303), [DocAware summary](https://www.synapsesocial.com/papers/69ba43e94e9516ffd37a5a44).

## Run run-12540387 — notes-api-hono, Qwen3.6-35B-A3B MTP (2026-10-29 00:15 – 00:45 JST)

**Result:** hidden 9/9 in 29.8 active minutes, the fastest run in the ledger (the previous Qwen3.6 run took 142). It used 88 model calls and had zero reverts. The locked suite went 12/12 green at round 0. Mutation score was 0.75, or 0.917 with unit tests. Cache share was 64% and tool failures 9.6%. It is the first run on a harness carrying LF.390–393, and none of the problems those fix came back: the data directory was created, no fix reply ran long, there were no `.body.<field>` reads and no stale threads. The two mutation gaps were closed with real tests.

### What went wrong, and what was built

- **The milestone review asked for a change no revision may make (LF.394).** Its finding SR-6 (major) asked for SIGTERM/SIGINT handlers in `src/main.ts`. That is the pack's kept start file, which the harness restores before every run. The security review already leaves such findings out; the milestone review did not, so the sprint would have been sent back for work nobody may do. A gating milestone finding whose named files are all harness-kept is now recorded as minor, with a note saying why. It is kept rather than dropped, because an emptied `changes_required` review is asked again.
- **Edit failures in the fix stages.** Three of the four came from a `find` text that appears more than once in the file. The tool already says so and asks for more context, and the retries succeeded. Nothing was built for this.

### What can be improved

- **The release noted four contract lines it did not check** (parameterised routes and a successful write), plus a PUT-404 contract line it judged unkept. Hidden tests passed, so the product is right, but the release check reads these shapes weakly. This is plan item 16: contract-line coverage, with body shapes and writes read back.
- **A mutation flipping `||` to `&&` in validation went unnoticed by the locked suite.** The unit tests caught it, which is why the score is 0.917 with them. A targeted test for combined validation conditions would close it.
- **The design review left four contradictions open:** 400 or 422, graceful shutdown deferred yet described, an unnamed body-limit middleware, and who creates `DATA_DIR`. The product survived them, but each one is a chance for a later stage to chase the wrong side.

### How other harnesses handle this

- Protected files are usually enforced at the tool layer, and the reviewer is told about them. Aider marks files read-only so the model can see them but not edit them. Claude Code's permission rules can deny edits to a path. This harness already restores kept files and refuses writes to them, but its reviewers were not told about them. LF.394 closes that gap for the milestone review.

### Added value

- With LF.390–393 in place, the same brief on the same model went from 142 to 30 active minutes and from 17 reverts to 0. That is the clearest measured gain from one batch of fixes so far. LF.394 removes the one remaining way this run could have lost a sprint.

## Run run-92d13786 — notes-api-hono, Qwen3.6-35B-A3B MTP (2026-10-29 00:51 – 01:57 JST)

**Result:** hidden 9/9 in 65.8 active minutes over 168 calls (`mixed_versions`: LF.395–396 were deployed at 01:42). Mutation score was 0.833, or 1.0 with unit tests. All 18 criteria were green, but the locked suite ended 13 passed and 1 failed. Most of the time went into the acceptance suite, not the product: one reopen after the first draft, and a 46-call repair. Three harness fixes came out of it (LF.395–397). The two redundant-read KPIs regressed (33% against a 15% mean), all of it from the repair stage.

### What went wrong, and what was built

- **`request.newContext` on the Playwright fixture (LF.395).** The restart test reached the second service through a method the `request` fixture does not have. The same mistake is in locked suites from four earlier runs. It throws only once the first service has run, so the review locked the suite and it was reopened after the first draft. A static check now finds it before the lock and gives the correction: send the request to the full URL.
- **A cut memory note misled the repair (LF.396).** With its read tool withheld, QA saw a diff of its own edits cut after the first two hunks. It took that as everything it had done, disbelieved the edit tool's `already_applied`, and resent the third edit five more times until its budget ran out. A cut diff now names each hidden hunk's lines and first changed line, and says those changes are in the file.
- **A test asserting 200 for a create the contract answers with 201 (LF.397).** It looped over `/health` and `POST /notes` with one `toBe(200)`, and it had no criterion tag. So every criterion read green beside a red suite. The model reviewer had noticed it but locked the suite with it open. A deterministic check now names a success status the contract does not give for that method and path, in direct calls and in loops over endpoint entries. It found no false positives on 25 earlier locked suites.

### What can be improved

- **The product crashes (500) on a request with no JSON body.** Both `POST /notes` and `PUT /notes/:id` did this. The release contract probe found it, but the probe runs only at release, so it became a release note, not a defect. Hidden tests don't send empty bodies, so the score didn't show it; real clients would. The next step is to run the contract probe at a test round once the suite is green, and raise a 5xx as a defect. It will be built behind a switch and measured.
- **Tests that name no criterion.** The suite review only refuses a suite where no test names a criterion. A single untagged test proves nothing and hides its failures from the criteria view. Its failures should at least be visible to the rounds.
- **Suite repairs are the slowest part of these runs.** On this model, review rounds plus repairs took longer than building the product. Plan item 10 (targeted QA repair: send only the named tests and their exact corrections) fits here.

### How other harnesses handle this

- **Contract-driven API testing tools probe malformed input as a matter of course.** Schemathesis generates requests from an OpenAPI schema, including missing and malformed bodies, and treats any 5xx as a failure by default. RESTler (Microsoft Research) fuzzes stateful REST APIs and reports 500s as bugs. Both make "never a 500 for bad input" a default check rather than a criterion someone must write. This harness has the contract and the probe runner already; what it lacks is running them before release and treating a 5xx as a defect.
- **Coding agents keep the model's view of a file consistent with the file.** Aider resends the whole edited file after an edit; others return the post-edit region in the tool result. LF.396 takes the cheaper route of saying plainly what was cut.

### Added value

- LF.395 and LF.397 remove two suite mistakes that cost a reopen each and appeared in five runs and one run respectively. LF.396 removes a loop that can hit any stage whose read tool is withheld. The next step, the contract probe in the test rounds, would turn a class of crashes the product ships with today into defects fixed before release.

## Run run-d907728e — notes-api-hono, Qwen3.6-35B-A3B MTP (2026-10-29 02:12 – 02:46 JST)

**Result:** hidden 9/9 in 33.6 active minutes over 107 calls, on a single harness version (1e42bed6, the first with LF.398 on). The locked suite passed 20/20. Mutation score was 0.667, or 0.917 with unit tests. Two unit tests shipped failing: the one fix attempt broke 35 other tests and was reverted, and the green sprint settled at its first exhaustion (owner decision, LF.327).

### What went wrong, and what was built

- **LF.398 never fired, for two reasons (LF.399).** First, it was asked only of a fully clean round, and the failing unit tests kept every round from being one, though the acceptance suite was green. Second, six of the eight contract lines followed none of the contract's forms, so there was nothing to probe:
  - `AC-10, AC-3, AC-4, AC-5 GET/PUT/DELETE /notes/{id} for non-existent -> 404`
  - `AC-13, AC-18 POST/PUT /notes with invalid title -> 400 or 422`

  The contract reader now takes several methods per line, and a note before the arrow, including parenthesised ones such as `(duplicate)`. A noted line is about a request the bare probe doesn't send. So at release a mismatch on it is listed as unchecked, never as a broken contract; only a 5xx counts as a failure. The round now asks for server errors whenever the locked suite is green, whatever else it found. The reader corpus showed 16 earlier contract lines read differently, and each was reviewed before the new reading was accepted.
- **`__dirname` in an ES-module test, again.** Two runs in a row had it. The suite's own run catches it before the lock, at the cost of a short repair, so nothing was built for it.

### What can be improved

- **The unit-test fix that broke 35 tests.** One attempt and a revert, then the sprint settled and the run shipped two failing unit tests. A second, smaller attempt that sees the revert's evidence (the 35 tests it broke) would likely close it. The contrastive fix candidates in B22(a) fit this case directly.
- **The design review left the same kind of contradiction open again:** which file creates `DATA_DIR` and checks `PORT`. The pack's kept `start.sh` does neither, but three sections of the specification said it does. The architect could be told which files the pack keeps and what they do, so it doesn't attribute behaviour to them.
- **No review read the product's code.** Fast delivery accepted the sprint on its locked suite alone. That is fine for the score, but nothing looks at the code's quality. A cheap one-pass review at release, which records findings and gates nothing, would give the owner that view.

### How other harnesses handle this

- **API contracts are usually machine-readable specifications, not free-form lines.** Tools such as Schemathesis and Dredd take an OpenAPI document, so every operation, parameter and response is structured, and checks are generated rather than parsed. This harness asks the architect for one line per check in a small text form. That is easy for a small model to write but easy to write loosely, as here. Accepting what models actually write, as LF.399 does, is the cheaper step; asking for a structured contract would be the larger one.

### Added value

- LF.399 turns compound lines, like the six this run wrote, from unchecked into checked. The release report no longer calls a noted line broken because the probe sent the wrong request. And LF.398's crash detection now also runs on rounds where only the unit tests fail.

## Run run-99a07406 — notes-api-hono, Qwen3.6-35B-A3B MTP (2026-10-29 03:05 – 04:26 JST)

**Result:** hidden 9/9 in 73.4 active minutes over 175 calls. The locked suite passed 11/11. Mutation score was 0.75, or 1.0 with unit tests. The run was `mixed_versions`: LF.400–402 were deployed into it, and it was rewound once past a wrong replan. It was the most instructive run of the night. Three separate harness weaknesses each cost a stretch of time, and each is now fixed.

### What went wrong, and what was built

- **A stage that hit a wall, then started over blind (LF.400).** The unit-test writer found a real crash, `DELETE` answering 500, in `app.ts`, a file the backend work order owns, and was refused the edit. It then spent its remaining calls building a child-process runner around the storage module's in-memory state, and gave no answer. The fresh attempt's note listed only the commands it had run, so it picked up the half-built runner. A restarted stage is now told why its last attempt ended, which files it was refused and where those findings belong (`blockers`, `defects`), and which files it changed.
- **A one-line fix that two fixers missed (LF.401).** `c.body('', 204)` throws "Invalid response status code 204" on Node. The fixers saw the message, but one rewrite was reverted and the next left the call unchanged. Stack packs can now declare known errors, a message phrase mapped to its cause, and a defect carrying the phrase gets the cause added. Both Hono packs declare the 204 case, which appears in 4 of 35 earlier products. After the deploy, the next fixer's resolution quoted the cause and fixed it.
- **A green sprint sent back for scratch files (LF.402).** With every acceptance and unit test passing, the sprint was planned a third time. The reason was a cross-file finding that the dead attempt's leftover files sat outside the test script's pattern, and it advised widening a script the pack keeps and restores. A green sprint now settles beside findings read from the files, which are recorded as known issues. The finding now says to rename or delete stranded files, never to change a kept script. The run was rewound to the round before the wrong verdict; the replayed round was clean and the run released ten minutes later.
- **Two smaller fixes (LF.403).** The contract reader now handles a note among the statuses: `-> 201 (with Note object) or 400/422`. And `loop.sh corpus accept` had been undone by every scored run's harvest; it now copies the accepted corpus into the worker as well.

### What can be improved

- **Leftover files from a dead attempt stay in the product.** The child-process runner and the `child-verify-*.mjs` files its tests wrote are still in `test/`. A restart could remove what the dead attempt created and that nothing imports. LF.400 asks the model to do it; the harness could do it itself.
- **Module-level state made the storage code hard to unit-test.** The architect's file plan put the notes array at module scope. A design guide line asking for state the caller passes in, or a factory, would make tests trivial and the product easier to reason about. Stack-specific wording would belong in the pack.
- **QA keeps labelling testable criteria "not automatable".** It happened in three runs. It's harmless, but the field's wording may invite it.

### How other harnesses handle this

- **Starting over with lessons.** Retry loops in coding agents usually carry a reflection forward, not just a record of actions. Reflexion-style agents write a short verbal reflection after a failed attempt, and SWE-agent-style trajectories record what failed and why. The harness's carry-over note was all facts and no reason; LF.400 adds the reason and the boundaries the attempt ran into.
- **Known-error knowledge bases.** Some build-repair tools match compiler or runtime errors against a curated table of fixes before handing off to a model, so common errors get fixed instantly and the model handles the rest. LF.401 is the same idea, kept per stack pack so that it stays stack-agnostic.

### Added value

- These four fixes target waste, not score. This run lost roughly 30 minutes to the three issues. Each is now handled the first time it happens: a restart knows its predecessor's dead end, a known error arrives with its cause, and a green product is released rather than redrafted.

## Run run-0d97a96c — notes-api-hono, Qwen3.6-35B-A3B MTP (2026-10-29 04:40 – 05:55 JST)

**Result:** hidden 9/9 in 69.5 active minutes over 153 calls. The locked suite passed 22/22. Mutation score was 0.917, the best of the night. The run was `mixed_versions`: LF.405 was deployed, and the run was rewound once to the dispute that had kept an unpassable test locked. It was released after one milestone revision. Four harness fixes came from it (LF.404–407).

### What went wrong, and what was built

- **A plan sent back for a file nobody writes (LF.404).** The sprint scope named `notes.json`, the data file the service creates in `DATA_DIR`, and the plan check asked that a work order be given it. That cost two lead calls. Data-type files named near the pack's data-directory variable are now left out.
- **An unpassable test kept locked by a misread verdict (LF.405).** A test called `uid()` twice and compared the title with a freshly generated string. The QA lead explained exactly that, ending in the dispute prompt's own words, "its own steps never set up". "never set" matched the pattern for reasons about the product, so the test stayed locked. Reasons about the test's own steps now reopen it. After the rewind, QA repaired both tests and every criterion passed with the product unchanged.
- **Two release and loop details (LF.406).** `POST /notes -> 413` was failed at release for the 400 a correct product gives a bare probe; lines allowing only 409/413/415/429 are now listed as unchecked. And the corpus fix of LF.403 had copied files into the worker under the host's owner, which broke the next harvest. Ownership is now set, and the harness repaired it.
- **The kept-files contradiction, at its source (LF.407).** For the third run the specification put behaviour in files the pack keeps: graceful shutdown in `main.ts` here, `DATA_DIR` creation in `start.sh` before. The milestone review sent the sprint back for it, which cost a revision. The layout every stage reads already said these files are the harness's. It now also says they do what they do now and nothing more, and that anything else the product must do at start or shutdown goes in the product's own files.

### What can be improved

- **Fixing minor findings can break things.** Removing a duplicated `describe` block, a minor tidy-up the milestone review asked for, broke a unit test; the harness caught it and a fixer repaired it. Minor findings could go to a stage that must run the unit tests before answering, or be recorded rather than fixed in Fast delivery.
- **QA's "not automatable" labels keep appearing:** four runs now, always for criteria its suite does test. Worth a look at the field's description.

### How other harnesses handle this

- **Protected-file rules belong in the plan, not only at the tool.** Aider's read-only files and Claude Code's deny rules stop edits to protected files, but nothing there stops a planner assigning work to them. Spec-driven approaches such as GitHub's Spec Kit put fixed project conventions in a "constitution" the plan is written against. LF.407 puts the same constraint in front of the architect.
- **Judge outputs are parsed, not pattern-matched, where it matters.** Agent frameworks that route on a model's verdict, such as LangGraph's structured outputs or OpenAI's structured judging, ask for an explicit enumerated field ("test\_wrong" or "product\_wrong") rather than inferring it from prose. LF.405 patches the prose classifier. The sturdier fix is a required field in the dispute answer, which I've added to the backlog.

### Added value

- With LF.405 the harness no longer holds a correct product to an impossible test because of how the QA lead phrased its reason. LF.407 removes the most frequent cause of review send-backs in tonight's runs.

## Run run-59ade0e8 — notes-api-hono, Qwen3.6-35B-A3B MTP (2026-10-29 06:13 – 09:09 JST)

**Result:** hidden 9/9 in 136.4 active minutes over 221 calls, the longest run since the model change. The locked suite passed 17/17, and mutation score was 0.917. The run was `mixed_versions` with three rewinds, each to just before a wrong verdict that a fix shipped tonight now prevents. Without those three issues it would have run about as fast as tonight's best runs.

### What went wrong, and what was built

- **A comment read as code (LF.409).** A correct test used native `fetch` to send invalid JSON, under the comment "Playwright's request fixture does not read a `body:` option". The body-misuse check matched the comment's `body:`, and the locked suite was reopened for a test that passed. Comments are now skipped.
- **A plan with no API in it (LF.410).** The scope named `src/app.ts` ("complete Hono app with all six endpoints"), but no work order listed it. The plan check passed it as an existing file, though it was still the scaffold's stub. The first draft passed 2 of 18 criteria. A stub no longer counts as built, and after the rewind to the plan the draft passed 16 of 18.
- **A test no product could pass, called sound (LF.411).** A test created titles `list-a-${slug}`, filtered for `list-${slug}-` and expected two. Two fixers said so; the QA lead read it twice and said it was sound. A deterministic check now compares what a test sends with what it looks for. After the rewind QA repaired it, and the criteria passed with the product unchanged.
- **A false contract failure (LF.412).** `PUT /notes/999 -> 404` was answered 400 because the probe sends no body. A bodiless write refused for its body is now listed as unchecked.
- **Shutdown wiring placed in a kept file again.** The specification predated LF.408. The milestone review asked for a `setServer()` export "called by harness-managed main.ts", which nothing calls. That cost a revision plus a unit-test fix, about 35 minutes. LF.408 catches it at the architecture review from the next run on.

### What can be improved

- **Reasoning cost on this model.** The technical lead's replies reached 30–46k tokens (about 5 minutes each). In fix stages nearly every reply reasoned to the 12k cap and was salvaged, about 4 minutes per tool call. Two proposals for the owner: a reply cap for planning and review stages, and counting salvaged replies toward switching thinking off. Both change how much the model reasons, so they wait for approval.
- **The QA lead's judgement is the weakest link in the suite loop.** Tonight it misread one test twice, and an earlier run's verdict was misrouted (LF.405). Every deterministic check added (LF.395, 397, 409, 411) took a decision away from it. A structured verdict field (B28) and a second, independent reading for tests a fixer blames would make the dispute sturdier.

### How other harnesses handle this

- **Checks over judges for test validity.** Mutation testing frameworks (Stryker, PIT) and property-based testing rely on executable checks rather than reviewer judgement. SWE-bench-style harnesses validate a test by running it against a known-good and a known-bad version: fail-to-pass and pass-to-pass. The harness could apply the same idea to a disputed test: run it against the product, and against a version with the test's own claim reversed, and let the outcome decide rather than the QA lead.

### Added value

- Tonight's runs turned up a series of suite and plan failures, and each is now caught by a deterministic check. The model's reasoning cost, not the harness, is now the main lever on run time for this model.

## Run run-f9bbe2d6 — notes-api-hono, Qwen3.6-35B-A3B MTP (2026-10-29 09:21 – 10:23 JST)

**Result:** hidden 9/9 in 61.6 active minutes over 125 calls. The locked suite passed 12/12, and the new visible-versus-hidden gap was 0. Tool failures were 1.2%, the lowest of the night, and mutation score was 0.917. It was the first run on LF.408–412, and LF.413–427 were deployed into it in stages (`mixed_versions`).

### What was measured

- **The planning and review reply cap (LF.413, owner-approved) works as designed.** The largest planning or review reply was 20.8k tokens, the cap plus its salvage, and the mean was 3.9k. The worst earlier run had a 46k maximum, nine replies over 20k, and a 10.3k mean. The review outcomes looked normal: one architecture send-back, one suite send-back, then a lock.
- **The specification didn't place shutdown handling in a kept file**, so LF.408 had nothing to catch. One run is too few to credit LF.407 or LF.408.
- **LF.414 (thinking off after salvaged fix replies) wasn't exercised.** No defect-fix stage ran: the first draft passed every criterion.

### What went wrong, and what was built

- **A green sprint was sent back twice for a run that wasn't the suite (LF.426).** The milestone review accepted a sprint at 18 of 18. The gate read the execution ledger's last test run, a unit or partial run with 1 failure in 9, and sent it back for a revision, twice, costing about 10 minutes each. It had done the same in the two runs before. This contradicts the owner's LF.327 rule, so the gate now leaves a green locked suite alone when the failing run was another command.
- **Built during the run, in parallel:** the acceptance bundle (LF.417–419, 424–425), the fix-loop bundle from a worktree agent (LF.420–423: no re-measure of an unchanged product after a kept fix, revert notes replaced instead of piling up, closures guarded by the product's fingerprint, net gain weighed by what a fix broke), and the ops bundle from a second agent (LF.430–437: stale deploy hold, immediate recovery of a run whose worker was killed, bounded output capture, `init: true`, temp-directory clean-up, memory peaks per command). Each item has a test that fails on the old code, and the merged tree passes the full suite.

### What can be improved

- **Measuring the held-out family is now the priority.** Every result tonight is on notes-api-hono. The next run is tasks-api, the plan's item 23.
- **Doubtful items stay behind switches that are off,** under the owner's rule: targeted re-lock (LF.415) and plan items 9, 10 (part two), 11–20 and 24. Each turns on only after a measurement says so.

### How other harnesses handle this

- **Parallel agents in isolated worktrees, merged after review,** is how Claude Code's own subagent pattern and tools such as Conductor run separable work. This run's two worktree agents delivered 12 fixes in about 20 minutes each, with no merge conflicts, because each brief named the files it owned.

## Run run-627cbf21 — tasks-api (held-out family), Qwen3.6-35B-A3B MTP (2026-10-29 10:27 – 11:16 JST)

**Result:** hidden 10/10, with 5 of 7 quality edges held, in 48.3 active minutes over 117 calls, on a single harness version (9e18db6a). The locked suite passed 29/29, the visible-versus-hidden gap was 0, and tool failures were 2.4%. This is plan item 23, the first measurement of tonight's fixes on a brief they weren't tuned on: Python on FastAPI, with sign-up, sign-in, tokens and per-user items.

### What was measured

- **The fastest tasks-api run in the ledger.** The 15 earlier Qwen3.6 tasks-api runs took 59 to 237 active minutes, with a median of about 120, and one scored 0. This one took 48. The first draft did not start, because an undeclared `passlib` import broke it. Two fix rounds got it started, and a rewrite then made 16 criteria pass at once; dispatch closed them as already passing, without a fixer.
- **Nothing from tonight's Hono-specific pack work applied**, so the gain is from the general fixes: suite checks, repair and plan logic, the reasoning caps, and the fix-loop and ops bundles.

### What can be improved

- **No unit tests shipped.** The unit command ran none and was counted as a pass. The release flags it, but nothing during the run asked for unit tests while the acceptance suite was green. A product without unit tests is fragile for whoever maintains it.
- **A contract line with no criterion id is unread:** `GET /health -> 200`. The contract reader could accept it as a check without a criterion.
- **A model file nothing imports** (`models.py`, 42 lines) shipped as dead code. The release names it; a clean-up step could remove it.
- **Two quality edges failed.** Which brief edges the product misses is the next thing to inspect on this family.

### How other harnesses handle this

- **Benchmark integrity by held-out sets.** SWE-bench Verified and Terminal-Bench keep evaluation sets separate from development, and SpecBench reports the gap between visible and hidden scores. This harness now reports that gap with every score and has run its first held-out family. One run is too few: the plan calls for at least two per family before a delta is trusted.

## Run run-943927b0 — notes-api-hono, Qwen3.6-35B-A3B MTP (2026-10-29 11:29 – 12:18 JST)

**Result:** hidden 9/9 in 40.7 active minutes over 71 calls, the fewest calls of any run tonight. The locked suite passed 17/17 and the visible-versus-hidden gap was 0, but mutation fell to 0.667 against a recent mean of 0.834. It was the first run on the consolidated switches (8d793eee). It was rewound once, past a false alarm from one of my own checks (LF.441), and is `mixed_versions`.

### What was measured

- **LF.408 caught the kept-file misplacement before any code existed.** The architecture review got the finding, and the revised specification moved shutdown handling into `src/app.ts`. Three earlier runs lost a revision to this; this one lost none.
- **LF.410 sent the plan back for the unassigned stub `app.ts`.** After it, the first draft passed every criterion. In run-59ade0e8 the same gap had left the first draft at 2 of 18.
- **The first draft was fully green, 18 of 18, once the false reopen was undone.**

### What went wrong, and what was built

- **A false positive in LF.411, this morning's own check.** It flagged a right test as looking for a title it never sent; the test sent it through its helper `createNote(request, 'QA-crud-title', ...)`. It also reached the release notes as a problem the suite was "locked with". LF.441 counts values passed to any helper given the fixture. Run-59ade0e8's genuinely impossible test is still caught.
- **A contract line with no criterion id** (`GET /health -> 200`, seen on tasks-api) is now read (LF.440).
- **A cross-file finding about an installed `vitest` was reverted twice:** removing it broke nine unit tests, and the green sprint then settled with it as a known issue (LF.402). The unit tests and the package choice disagree; the testing role should be told which runner the pack runs.

### What can be improved

- **Every new static check should be run against all the locked suites before it ships.** LF.411 was checked against 40 earlier suites, none of which used a helper this way. A larger standing corpus of real suites, like the reader corpus for contract lines, would catch a false positive before a live run does.
- **The mutation score is noisy run to run:** 0.583 to 0.917 tonight. Judging an experiment by it needs several runs.

## Run run-dba1ccf8 — notes-api-hono, Qwen3.6-35B-A3B MTP (2026-10-29 12:26 – 13:10 JST)

**Result:** hidden 9/9 in 43.7 active minutes over 108 calls, on a single harness version (fca7568b). The locked suite passed 11/11 and the visible-versus-hidden gap was 0. Mutation score was **1.0**: every deliberate change was caught. The specification chose SQLite storage this time, so the run tested a design the harness doesn't usually see. LF.410 again sent the plan back for the unassigned stub `app.ts`. `TARGETED_SUITE_REPAIR` was on, but nothing reopened the suite, so it had nothing to act on.

### What went wrong, and what was built

- **Unit tests for a runner the pack doesn't use (LF.443).** The tests called `describe` and `it` as globals, as Vitest allows; the pack runs `node:test`, which has none, so they failed with "describe is not defined". Both fixers rewrote `package.json` and added a Vitest config, but the test command is the pack's and is put back, so neither fix could work, and the tests shipped failing. The previous run showed the same mismatch. Every pack that runs `node --test` now attaches the cause to such a defect: import from `node:test` and `node:assert`; changing the manifest can't fix it.

### What can be improved

- **Fixers aim at files the harness restores.** Fixers keep editing kept files (`package.json` scripts, `main.ts`) and the harness keeps putting them back. A fixer could be told up front, in its defect, which of the files it might reach for are kept. LF.394, LF.407 and LF.408 cover the reviews and the architect; the fixers are the gap left.
- **The re-lock gate and the structured dispute verdict need events to measure.** Two runs have passed without a post-lock repair. Measuring these experiments needs runs where tests are disputed or repaired, which the held-out family and larger briefs produce more often.

### Added value

- Four notes-api-hono runs in a row finished in 41–62 active minutes at full hidden score, with LF.408, LF.410 and LF.426 each catching a problem that had cost earlier runs a revision. This brief now completes reliably and quickly; the remaining measurement value is in the held-out family and larger briefs.

## run-b115ca5c — tasks-api (held-out, second run), failed 15:30 JST 2026-10-29, hidden 1/10

**What happened.** Sprint 1 reached 17 of 48 locked tests. Sprint 2 held at a best attempt of 42 while later attempts measured 30–37. The sprint was replanned until the limit, and the run failed. The final score re-measured the best attempt at 29/48 visible and 1/10 hidden: every hidden test that signs in got 401.

**Root cause (reproduced by hand).** The product opened its SQLite session in a FastAPI `yield` dependency and committed after the `yield`. Since FastAPI 0.118, that code runs *after the response is sent*. A sign-up answered 201, and a sign-in sent straight after it found no account: 401 at once, 200 after a 1-second wait. The product's unit tests use `TestClient`, which waits for the teardown, so they passed. The fixers could not reproduce the failure, and the suite's counts swung from one measurement to the next on near-identical code. A required `Header()` also answered a missing credential with 422 instead of 401.

**Fix (LF.447).** The FastAPI seed guidance now says that teardown runs after the reply. It tells the agent to commit in the route, or to use `Depends(..., scope="function")`. It notes that `TestClient` hides the race, and that a header the route checks itself is declared `Header(None)`. The guidance is FastAPI-only, so it lives in `seed.py`.

**Features to improve.**

- *Timing hint:* when one product's suite gives different results on whole-suite runs, tell the fixer the failure is timing-dependent (the product answers before its write is visible). Do not send it to rewrite logic.
- *Real-service unit check:* the harness could run one unit-level round-trip against the started service, not the in-process client.

**How other harnesses do it.** SWE-agent-style loops re-run a failing test several times before they assign blame. Flaky-test tooling (pytest-rerunfailures, Bazel's flaky attribute) labels a test that passes and fails on the same commit as flaky rather than broken. Our `unstable.py` covers only "fails in the suite, passes alone".

**Added value.** This is the first held-out failure since the Qwen3.6 switch. It shows a failure class (async teardown ordering) that unit tests cannot see, and that more fixer attempts cannot cure. The next tasks-api run measures LF.447 directly.

## run-c99de99f — tasks-api (held-out, third run), completed 18:46 JST 2026-10-29, hidden 10/10

**Result.** Hidden 10/10, quality 7/7, locked suite 23/0, visible and hidden agree. 83.2 active minutes, 182 model calls, 109 tool calls, 3.7% tool failures, mutation 0.5. It ran on harness 7885d3c, with LF.447 live and no mixed versions.

**What happened.** The first draft started, unlike the failed run's. Sign-in failed at first for a new reason: the product re-hashed the password with a fresh salt and compared hashes. A fixer cured it in round 2. LF.447's guidance reached every stage, and this product committed inside each database function, so the race behind the previous failure never appeared. The draft still declared the credential header required (422 instead of 401) despite the guidance, and fixers corrected it.

**Where time went.** Sprint 1 took three attempts. In attempts 2 and 3, eight fixes in a row were reverted. Each broke the same 10 passing tests and made none pass. The project's own unit tests disagreed about row access: eight read rows by name, and one asserted that rows are read by position "since it does not set row\_factory". The harness then escalated rather than replan a fourth time, and sprint 2 went green on its first attempt. The 10 reverts against a 5-run mean of 4 are flagged as a KPI regression.

**Features to improve.**

- *Contradictory unit tests:* when every fix for one defect breaks the same set of the project's own unit tests and gains nothing, the defect is a contradiction between tests, not a product fault. Route it to whoever owns those tests with both tests side by side. A fifth fixer on the product cannot win.
- *Same-revert memory:* after two identical reverts (same broken set, zero gain), stop sending fixers at that defect within the attempt.
- *Unused file:* `models.py` (36 lines) was never imported. The release saw it; nothing before release did.

**How other harnesses handle it.** Aider and SWE-agent treat the repository's tests as ground truth and have no notion of contradictory tests; they simply loop. Agentless-style pipelines generate several candidate patches and pick by test majority, which also fails when the tests conflict. Tools that grade test quality (mutation tools, test-impact analysis) flag tests that constrain implementation details, such as asserting positional access, as brittle rather than behavioural. That is the signal we would add.

**Added value.** The held-out family is back to 10/10 with a clean visible/hidden match. The remaining cost is the 3-attempt sprint 1, and the contradictory-test detector above targets it directly.

## run-d96298ae — notes-api-hono (Fast), completed 20:20 JST 2026-10-29, hidden 9/9

**Result.** Hidden 9/9, locked 11/0, no visible/hidden gap. 81.0 active minutes, 130 model calls, 91 tool calls, 2.2% tool failures. Harness 7885d3c, not mixed. The mutation score of 0.5 was flagged as a regression against a 5-run mean of 0.884.

**Where time went.** The product was green after one drafting round. About 37 of the 81 minutes went to four mutation defects. One was judged equivalent. Two stayed uncured after two fix stages each and closed as completion gaps. The fourth was cured by a rewrite of the route unit tests. The two the release still lists were `||` to `&&` changes in validation guards.

**Measured before proposing a cap.** Across the last 14 runs, second- and third-round fixes did cure mutation defects three times (d907728e, 32568792, 92d13786). A one-try cap would lose real wins, so no change.

**Features to improve.**

- *Mutation fixes by example:* a fixer told only "no test notices `||` made `&&` on line 86" twice wrote tests the mutant still passed. The harness could run the mutant and hand the fixer one concrete input whose outcome differs between original and mutant (it already has both). The fixer then writes the test for that input. This turns a search into a transcription.
- *Contract lines with a parameter:* 5 contract lines with `{id}` were unchecked at release again. Probing a parameter route after creating one (LF.340) should cover these. Check why it did not fire on this stack.

**How other harnesses handle it.** Mutation-guided test generation (Meta's ACH, 2025; mutation-guided LLM test-generation research) gives the model the mutant diff and asks for a test that kills it. ACH also checks the generated test against both versions before accepting it. That is the "by example" step above, and it is the main difference from what we do.

**Added value.** Five notes-api-hono runs in a row are now at 9/9. The remaining lever on this family is time spent on mutants, not correctness.

## run-186114da — notes-api-hono (Fast), completed 22:53 JST 2026-10-29, hidden 9/9

**Result.** Hidden 9/9, locked 12/0, no visible/hidden gap. 45.6 active minutes, 104 model calls, 57 tool calls, 3.5% tool failures. Harness 7885d3c, not mixed. The previous notes-api-hono run took 81 minutes; this one is back in the usual 41–62 band.

**What happened.** The first design was sent back once and the revision passed. QA's suite passed review on the first try. The first draft left six acceptance defects. Two had a real cause: a handler variable that shadowed the parsed body, and a title validator that returns an object but was tested as a boolean. Two were closed because they passed by the time a fixer was due. One fix broke 3 passing tests and was reverted. A mutation defect was cured by a unit test.

**Flags.** `fixes_reverted` 1 against a mean of 0.4 and `identical_call_rate` 0.053 against 0.025. Both are single counts on a short run; neither points at a harness fault.

**Features to improve.**

- *Parameter routes at release:* four contract lines (`PUT`, `GET`, `DELETE` on `/notes/{id}`) went unchecked at release for the second run in a row. The release probe (LF.340) covers a parameter route only when its line allows a 4xx, and probes it with a record that does not exist. A line that allows only 200 or 204 is never probed. Create a record through the contract's own write line first, then probe the parameter route with its id. This is a verification gain with no behaviour change to the product.
- *Shell-shaped commands:* a fixer sent `cd x && node --version` as one command. The refusal is correct, but it costs a call. The refusal text could name the working-directory argument, as it does elsewhere.

**How other harnesses handle it.** Schemathesis and Dredd, which test a service against its OpenAPI description, chain calls by feeding a created resource's id into later requests (Schemathesis calls this stateful testing, built on OpenAPI links). That is the create-then-probe step above, and they treat unlinked parameter routes as a coverage gap rather than silently skipping them.

**Added value.** Six notes-api-hono runs in a row at 9/9, with times between 41 and 62 minutes except the one with four mutation defects. The remaining release gap on this family is stateful route coverage.

## run-ca605d5d — tasks-api (held-out, fourth run), completed 01:35 JST 2026-10-30, hidden 10/10

**Result.** Hidden 10/10, quality 7/7, locked 25 passed and 1 failed (AC-17 shipped deferred). Visible 0.962 against hidden 1.0. 129 active minutes, 304 model calls, 252 tool calls, mixed\_versions (one rewind to take LF.448). It is slower than the 83-minute run before it.

**What happened.** Sprint 1 first hit a defect no fixer could cure. QA's locked tests signed in as users they never created, so a correct product got 401. The dispute named two of the nine such tests; the reclassification cap (2) was then spent, and the sprint was replanned. QA had been told to change only the tests named, so it fixed two and left seven it could see. LF.448 lets QA repair tests with the same fault in one pass. After the rewind, sprint 1 passed with no fix round. Sprint 2 was replanned three times over one test: a Python test that read `start.sh` and asserted it contained `DATA_DIR`. The kept-file check knew only JavaScript suites. LF.449 extends it to Python.

**Features to improve.**

- *Sibling faults:* when a test round names a fault, the harness could find the other tests failing with the same message and hand QA the whole set. That keeps the cheap lock available; today a sibling repair forces a full suite review, about 15 minutes.
- *Stale defects at a replan:* after a dispute repairs tests, the replan briefing still carries the failed attempt's defects about those tests, and the technical lead reasoned about a sign-in 401 the product did not have. Drop those defects from the briefing.
- *Language coverage of static checks:* two harness checks in a row knew only the JavaScript suites (LF.446, LF.449). A test that lists which checks run on which suite language would show the next gap before a run does.

**How other harnesses handle it.** Test-generation systems that repair their own tests (for example the self-refinement loops in CodeT and AlphaCodium) re-run the whole generated suite after any edit rather than a named subset, and fix by failure class. That is the sibling idea above, but they pay the full re-run each time. We can keep the cheap lock by grouping failures first.

**Added value.** The held-out family is at 10/10 in three of the last four runs. The cost is in the time spent on QA's own tests (83 to 129 minutes), not in the product.

## run-d2e68f5b — notes-api-hono (Fast), completed 16:45 JST 2026-10-30, hidden 9/9, on the new build model

**Result.** Hidden 9/9, locked 15/0, no visible/hidden gap. 285 active minutes, 390 model calls, 465 tool calls. Build model `qwen3.8-flash-next-coder-iq1_m` (a 1-bit quant), changed by the owner before this run. Three harness versions (mixed\_versions, two rewinds). The KPI flags: tool failure rate 11.5% against a 5-run mean of 2.9%, and prefill/decode ratio 6.3 against 3.9.

**What happened.** The product was built and green after the second build. About four hours went on QA's suite. Three harness bugs kept it going: (1) QA rounds are stages with a round number, so the delete and move tools refused QA's own scratch probe files as another stage's tests; (2) the Hono start file called the app factory with no argument while the design had given it a `dataDir`, so the service crashed at start and the suite locked with 0 tests; (3) the check for tests that read what the test process does not have read a comment as code, so QA's explanation of the flaw was sent back as the flaw. LF.450-452 fixed these. LF.453 fixes a fourth, found at scoring: AC-14 and AC-15 stayed deferred after tests covered them, and the release listed them as unproven.

**The tool failure rate.** 11.5% is a model effect plus the above. Most were edit anchors that did not match the text exactly, and QA's repeated delete attempts. The harness's refusals worked as designed; the cost was calls.

**Features to improve.**

- *A check's own false positives:* two of the four bugs were a static check reading comments or the wrong stage. The replay of stored real suites caught one existing false positive (suite-14) the moment it was run; it should run on every new check. It already does; the gap is that nothing replays the checks on a suite QA has just written, before it is sent back.
- *Interface of the design against the pack:* the harness found the `createApp(dataDir)` mismatch only at the first test round (a pack contract defect). The architecture review could check the design's factory signature against the pack's guide.
- *Scratch probes:* a probe that carries no criterion could be removed by the harness at the lock instead of asking QA to delete it.

**How other harnesses handle it.** Most agent harnesses (SWE-agent style) let one agent own its working files for the whole task; they have no notion of stages owning files, so they do not hit rules like (1). Pipeline harnesses that do split roles (for example MetaGPT) give each role a fixed output folder and let the role rewrite its own folder freely, which is the same rule we now apply to QA rounds.

**Added value.** The first run on the new model reached 9/9 hidden. The remaining cost is calls spent on QA's suite, and fewer false positives in the checks cut it directly.

## run-817b3ce3 — tasks-api (held-out, fifth run), completed 20:43 JST 2026-10-30, hidden 10/10

**Result.** Hidden 10/10, quality 7/7, locked 22/0, no visible/hidden gap. 116.2 active minutes, 296 model calls, 231 tool calls, 7.9% tool failures. Qwen3.6 again (the owner reloaded it after a day on a 1-bit model). Three harness versions (mixed\_versions: one rewind, one resume). Mutation score 0.25 against a 5-run mean of 0.708 is flagged.

**What happened.** Two earlier starts failed at the first stage on HTTP 500/502: the reloaded model server answered small requests but not prompts of about 4,500 tokens. After the owner fixed it, the run went through. The first locked suite had tests that signed in as users nothing created; the test round raised them as product defects, and a fix round and a dispute were spent. LF.455 now catches that before the lock. Sprint 1 then failed three attempts on unit tests that disagreed with the code about a function's parameters. Each fix changed the function to suit some tests and broke others, and was reverted. LF.457 now tells the fixer both sides of the disagreement and which to change. After it, sprint 1 completed and sprint 2 went through reviews on the first pass.

**Features to improve.**

- *Tests and code written in parallel:* the unit tests (testing work order) and the code (backend work order) are written in the same milestone with no shared signature table, and disagree. This is the third run it has cost a sprint. The spec already has function contracts; the testing work order could be handed the exact signatures, and a check could compare test calls to definitions before the first test round.
- *Mutation score:* 0.25 is the lowest on the held-out family. Four of its six mutants were `or`/`and` flips in validation guards. The harness judged some equivalent and the rest left open after two tries. The by-example idea from run-d96298ae (hand the fixer an input where original and mutant differ) applies directly.
- *Model readiness:* the plain ready check passed while real calls failed. `loop.sh ready deep` (LF.454) now sends a 13,000-token request.

**How other harnesses handle it.** Design-by-contract tools (Pact-style consumer-driven contract tests, OpenAPI-first generators) derive both sides from one signature table, so a test and its code cannot disagree on parameters. Our pipeline generates both from prose; a signature table extracted from the spec is the nearest equivalent.

**Added value.** Five tasks-api runs now: 1/10 (failed), 10/10, 10/10, 10/10, 10/10. The four sprint-killing patterns found since the failed run are fixed, and this run still spent four attempts on sprint 1 before LF.457 settled it, so the next run is the real test of the fixes.

## run-abb23c25 — notes-api-hono (Fast), completed 22:16 JST 2026-10-30, hidden 9/9

**Result.** Hidden 9/9, locked 13/0, no visible/hidden gap. 89.4 active minutes, 159 model calls, 115 tool calls, 7.0% tool failures. Qwen3.6. Three harness versions (mixed\_versions: two resumes). Mutation score 0.667. KPI flags: redundant reads 18% against a mean of 9%, model errors 2, fixes reverted 5 against 0.6, defects left open 5 against 1.2.

**What happened.** QA wrote the suite cleanly (43 tool calls, no failures, locked on the review's third round) with none of the scratch-file or start-file trouble of the previous notes-api-hono run, so LF.450-453 held. The first draft failed eight acceptance criteria; one fix cured six at once and two later fixes that broke ten passing tests were reverted. The unit tests then blocked sprint 1: every test file imported the product with `../../src/` from `test/`, one directory too far, Node answered ERR\_MODULE\_NOT\_FOUND with a path outside the project, and the fixers read it as a missing file and edited the manifest and the product. LF.470 added the cause to the Node packs' known-error table; the next fix round used it exactly (`../src/`) and sprint 1 completed.

**Release gaps.** (1) A blocking milestone finding was recorded as a risk, not fixed: the DELETE handler still validated the id with `parseInt` after the GET and PUT handlers had been corrected. A fix scoped to the handlers the defect named left the third with the same fault. (2) Four contract lines (`GET /notes/{id} -> 200 | 404`, `PUT ... -> 200 | 404`) went unchecked because a pipe between statuses followed none of the contract's forms. LF.471 reads it. (3) Two mutants survived.

**Features to improve.**

- *Sibling handlers:* when a fixer corrects a fault in one handler (an id validation, a status code), the harness could list the other handlers that share the pattern and put them in the same fix. The sibling-fault idea of LF.448 for tests applies to product code too.
- *Known-error causes from the first draft:* the import-depth fault is checkable before any run: resolve each relative import in the unit tests against the file tree. A static check at the first unit-test write costs nothing and removes a sprint attempt.
- *Contract grammar:* the contract's forms keep growing by one separator per run (`or`, `/`, `,` and now `|`). A permissive parse for the status list is cheaper than a regex per spelling.

**How other harnesses handle it.** SWE-agent-style harnesses run a language-server or compiler check after every edit, which would flag a relative import that resolves to no file at write time. Our pipeline has the language service for the product but reported this one only as a failing unit test.

**Added value.** The first notes-api-hono run after the QA fixes had a clean QA stage. The cost moved to the unit tests and the mutation fixes, which Phase 2's switches (tests-only writes, kept candidates, the in-stage mutant check) address; they are off and untested so far.

## First two runs at once on two Qwen servers — run-c82c85d9 (tasks-api) and run-21519414 (notes-api-hono), completed 2026-10-31

**Results.** run-c82c85d9 (tasks-api, pinned to :8888 from 00:47 JST): hidden 10/10, quality 7/7, locked 23/0, 318.8 active minutes (342 wall), 726 calls, mutation 0.75. run-21519414 (notes-api-hono, pinned to :1234 from 00:47 JST, its first run on that server): hidden 9/9, locked 10/0, 92.9 active minutes, 184 calls, mutation 0.25. Both full marks; the harness was 14129b8 then 77638e3 (the pin), Phase 2 experiments off.

**Throughput.** The pin worked as designed: both runs advanced at the same time, each on its own GPU, with no cross-slowdown visible in call counts. The tasks-api run is the slow one: five hours, almost all of it in sprint 1, which took four attempts. The unit tests and the code disagreed about the database helper (written as a framework dependency, tested as a context manager); each fix satisfied one side and broke the other, and was reverted. LF.457 and LF.473 hints did not end the standoff by themselves. The first draft also used Pydantic 1 forms on Pydantic 2 (LF.472). The notes-api-hono run was quick (93 minutes) but shipped two failing unit tests and two surviving mutants, because the sprint had no fix round to spare.

**Release gaps worth acting on.** (1) tasks-api shipped three criteria deferred for lack of a test carrying their id (AC-1, AC-17, AC-21): QA left them unnamed and the review accepted a deferral instead of sending the names back. (2) A contract line written `AC-health GET /health -> 200` was unreadable: a non-numeric criterion id. (3) A milestone finding that a unit test checks the wrong database file was recorded as a risk, not fixed.

**Features to improve.**

- *Settle a standoff by the callers:* when two successive reverts break the same set of tests and neither side wins, the harness should stop rewriting the product and send the defect to the tests' owner with both callers' evidence. The hints (LF.457, LF.473) tell the fixer which side to change but cannot stop a fixer that edits the product anyway; a `TESTS_ONLY_WRITES` pass (built, off) forces it.
- *Deferral is a last resort:* a criterion deferred only because no test name carries its id should go back to QA as a naming fix, not ship deferred.
- *Criterion ids:* accept `AC-` followed by letters in a contract line instead of setting the line aside.

**How other harnesses handle it.** Consumer-driven contract testing (Pact) fixes the signature once and generates both sides' tests from it, so a test and its code cannot disagree; the closest we have is the spec's function contracts, which the testing work order does not yet receive as a table.

**Added value.** The two-server setup roughly doubles the number of measuring runs per day, which is what the Phase 2 switches now need: the next pair runs the fix-loop group on, against these two runs as the off baseline.

## run-ec3e81ab (tasks-api, :8888, fix-loop group on), completed 2026-11-01 03:44 JST

**Result.** Hidden 10/10, quality 7/7, locked suite 33 passed and 0 failed, visible-hidden gap 0, mutation 6/6 (5 caught by a specific test). No false acceptance. The off-arm tasks-api run (run-c82c85d9) also scored 10/10 but with mutation 0.75 and a five-hour sprint 1.

**What this run says about the fix-loop group: almost nothing.** The defect ledger holds one defect: a regression where an earlier change made `/health` return `{}`, reverted by the first fixer. With one defect the group had nothing much to act on, so the better mutation score cannot be credited to it. The run is also marked by two interruptions: a model outage and a deploy at 03:39 JST that hit it live, because the pause command failed for want of credentials. Orphan recovery resumed it within seconds. The 16 model errors flagged against a 5-run mean of 4.4 are probably the outage; that was not checked error by error.

**What can improve.**

- **The release knew of 8 gaps and still shipped them.** Five are criteria whose tests QA left open at the lock (AC-8, 9, 10, 18, 21). The product passed the hidden tests anyway, so these were not costly here, but the suite proved less than its 33 passes suggest.
- **14 of the contract lines were not checked at release,** mostly routes with a parameter. `CONTRACT_PROBE_WITH_A_RECORD` (LF.488) targets exactly this and is built but off. This run is its case for measurement.
- **An over-strict locked test was found and kept.** The AC-18 gap says the test requires `{"status": "ok"}` where the spec allows an empty body; the fixer then reverted correct-by-spec code to satisfy the test. No harm in the score, but this is the same test-versus-spec standoff seen before, settled by the test's authority rather than the spec's.
- **Two design-review findings were left open by escalation** (how `DATA_DIR` is created, the secret key's name and path). A contradiction left in the specification is a likely source of later rework.

**How other harnesses handle this.** The sources found are mostly practitioner write-ups, not measured studies, and no shared benchmark for contract coverage turned up.

- **Contract tools in the loop:** one Codex CLI write-up runs Specmatic contract and resiliency tests after each endpoint against an OpenAPI spec, and neither may fail before moving on. We probe a hand-written contract later and less often; an executable spec would probe more lines, at the cost of requiring a spec format.
- **Traceability tables:** a playbook maps every criterion to its tests and every test to a spec item. Our locked suite does criterion mapping; `CONTRACT_LINE_COVERAGE` (LF.484) adds the route side, as a lenient text search only.
- **An evaluator prompted to find problems:** EasyHarness separates generator from evaluator. Our reviews already do this.
- **Hidden checks:** one write-up reports that agents shown the tests scored well on them but shipped broken work, while those with a hidden oracle stayed honest. It reports the experiment secondhand. Our benchmark's hidden tests fit this, but they exist only in benchmarks; a customer run has no such check.

**Adding value.**

- Show the owner, on the run page, which criteria were proved and which shipped with a known gap. A green run with 8 known gaps should not look the same as one with none.
- Offer a held-back portion of the customer's own acceptance tests, run only at the release gate, as a paid assurance feature. This is an idea, not yet tested on any run.

**Next measurement.** Turn on `CONTRACT_PROBE_WITH_A_RECORD` and `CONTRACT_PROBE_AT_LOCK` as one arm once the fix-loop group has enough runs with real defects to read.

Sources: [EasyHarness](https://github.com/leeif/easyharness), [Harness Engineering Playbook: the verification chain](https://agents-zone.github.io/harness-engineering-playbook/en/chapters/03c-practice.html), [Contract-driven API development with Codex CLI and Specmatic](https://codex.danielvaughan.com/2026/04/23/contract-driven-api-development-codex-cli-specmatic-mcp/), [The Check Becomes the Spec](https://blakecrosley.com/blog/check-becomes-the-spec).

## run-416d1bbb (notes-api-hono, :1234, fix-loop group on), completed 2026-11-01 06:39 JST

**Result.** Hidden 9/9, no false acceptance, locked suite 17 passed and 0 failed, visible-hidden gap 0. Mutation 7 of 12 caught by the locked suite (0.583), 10 of 12 with the unit tests (0.833). About 3.5 hours wall time, 197 tool calls, 9.6% failed. Against the prior 5-run mean, tool failures (0.096 against 0.031), identical calls and lost replies were all flagged as regressions. Many of the failures seen in audits were refused edits and commands, but they were not counted by cause.

**The run scored full marks after losing about two hours to a wrong verdict.** The product read its data folder as a file and called `process.exit(1)` on its first write under the restart test. The harness's test helper threw the service's output away, so the test saw only "fetch failed". The dispute ruled that a fair test could not pass for any product and sent it to QA, who may not change the product. QA said in its own words that this was "likely a product bug", but had no way to hand that back. It worked for about 90 minutes before re-locking. Once a fixer received the failure, and after a deploy gave the run the fatal error in plain text, the bug was fixed in about 20 minutes.

**What can improve.**

- **Evidence reached the stage that needed it too late.** Now fixed: LF.491 keeps the service's output and reports a death, and a disputed test whose service died stays locked; LF.493 carries the report to the fixer. Seen working on this run from 06:14 JST.
- **QA has no way to say the product is at fault.** `QA_SAYS_THE_PRODUCT_IS_AT_FAULT` (LF.494) is built and off, tested with mocked agents only. It needs measuring.
- **False "cannot pass" findings keep costing QA time.** Three tonight: LF.490 (a helper's answer read as a fixture response), LF.492 (a content type read on another answer in a test that also deletes), and the wrong dispute. All are text-pattern or prose judgements. `SPEC_DRY_RUN` targets this class but stays off until it has a sandbox.
- **The mutation check is costly when the suite has no answer.** Three fix rounds went on it, two of them left open because the unit tests still pass with the change. The release still lists surviving mutants. Whether those stages earned their time is not yet measured.
- **The suite dropped a list check in repair** (`notes.length >= 3`), and AC-15 now only confirms the start file exists and is executable, plus health. The hidden tests passed, but the final suite proves less than the first version asked for, and the release lists this as open.
- **The readiness check probes only the server in the global setting,** so a busy :1234 reports not ready even when the run would start on :8888. It has delayed nothing yet.
- **One false merge explained an older false acceptance.** LF.495: a folder name in a path merged a criterion's own failure into a unit-test defect on run-dfcaf697 (8/9). That is now fixed, and its review is covered here rather than separately.

**What this run says about the fix-loop group.** More than run-ec3e81ab: 9 test rounds and 11 fix stages, and reverts caught fixes that broke tests. But this run's time went on the dispute, so one run can't separate the group's effect. Keep measuring.

**How other harnesses handle this.** Sources are vendor documentation and blog posts, with no shared standard. They agree on the principle we had missed: server logs from the failing window are what prove a product bug.

- BrowserStack's failure-analysis agent separates product bugs from environment and script issues by correlating logs, screenshots and metadata, and notes that it cannot reach server-side logs held outside the product. Those must be captured and supplied.
- A published triage write-up gives the same case: a failure looks like a test problem until the server log proves otherwise, and warns of answers that depend on logs nobody kept.
- Testkube's triage agent splits infrastructure failures, such as out-of-memory kills and runner crashes, from real test failures.
- One team's triage agent writes a rationale with each verdict. Our dispute gives one, but until tonight it could not be checked against evidence.

**Adding value.**

- A plain product feature follows: on the run page, show each failing test with its service's output beside it. This is the evidence that took the harness two hours to see, and an owner would use it the same way.
- Report how much of a run went on repairing tests against building product. Tonight that figure would have flagged the problem hours sooner, on both runs.

Sources: [BrowserStack test failure analysis](https://www.browserstack.com/docs/test-reporting-and-analytics/agents/test-failure-analysis?fw-lang=nodejs), [Why did the test fail? A triage rulebook](https://hackernoon.com/why-did-the-test-fail-a-triage-rulebook-tested-on-two-llms), [Testkube infrastructure triage agent](https://docs.testkube.io/articles/infrastructure-triage-agent).

## run-0349d8e9 (notes-api-hono, :8888, fix-loop group on), completed 2026-11-01 07:52 JST

**Result.** Hidden 9/9, no false acceptance, locked suite 22 passed and 0 failed, visible-hidden gap 0. Mutation 8 of 12 (0.667), 10 of 12 with unit tests. About 4 hours, 388 tool calls, 6.4% failed: 12 test rounds, 18 fix stages, 3 re-plans, 8 fixes reverted against a recent mean of 2.4, and 19 defects left open against 9. One unit test ships failing, and the release says so. Model errors were 7 against a mean of 0; the deploys at 05:14, 06:00 and 07:15 JST may explain them, but that was not checked.

**A full score in about 2.5 times the time of the earlier run of this benchmark** (run-21519414: about 93 active minutes). Three things consumed the time:

- **False findings before any product existed.** LF.490 and LF.492 reopened a locked suite over tests that were right. Both are fixed.
- **A test of a protected file.** The AC-15 test read `start.sh`, which the harness writes and keeps, so no fixer could satisfy it. LF.496 now finds this before the lock.
- **A contradiction in the specification, flagged and then built on.** Design review left open, as a major finding, that the `/health` criterion asked for an empty body while the API contract said otherwise. The unit test took one side and the locked test the other, and every fix for one was reverted for breaking the other. At least six fixes went this way. The run ended only because every locked test passed and the remaining unit test was escalated and accepted.

**What can improve.**

- **An open contradiction should not reach the build.** This is the highest-value item from tonight. Today the architect's review can find one and the run records it as a known risk after the revision limit. Two of tonight's runs carried such findings, and this one cost hours. A contradiction between two parts of the specification is a question with a small answer; a stage that settles it before QA and the drafters write opposing tests would have removed the standoff at its source. Not built.
- **The standoff itself:** `UNIT_TESTS_YIELD_TO_THE_LOCKED_SUITE` (LF.497) is built and off. This run is its case for measurement. It treats the symptom only.
- **The fix-loop group:** two heavy runs now, both scoring full marks, both slow, for causes outside the group. Its effect still can't be read from these runs.
- **Time to first real fix.** QA repair ran for about 90 minutes before any fixer saw this product. The first fixer then took the suite from 3 passing to 20 of 22 in about 10 minutes. A report of time spent repairing tests against time building product would have shown this early.
- **Readers should not take a release's green as cleanly earned.** It shipped with 7 known gaps, a failing unit test and no review of the code (fast delivery). The hidden tests are what confirmed it, and customer runs do not have those.

**How other harnesses handle this.** From secondary sources, not official documentation; check those before relying on the details.

- GitHub Spec Kit is described as having an analysis step that scans the specification, plan and work list for inconsistencies, gaps and contradictions as a gate before implementation, and a clarify step for ambiguity, which sources recommend running before planning because it is cheapest to fix there. One comparison notes these gates are optional and pay off mainly on complex features.
- AWS Kiro is claimed by one article to use formal logic and SMT solvers to catch contradictions in requirements before code is generated. That is a single source and is unconfirmed.

Our architecture review already finds these contradictions. The gap is what happens next: we record and carry on, where these tools describe a gate.

**Adding value.**

- Turn a spec contradiction into one plain question for the customer at the review stage, with the harness's suggested answer, and proceed on the suggestion after a timeout. It uses the existing gate and approval pieces, removes hours of machine time, and shows the customer the decision that was made.
- Report the cost of a run by cause: spec problems, test problems and product problems. That gives an owner a reason to write a better brief.

Sources: [Spec-driven development tools compared](https://levelop.dev/blog/spec-driven-development-tools-compared), [Spec Kit review](https://chatforest.com/reviews/github-spec-kit-specify-cli-spec-driven-development-ai-coding-review/), [How Kiro and AI agents build from specs](https://www.morphllm.com/spec-driven-development).

## run-27b8cc24 (tasks-api, :1234, fix-loop group on), completed 2026-11-01 07:57 JST

**Result.** Hidden 10/10, quality 6/7, no false acceptance, locked suite 29 passed and 0 failed, visible-hidden gap 0. Mutation 7 of 8, all with a specific test; 8 of 8 with unit tests. About 70 minutes from start to release, the cleanest run of the night: 1 test round, 2 fix stages, 2 sprints. It is one run, and it started after the night's false-finding fixes (LF.490-492, LF.495), so it suggests those mattered but does not show it.

**The missed edge is a real product bug.** Malformed JSON on `POST /items` answers 500, where 400 or 422 is right. The locked suite did not ask, and the hidden quality test found it. The test's name says a missing field, but the request it sends is unparsable JSON.

**What can improve.**

- **A draft broke the app and the harness recovered without help.** Sprint 2's draft took the suite from 18 passing to 1 (a wrong argument to `init_db()`, and a route that shadowed an imported function). The best-attempt restore put the files back, the dispute read the failure as a product bug, and the re-plan got to 29 of 29. This is the recovery working as intended.
- **Malformed input is an edge nobody was told to test.** A generic probe of each write route with an unparsable body could catch this class for every product, in any stack. It could be added to the contract probes that are built and off (LF.485, LF.488). Not built.
- **21 contract lines were not checked at release,** mostly routes with a parameter. `CONTRACT_PROBE_WITH_A_RECORD` (LF.488) is the measured answer, still off.
- **The suite left cross-user changes untested.** AC-19 checks that one user cannot see another's items, but not that they cannot change or delete them, and the release lists this as open. The hidden tests passed, so the product may well be right, but nothing the customer has proves it.
- **Tool failures doubled** (10.7% against a mean of 5.0%), and identical calls rose. Most of those seen in the audit were withheld reads and edits to another work order's files, refused as designed, though that was not counted by cause. The refusals work, but the model keeps trying.

**The fix-loop group.** Barely exercised here, as on run-ec3e81ab. So far: 5 finished runs on, four at full hidden marks and run-dfcaf697 at 8/9, whose loss traces to a false defect merge (LF.495) rather than the group; 2 off-arm runs, both at full marks. Hidden score can't separate them on these two benchmarks; time and reverts will have to, and tonight's deploys and false findings cloud those.

**How other harnesses handle this.** Mostly vendor posts and community write-ups, and I found no rigorous study of how harnesses verify isolation.

- A write-up of a Tenzai benchmark reports that agents mostly avoided SQL injection and cross-site scripting, while authorization logic errors appeared in most generated apps.
- A Semgrep session abstract says models find missing authorization best within one file, and struggle across files or in middleware. Its results could not be confirmed from the abstract.
- Practitioners recommend a standing test: create two users, make a resource as the first, and try it as the second, on every route. One proposes a scoping layer that adds the caller's id to every query by default.

**Adding value.**

- Generate the two-user test from the interface contract for any product with sign-in: every route with a parameter, tried as the wrong user, on a record made through the contract. `CONTRACT_PROBE_WITH_A_RECORD` already makes the record, so most of the machinery exists. This is a security guarantee a customer can understand and that no test author has to remember. Not built, and it needs care: it must learn from the specification what a refusal should look like.

Sources: [Vibe coding tested: agents and security controls](https://www.pulse.bot/cybersecurity/news/vibe-coding-tested-ai-agents-nail-sqli-but-fail-miserably-on-security-controls-a51a3d24-c87f-4396-b114-527c743e65aa/), [Semgrep: can LLMs really find IDORs?](https://semgrep.dev/events/can-llms-really-find-idors-limits-of-ai-security-reasoning), [AI-generated APIs have an IDOR problem](https://dev.to/c_k_fb750e731394/ai-generated-apis-have-an-idor-problem-3-patterns-cursor-misses-4ji6).

## run-7829e37c (notes-api-hono, :8888, fix-loop group on), completed 2026-11-01 08:37 JST

**Result.** Hidden 9/9, no false acceptance, locked suite 10 passed and 0 failed, visible-hidden gap 0. Mutation 10 of 12 (0.833), 11 of 12 with unit tests, the best on this benchmark tonight. About 41 minutes, 93 tool calls, 7.5% failed: 3 test rounds and 4 fix stages. No KPI regression. The earlier runs of this benchmark took about 93 minutes, 3.5 hours and 4 hours.

**The first run with all of tonight's fixes, and the fastest.** It is one run on one benchmark, and models vary, so this is encouraging and not proof. It met none of the false findings that cost the two previous runs their hours.

**But the short suite proves less.** It has 10 tests where the earlier runs had 17 and 22, yet it caught more mutants, so test count alone is not the measure. The release lists 11 known gaps, five of them criteria QA left open at the lock, and 9 contract lines unchecked.

**What can improve.**

- **Two more blocking design findings were left open,** one of them a contradiction (the testing section's runner against the imports it shows). It did not cost hours this time, but it is the same path as run-0349d8e9. `SETTLE_SPEC_CONTRADICTIONS` is built, off and unmeasured.
- **Two unit tests ship failing.** The release says so and the locked suite passes, but a customer receiving a project with a red unit test may reasonably read that as broken. A release should say this prominently, or the run should repair or remove them on the way out. Not built.
- **The word "escalated to a person" is misleading** on an unattended run: the decision record shows an automatic acceptance. That wording should say what happened.
- **The specification named its own missing dependency,** `tsx`, as a blocking finding. A check of the file plan against the manifest could settle this class without a model. Not built.

**How other harnesses handle this.** No new search for this review: the findings from tonight's earlier reviews on contradiction gates and on evidence for triage apply unchanged.

**Adding value.** Show the known-gaps list as the headline of a release, with plain wording, ranked by what a customer would care about. Eleven gaps on a run scoring full marks means the list needs ordering for it to be read at all.

## run-767b4f54 (notes-api-hono, :8888) and run-4027a954 (tasks-api, :1234), both fix-loop group on, completed 2026-11-01 about 09:27 and 09:33 JST

**Results.** run-767b4f54: hidden 9/9, locked suite 10 of 10, mutation 10 of 12 (12 of 12 with unit tests), about 40 minutes. run-4027a954: hidden 10/10, quality 7/7, locked suite 37 of 37, mutation 3 of 12 (10 of 12 with unit tests), about 84 minutes. Neither was a false acceptance, and both ran on an unchanged image from start to finish.

**The 40 minutes held.** Two notes-api-hono runs in a row now take about 40 minutes, against 93 minutes, 3.5 hours and 4 hours before them. That points to the night's false-finding and evidence fixes, but two runs do not prove it.

**Full marks hide a weak suite on tasks-api.** The locked suite caught 3 of 12 changes to the product, flagged as a regression against a recent mean of 0.775, and 19 contract lines went unchecked. 37 tests that notice so little are testing shape more than behaviour. The unit tests caught 10 of 12, so the project as a whole is better covered than the locked suite alone, but the locked suite is what defines done.

**What can improve.**

- **Contradictions again, on both runs.** Blocking design findings were left open on each: two on run-767b4f54 and one on run-4027a954. This is what the contradiction group now measures.
- **A product that breaks its own contract shipped at release.** run-767b4f54's release reports that the product does not keep its interface contract on one `PUT` line, yet it released and passed the hidden tests. Either the probe is wrong or the suite and hidden tests both missed it. That has not been looked into yet.
- **Eight fixes reverted on run-767b4f54, and a pack rule may be part of it.** A kept start file and smoke test call the factory one way, and the product declared it another. Three fixes in a row each broke the same 23 unit tests. How many of the eight trace to this has not been counted.
- **Dead code shipped.** run-4027a954 has 2 source files, 72 lines, that nothing runs; the release says so.

**How other harnesses handle this.** No new search: the earlier findings apply. Weak suites that pass are the same concern as the mutation-testing literature, and our release already reports them; what it lacks is a consequence.

**Adding value.** A mutation score this low could hold a release back or trigger one targeted round of test writing, at the customer's choice. It is measurable, cheap to explain, and more honest than a green tick.

**Next.** The contradiction group (`SETTLE_SPEC_CONTRADICTIONS`, `UNIT_TESTS_YIELD_TO_THE_LOCKED_SUITE`) went on at 09:49 JST, measured on the next runs against these.

## run-617f1671 (notes-api-hono, :8888), completed 2026-11-01 10:53 JST

**Result.** Hidden 9/9, no false acceptance, locked suite 18 of 18. Mutation 9 of 12, 10 of 12 with unit tests. About 64 minutes, 92 tool calls, 3.3% failed. No KPI regression.

**What this run measured.** Only `UNIT_TESTS_YIELD_TO_THE_LOCKED_SUITE` was effective, and it did not fire. `SETTLE_SPEC_CONTRADICTIONS` was switched on and did nothing, because a run with no judgement model named handed that stage `None` and the step skipped silently. Fixed as LF.501, deployed at 10:57 JST. So this run is a baseline for the group, not a result. The tests had used a stand-in model, which hid it; reading a real run's decision log found it.

**A pattern across the morning's runs: the harness contradicts the specification itself.** The blocking finding here is that `src/main.ts` has contradictory ownership across three sections, and two major findings say the same of the start file and of what a kept file is prescribed to do. run-767b4f54 had the same (signal handlers prescribed for a kept file, and a test-runner contradiction). The architect is writing a specification for files the harness writes and keeps, and the review then spends revisions on it. These runs each used 6 revisions and still ended open.

**What can improve.**

- **Tell the architect what the pack keeps, and what its runner is, before the first draft.** If the specification never prescribes kept files, a recurring class of findings never appears. It is cheaper than settling them afterwards, and deterministic. Check first what the architect is told today: this has not been looked at yet. Not built.
- **Silent skips in switched-on features.** A measured arm that quietly does nothing wastes the measurement. `loop.sh effects` should say when a switch that is on never acted on a run that reached its stage. Not built.
- **Repair scope.** QA's repair changed tests the dispute did not name. Here that made the suite stronger, which is fine, but nothing guarantees the direction.

**How other harnesses handle this.** No new search; the earlier findings apply.

**Adding value.** The same point as the contradiction reviews: every finding the customer never has to read is value. Removing the harness's own contradictions from the specification comes first.

## run-7904116f (tasks-api, :1234), completed 2026-11-01 about 10:59 JST

**Result.** Hidden 10/10, quality 7/7, no false acceptance, locked suite 22 of 22. Mutation 7 of 9, 8 of 9 with unit tests. About 70 minutes, 80 tool calls, 1.2% failed, the lowest failure rate of the night. Interrupted once by a paused deploy at 10:56 JST.

**What this run measured.** Like run-617f1671, a baseline: contradiction rulings were inert for it, and the yield rule did not fire. A fix was reverted twice in a row for breaking the same unit test, `test_signin_success`; whether it would have qualified for the yield rule was not checked. It shipped with that unit defect escalated and accepted. Flagged against recent means: 4 reverted fixes, and one reply lost to the length cap, which cost 15% of output.

**What can improve.** The architect told the setup only in its first request is now fixed as LF.502: the calls writing each section and all revisions had no pack facts, which likely explains the recurring findings about the harness's own files. Merged and not yet deployed, and not yet measured. The new `effects` line (LF.503) now reports a switch that was on and never acted.

**How other harnesses handle this.** No new search; the earlier findings apply.

**Adding value.** Nothing new beyond the earlier reviews.

## run-3095f3a7 (tasks-api, :1234), completed 2026-11-01 about 12:16 JST

**Result.** Hidden 10/10, quality 7/7, no false acceptance, locked suite 35 of 35. Mutation 7 of 12, 10 of 12 with unit tests. About 70 minutes, 75 tool calls, 1.3% failed. Two unit tests ship failing, and the release says so.

**The first real test of contradiction rulings: two rulings proposed, both rejected, none kept.** Both quotes failed the word-for-word check here, and on run-bce0db0a the model quoted the review's finding where it should have quoted the specification, and ruled against the setup's own start command. Had its quotes been right, that wrong ruling would have stood. So the check is earning its place, and the feature as first built was unsafe. LF.504 now tells the call what the setup decides and where to quote from. These runs did not have it, so it is untested. Rulings have not yet produced a single accepted decision.

**A sprint with nothing to do still went through every review.** Sprint 1 held only the health criteria, which the scaffold already passes. It was accepted after about 4 minutes of reviews, with almost nothing built. The result is right and the time is small, but a planner giving a whole sprint to what the setup provides is a small planning fault. Not fixed.

**How other harnesses handle this.** No new search; the earlier findings apply.

**Adding value.** Nothing new beyond the earlier reviews.

**Next.** LF.502-506 went live at 12:20 JST: the design stages told what the setup decides, the ruling call given the same facts, and the exact-count check. run-2363aa37 is the first full run with them. The question it answers is whether design review stops ending on findings about the harness's own files.

## run-bce0db0a (notes-api-hono, :8888), completed 2026-11-01 13:52 JST

**Result.** Hidden 9/9, no false acceptance, locked suite 11 of 11. Mutation 8 of 12, and the unit tests added nothing to that. About 2 hours 55 minutes: 6 test rounds, 12 fix stages, 6 fixes reverted against a mean of 2.4. Against the two 40-minute runs before it, this is what the same benchmark costs when things go wrong.

**Where the time went.**

- **Tests no fix could satisfy.** Two tests asserted exact counts on a list other tests write to. Fixers worked on them for about 90 minutes before a dispute named them. LF.506 now finds this class without a model. It arrived too late for this run.
- **A product bug handed to the wrong stage.** The restart test failed because no store function loaded its data on a fresh start. QA, who may not change the product, spent about 50 minutes on it, in replies of up to 35,000 tokens. Once a fixer had it, the cause was found in minutes. This is the second run with this shape, so `QA_SAYS_THE_PRODUCT_IS_AT_FAULT` is now on as a measured arm.
- **A false finding carried in from design.** The review called the setup's own start command impossible, and the spec went through all its revisions on it, with AC-15 written to use another tool. LF.502 tells the design stages what the setup decides; this run's design stage ran before it.

**What can improve.**

- **A repair can weaken a test beyond what was asked.** Told to stop counting a shared list, QA also removed the checks on each list item's field types. The re-lock's review let it pass, and nothing in the harness compares assertions before and after. A check of what a repair removed, in the tests it was sent to repair, would catch this. Not built.
- **A dispute's ruling quoted the harness's own instructions as the standard.** Its verdict was right, but nothing checked the quote. LF.507 now requires the quote to be in the brief, the specification or the criterion. The cost to watch: a right verdict with a paraphrased quote now stays locked.
- **Mutation stays middling.** 8 of 12, and the unit tests noticed nothing further.

**How other harnesses handle this.** No new search; the earlier findings apply.

**Adding value.** A report of a run's time by cause (tests, product, specification) would have made this run's story visible on one screen. This has come up in three reviews now, so it deserves building.

## run-2363aa37 (tasks-api, :1234), completed 2026-11-01 about 14:28 JST

**Result.** Hidden 10/10, quality 7/7, no false acceptance, locked suite 34 of 34. Mutation 8 of 12, 9 of 12 with unit tests. About 2 hours 8 minutes: 4 test rounds, 7 fix stages, 3 milestone reviews, 3 lead plans. Two replies were lost to the length cap, 18% of output. It is the first full run with the design stages told what the setup decides (LF.502).

**LF.502, first look.** The open design findings no longer concern the harness's own files, here or on run-4958939d. That is what it was built for, and it is two runs. The review still used all six revisions on both, so it has not saved design time yet.

**Correction: a contradiction ruling has been accepted.** My reports said none had been. This run kept one, DR-8, and its statements are not a contradiction: that accounts and items survive a restart, against that editing a title is deferred. One does not rule out the other. It recorded a true fact and changed nothing, so it did no harm, but it is not what the step is for. On the evidence so far, across the four runs where the step could fire: one accepted ruling that says nothing useful, one correctly rejected wrong ruling, and at least one genuine contradiction wrongly rejected, since fixed (LF.508).

**So far the rulings have earned nothing, and LF.502 has done the job they were built for.** They cost one call a run and carry a real risk: a confident ruling reaches every later stage. If the next runs show no ruling that changes an outcome, the recommendation is to park `SETTLE_SPEC_CONTRADICTIONS` under MF.4's rule.

**What can improve.**

- **A defect that cannot be closed cost a re-plan.** A file kept importing a removed name, and the fixer was told so twice. It ended left open, and the sprint was planned again. Not investigated.
- **Replies lost to the length cap** rose to 18% of output. The earlier salvage work may not be covering what stage this is. Not investigated.
- **Slower than earlier tasks-api runs** (about 70 minutes). One run, and it took a paused deploy. Too early to say why.

**How other harnesses handle this.** No new search; the earlier findings apply.

**Adding value.** Nothing new beyond the earlier reviews.

## run-4958939d (notes-api-hono, :8888), completed 2026-11-01 about 14:41 JST

**Result.** Hidden 9/9, no false acceptance, locked suite 13 of 13. Mutation 8 of 12, 11 of 12 with unit tests. About 41 minutes, 60 tool calls, 1.7% failed, no KPI regression, and only 4 known gaps. It is the first notes-api-hono run with the design stages told what the setup decides.

**The cleanest run of this benchmark so far.** Three of the last five on this benchmark took about 40 minutes, and the other two took 64 minutes and nearly 3 hours. Once again the fixer found a restart bug within minutes (a missing load on start), and with no test reopened QA was never sent to it. This run therefore does not exercise the QA hand-back.

**A release that misreported the product.** It said the product does not keep its interface contract, because the probe's own bodiless `POST` drew 422 where the line said 400. The brief allows either. Fixed as LF.509. Run-767b4f54 reported the same kind of thing on a `PUT`, and that one has still not been examined.

**How other harnesses handle this.** No new search; the earlier findings apply.

**Adding value.** A release report a customer can trust needs its false alarms removed first. Each one teaches the reader to ignore the list.

## run-5acea1e1 (notes-api-hono, :8888), completed 2026-11-01 about 16:04 JST

**Result.** Hidden 9/9, no false acceptance, locked suite 14 of 14. Mutation 7 of 12, 10 of 12 with unit tests. About 76 minutes, 99 tool calls, 10.1% failed: 4 test rounds, 7 fix stages, 1 re-plan. Tool failures and defects left open were flagged as regressions.

**The first run with real contradiction rulings, and no sign they helped or hurt.** It kept two. DR-9 settled a real contradiction in favour of requiring both fields on `PUT`, on the brief's words. DR-10 settled how validation is done, which is not much of a contradiction. The product's validator still accepts a missing `body`, so the worry that DR-9 would make creation stricter than the brief did not show here, though whether the `PUT` path follows the ruling was not checked. At 76 minutes this run was slower than the 40-minute runs without rulings, but one run cannot say why. Keep measuring; the park rule stands.

**A dispute that worked.** It found a real test fault, a data file looked for in the wrong folder, and quoted the criterion correctly. QA repaired it in about 3 minutes, and it re-locked on the harness's checks because only that test changed. That is the path the night's fixes were aiming for. Tool failures came largely from QA trying to write product files and being refused.

**How other harnesses handle this.** No new search; the earlier findings apply.

**Adding value.** Nothing new beyond the earlier reviews.

## run-4529981d (tasks-api, :1234), completed 2026-11-01 about 16:23 JST

**Result.** Hidden 10/10, quality 7/7, no false acceptance, locked suite 44 of 44. Mutation 10 of 12, and 12 of 12 with unit tests, the best on this benchmark in this session. About 1 hour 44 minutes: 3 test rounds, 4 fix stages, no re-plans. It passed design review with no escalation, the first tasks-api run I have seen do so since the design stages were told what the setup decides. Two unit tests ship failing, and the release says so.

**The suite improved along with the speed of agreement, though one run cannot credit either to a change.** 44 tests noticed 10 of 12 changes, where this morning's 37-test suite noticed 3 of 12.

**What can improve.** Unit tests shipping red has now happened on several runs: they are the build's own, and a run that ends with them failing is misleading to a customer. A last step that repairs or removes them, and says which, would be worth building. Tool failures (9.3%) were mostly refused edits that changed nothing, which is wasted effort the harness refuses correctly but cannot yet prevent.

**How other harnesses handle this.** No new search; the earlier findings apply.

**Adding value.** Nothing new beyond the earlier reviews.

## run-ff5e0c66 (notes-api-hono, :8888), completed 2026-11-01 about 16:58 JST

**Result.** Hidden 9/9, no false acceptance, locked suite 18 of 18. Mutation 11 of 12, with the unit tests adding nothing: the best on this benchmark so far. About 50 minutes, 77 tool calls and no failed calls, 2 test rounds, 8 fix stages. No KPI regression, and only 3 known gaps.

**The cleanest run of this benchmark so far, and it says nothing about the switch groups.** Contradiction rulings produced none (the file holds an empty list), the yield rule did not fire, and the QA hand-back was not needed. What it does show is that with the design stages told what the setup decides (LF.502), a run can pass design review, build and release in under an hour with no failed calls. It is the fourth run of 50 minutes or less out of the eleven notes-api-hono runs since 10-31, so I would not yet call it the norm.

**One thing to watch.** It restored a locked test file after a scratch file was found in the acceptance folder (`tmp-inline-*.mjs`), which is backlog item B25. It did no harm here, but the harness had to put the locked version back.

**How other harnesses handle this.** No new search; the earlier findings apply.

**Adding value.** Nothing new beyond the earlier reviews.

## run-aa67722c (notes-api-hono, :8888), completed 2026-11-01 about 18:08 JST

**Result.** Hidden 9/9, no false acceptance, locked suite 19 of 19. Mutation 6 of 12, 9 of 12 with the unit tests. About 1 hour, 144 tool calls, 5.6% failed, 3 test rounds, 2 fix stages. No KPI regression.

**A false finding cost this run about ten minutes, and its release now carries the false note.** The check that flags a content type asserted on a `DELETE` answering 204 reopened the suite twice, for a test that deletes a missing note, expects 404 and reads JSON on that 404: the very check the finding recommends. QA could not repair a correct test, so the suite was locked again with the finding as a known-open note, and two copies of it appear in the release's gaps. That is the third false finding from this one check; fixed as LF.510, deployed at 18:17 JST.

**Also on this run.** A contradiction ruling was accepted (DR-9, where signal handlers belong), and a File Plan line still listed an import that is not a valid npm package, left open at design review. The suite is weaker than the best of this benchmark: it noticed 6 of 12 changes, and two persistence-level changes (`true` made `false`) went unnoticed. QA spent 7 failed calls trying to edit a unit-test file it may not touch.

**What can improve.** A check that is wrong three times is a signal to stop trusting pattern checks for this kind of judgement, and to run them as a tentative note that QA can answer, not as a ruling that reopens a suite. `SPEC_DRY_RUN` would replace this class of check, once it has a sandbox.

**How other harnesses handle this.** No new search; the earlier findings apply.

**Adding value.** Nothing new beyond the earlier reviews.

## run-be332286 (notes-api-hono, :8888), completed 2026-11-01 about 19:03 JST

**Result.** Hidden 9/9, no false acceptance, locked suite 24 of 24. Mutation 10 of 12, 12 of 12 with the unit tests. About 45 minutes, 64 tool calls and no failed calls, 3 test rounds, 5 fix stages. The first run with LF.510, and no false content-type finding.

**The same contradiction twice, settled the same way.** This run and run-5acea1e1 each had the specification disagree about whether `PUT /notes/{id}` requires both fields or treats `body` as optional, and each time the ruling chose "both required", on the brief's own words ("replaces both"). That is two real contradictions with the same cause, and both rulings agree with the brief, which is the best case so far for `SETTLE_SPEC_CONTRADICTIONS`. Both runs still scored full marks without needing it to, so it has not yet changed an outcome, and the contradiction repeats because the benchmark's specification produces it: a better fix upstream is to have the architect read the brief's `PUT` line before writing the data model.

**One thing to watch.** Repeated identical calls were 14% of calls against a mean of 3%, the highest this session. With zero failed calls, they are harmless but wasteful, and they may be a stage re-reading the same file in a long pass. Not investigated.

**How other harnesses handle this.** No new search; the earlier findings apply.

**Adding value.** Nothing new beyond the earlier reviews.

## run-fa8e80d7 (tasks-api, :1234), completed 2026-11-01 about 19:21 JST

**Result.** Hidden 10/10, quality 7/7, no false acceptance, locked suite 20 of 20. Mutation 6 of 12, 8 of 12 with the unit tests, flagged as a regression against a recent mean of 0.68. About 2 hours 55 minutes: 5 test rounds, 4 milestone reviews, 4 lead plans, 5 fix stages. Two replies were lost to the length cap, 9% of output.

**Slow, and the slowness is in planning and review, not in fixing.** The suite reached 18 of 20 within an hour of the first draft and 20 of 20 soon after; the other two hours went on sprint plans, four milestone reviews and a re-plan. A milestone review found a real correctness problem in the signin password check (line 89 of the app), and the run recorded it as a risk (DR-12) and shipped it. The hidden tests still passed, so this may be a stricter reading than the brief needs, but it is a finding the harness raised and then chose not to act on.

**What can improve.**

- **A criterion shipped deferred, unproven:** AC-17, the `start.sh` criterion. This is the harness's own kept file, so it is a case for the check that finds tests of a protected file's text (LF.496) and for the naming route (`NAMING_FINDING_BEFORE_DEFERRAL`, off). Why it was deferred was not looked into.
- **A weak locked suite again** (6 of 12), the second tasks-api run in three with a suite that notices little. The reviews have recommended a consequence for a low mutation score, which needs your decision.
- **Seventeen contract lines unchecked at release,** the highest this session; `CONTRACT_PROBE_WITH_A_RECORD` is the answer and is still off.

**How other harnesses handle this.** No new search; the earlier findings apply.

**Adding value.** Nothing new beyond the earlier reviews.

## run-17983a18 (wordstats-cli, :1234), launch sweep, completed 2026-11-01 about 21:13 JST

**Result.** Hidden 6/8, a false acceptance, on a locked suite of 36 of 36. Mutation 4 of 5. About 95 minutes, 144 tool calls, 13.2% failed.

**The failure.** `--top` prints `The 3` where the hidden test expects `the 3`. The specification added a rule of its own, that a word keeps the casing of its first occurrence, and the suite and code followed it. Every locked test agrees with the specification, so nothing inside the run could notice. This is the clearest example so far of a harness weakness the two API benchmarks never showed: the suite proves the product matches the specification, and it cannot prove the specification matches the brief.

**What can improve.** A check at design review that names rules the specification adds to observable output beyond the brief, and asks which the brief supports. Filed for triage; not built. QA also spent most of its failed calls trying to install its own test tools, refused because the brief allows only the standard library.

**How other harnesses handle this.** No new search; the spec-consistency tools noted earlier check a specification against itself, which would not have caught this.

## run-92f8ee23 (fullstack-bookmarks, :8888), launch sweep, completed 2026-11-01 about 21:44 JST

**Result.** Hidden 8/8, no false acceptance, locked suite 22 of 22. Mutation 11 of 12, 12 of 12 with the unit tests. About 2 hours including a failure and a deploy. The last run of this benchmark, on 10-26, scored 3/8 with a false acceptance, so the family has moved a long way on the code since, though this is one run.

**What it found.** A launch blocker in the model pin: an image sent to a model that cannot read it (LF.511, fixed). Two contradiction rulings were accepted. Its product also failed to start for a while, which the fixers resolved.

**What can improve.** The release reports the product does not keep its contract on `DELETE /api/bookmarks/{id} -> 400`; this may be another false alarm of the probe's own making, like LF.509, and has not been examined. A milestone finding about list markup was recorded as a risk, not fixed.

**How other harnesses handle this.** No new search; the earlier findings apply.

## run-7a4a8d63 (fullstack-bookmarks-py, :8888), launch sweep, completed 2026-11-02 about 00:40 JST

**Result.** Hidden 8/8, no false acceptance, locked suite 29 of 29. Mutation 8 of 12, and the unit tests added none. About 2 hours 50 minutes, up from 0/8 on 10-19. It reached this with no stack pack: "no stack pack fits; the agents set the project up".

**What the missing pack costs.** The score held, but the release carries no CI pipeline or container definition, the README does not say how to run the product, and the project setup was never proven (`stack-setup.json` was not written). A milestone review raised the README as blocking, and it was recorded as a risk and shipped. AC-14 shipped deferred. So hidden tests alone overstate this family: a customer gets working code with no packaged way to run it.

**What can improve.** A stack pack for this combination, or a rule that an unpacked project must at least document how to install, start and test itself. To weigh at triage.

**How other harnesses handle this.** No new search; the earlier findings apply.

## run-bfc8c162 (web-todo, :1234), launch sweep, completed 2026-11-02 about 01:12 JST

**Result.** Hidden 9/10, a false acceptance, on a locked suite of 20 of 20. Mutation 8 of 12, 10 of 12 with unit tests. About 4 hours, at the limit of the proposed gate, with about an hour of that on a false finding (LF.512).

**The failure.** A task completed while filtered to Active should leave the list, and it did not. The three locked filter tests never complete a task while a filter is on, so nothing noticed. The brief asks only that filters work correctly, so this is a gap in how far QA thinks through combinations, not a test that was weakened: an earlier suspicion that a repair hid it was checked and is wrong, since that repair made its test stronger. Why the product fails is not yet established; the handler does call a render.

**What can improve.** For anything a brief lets a user change and also filter or view, a test of changing it while viewing. Wording this in general terms for QA, without a stack or a product in it, is the fix to try at triage.

**How other harnesses handle this.** No new search; the earlier findings apply.

## run-101a87aa (web-todo-react, :8888), launch sweep, completed 2026-11-02 about 02:59 JST

**Result.** Hidden 1/10, a false acceptance, on a locked suite of 12 of 12. About 2 hours, 5 sprint attempts. The first scored run of this family. Mutation was not recorded, because my scoring command timed out.

**The failure is a launch blocker: the product does not build.** `npm run build` fails with `TS2503: Cannot find namespace 'JSX'`, so the scorer had no built app to serve and the page was blank. The locked suite runs on the dev server, which does not type-check, and nothing in the harness runs the project's production build. Run by hand on a copy, the build fails the same way. Every family with a build step is exposed.

**Also on this run.** The fixers did real work (state moved up to `App`, a race in loading saved tasks), and one contradiction ruling was accepted (DR-9) with no visible effect. A milestone review raised the 500-line limit as blocking, and it shipped as a recorded risk.

**What can improve.** Running the production build at each test round, as a defect like any other. Being built now as launch fix batch 1.

**How other harnesses handle this.** No new search; running a project's build in CI is ordinary practice, which is why its absence here is a gap.

## run-452d9723, tasks-api-change, 0/15 (11-02)

The first scored change to existing code failed every hidden test at start. The seed stayed at the workspace root, intake pinned a new folder, and the agents rebuilt the product there without `start.sh`, although the brief says it stays at the root. The harness marked the result non-deliverable, but it marked all 9 sweep runs that way, so that does not show it caught this failure.

**To improve:** a seeded product moves into the pinned folder at intake (LF.520, being built), and a seed with no manifest skips the setup stage. Working truly in place, so the customer's layout comes back unchanged, is the longer-term answer. Tools that work on existing repositories generally edit the repository where it is, so this is the gap that matters for real uploads.

**Added value:** low until fixed. Change requests on existing code are likely a main customer use, and today one with no project-like sub-folder cannot succeed.

## run-55de5eb7, textkit-lib, 8/8 (11-02)

Full hidden marks in 49 minutes, but the harness marked the result non-deliverable, because two locked tests were reclassified under dispute and a design finding was left to an escalation.

**To improve:** a correct product was labelled non-deliverable, the mirror image of a false acceptance. A customer would be told not to use something that works. Filed for the sweep's triage: what should count as a gap once the settled suite is green.

**Added value:** high for a small library; the time is the best of the sweep so far.

## run-67b0fb57, notes-api, 9/9 (11-02)

Full hidden marks in 56 minutes, catching 7 of 12 mutations, and again marked non-deliverable. The listed gaps include design findings a decision already settled, mutations that may behave the same, and contract lines with a route parameter that the harness did not probe.

**To improve:** the second full-marks run in a row with this label, so the label is losing its meaning. The real signal, such as the weak mutation score, is buried among items that are already resolved. Filed for triage: separate what is truly unproven from what was settled.

**Added value:** the product is right and fast to build; the verdict the customer reads is what lets it down.

## Sweep finished: the verdict says nothing (11-02)

run-91b34de5, notes-api-js, scored 9/9 in 55 minutes. It was the last of 9 sweep runs: 5 scored full marks, 4 did not, and all 9 ended non-deliverable. The label therefore cannot tell a good product from a bad one, and that weakens the "false acceptance" wording used for earlier runs: those runs were finished and released with gaps listed, and the same list appeared on the good ones.

**To improve:** a verdict split into what truly suggests breakage and what a reader should simply know (LF.521, being built).

**Added value:** this is what a customer reads first, so it matters as much as the score.

## run-d1d5eed8, web-todo-react recheck, 10/10 (11-02)

Up from 1/10 in 48 minutes, catching 11 of 12 mutations. The harness now runs the production build: it failed, was fixed, and a re-measure showed it passing. This run was also the first through the new verdict, and it correctly read as deliverable with notes.

**To improve:** one run is not a confirmation; the release candidate repeats it three times. Most notes on this run are page contract lines the harness cannot probe.

**Added value:** high. This is the clearest single gain of the launch cycle so far.

## run-a5a5854f, wordstats-cli recheck, 8/8 (11-02)

The family's first full marks after 5/8, 5/8, 7/8 and 6/8, in 43 minutes, catching all 4 mutations tried, and read as deliverable with 7 notes.

**To improve:** the score cannot be credited to LF.517. The specification still contains the first-occurrence rule behind the earlier loss, and the design review document does not mention the brief. Whether it was luck or a fix needs the repeat runs.

**Added value:** good if it repeats; the release candidate decides.

## run-b6e4870e, web-todo recheck, 10/10 (11-02)

Full marks in 51 minutes against 9/10 in about 4 hours last time, and read as deliverable. The mutation score, 8 of 12, is the weakest of the rechecks.

**To improve:** this family's past scores run 8, 10, 9, 2, 10, 9, so one 10 proves little, and LF.518 cannot be credited yet. Six defects closed without a fixer as soon as another fix landed, a sign that one cause was reported several times.

**Added value:** the time is the bigger gain if it holds; the release candidate decides.

## run-b8eb5351, tasks-api-change recheck, 15/15 (11-02)

Up from 0/15, catching 10 of 12 mutations. The existing code moved into the project folder, and the product was changed in place (`server.py` +159 lines). About 4 h 25 of clock time, including over an hour paused while my usage limit stopped the fix.

It still ends non-deliverable: the README is one line and never names `start.sh`. For a product that needs only `python3 server.py`, that is a fair complaint worded too strongly. A second run through the sprint was spent only on getting this README written.

**To improve:** a small README step in place of a full round; a test framework ready from the start on projects with no pack; `tmp-inline` files were left at the root here (fixed by LF.526, deployed after this run).

**Added value:** changes to existing code now work on the one brief tried. Still to check: an upload with a project-like folder, a git clone, and the customer getting their repository back nested.

## run-fd0630c7, notes-api-hono, 2026-11-02: 9/9

**To improve:** a work order that breaks tests is rolled back whole, and the sprint can end with the finding unfixed. Here the transaction work order took the suite from 16 passing to 7, the best attempt was put back and nothing retried it, so a requirement security review rated High ships as a note. The fixer's "equivalent" verdict is also unreliable: `db.ts` line 8 was closed as equivalent, then caught by a real test the harness measured.

**How others do it:** not researched for this run.

**Added value:** retry a rolled-back requirement once as a defect naming what broke; accept an equivalence verdict only with a recorded check; stop mutating TypeScript type annotations, which cannot change behaviour.

## run-304c1913, fullstack-bookmarks-py, 2026-11-02: 3/8, own suite 27/27

**To improve:** a stack with no pack lost every page check, so a suite finding things by CSS classes could pass a product that ignored the brief's stated structure. Reading a suite for what it proves should not depend on which pack set up the project. The release verdict read non-deliverable, but for an unrelated setup gap, so it reached the right answer by luck. A test tool also went into the product's own requirements file.

**How others do it:** not researched for this run.

**Added value:** LF.534 closes this for JavaScript browser suites. Python browser suites still have no such patterns, and no-pack suites still cannot have page lines of the interface contract probed at release.

## run-304c1913 after rewinds, fullstack-bookmarks-py, 2026-11-02: 8/8

**To improve:** the suite caught only 4 of 12 deliberate changes, the lowest here, so a green suite says little beyond what it was made to check. One fix stage spent 49 minutes on a defect the page could not close. The same report-path slip cost a round in each attempt.

**How others do it:** not researched for this run.

**Added value:** re-check remaining defects after each fix so a test at fault goes to QA sooner; a stack pack for this family would give it the checks a no-pack suite still lacks.

## run-eba03186, wordstats-cli, RC 1, 2026-11-02: 8/8

**To improve:** the product is labelled non-deliverable at full hidden marks for one failing unit test of its own, which a customer reads as the product failing. A sprint accepted on its suite alone had no review read its code. Mutation tried only 2 changes, too few to say much.

**How others do it:** not researched for this run.

**Added value:** say plainly that the tests the customer's brief defines pass and one internal test does not, instead of one pass or fail label.

## run-6e190dfa, web-todo, RC 1, 2026-11-02: full marks

**To improve:** half of all reads were repeats, mostly in the fix stages, and fixers rewrote a defect five times before one changed approach. The release checked none of the 17 contract lines, since they follow none of its three forms.

**How others do it:** not researched for this run.

**Added value:** give a repeated fixer the earlier failed attempts so it changes approach sooner; write contract lines the release can actually probe.

## run-0d817a9a, fullstack-bookmarks-py, RC 1, 2026-11-02: hidden could not run

**To improve:** the product shipped a start script that cannot start while its own suite passed 33 of 33, because the suite started the server itself. A customer's first command would have failed. The non-deliverable label was right only by accident.

**How others do it:** not researched for this run.

**Added value:** run the product the way its customer will, its own start command, as part of every green suite (LF.537). The acceptance suite should also start the product through that command, not its own, which LF.537 does not yet require.

## run-4e57c399, web-todo-react, 2026-11-02: hidden 10/10, page visibly broken

**To improve:** the task list is measured at 34 pixels wide, so a person cannot read it, and the benchmark's hidden tests still pass because they read text without checking it can be seen. The harness read the run as non-deliverable, which was correct. Fixers spent two hours reading the wrong element's style.

**How others do it:** not researched for this run.

**Added value:** a real look at the page for layout, not only text; the screenshot rubric is the existing feature closest to this. Hidden page tests should require visibility.

## run-9bc85e07 fullstack-bookmarks 8/8, run-da433831 textkit-lib 0/8, 2026-11-02

**To improve:** textkit's own suite passed 22 of 23 while a customer's import found nothing, because the test runner's path made a broken layout work. Fullstack lost an hour to a dropped page work order. Wrong tests stayed locked after correct rulings were refused, and a fixer then bent a correct function to suit one.

**How others do it:** not researched for this run.

**Added value:** check a library the way its user imports it, as LF.537 now checks a service's own start; protect a scaffold's package files from being deleted by a fix.

## run-f0bf8a48, textkit-lib, clean, 2026-11-02: 8/8, deliverable

**To improve:** the suite caught only 2 of 4 deliberate changes, and two findings of untested behaviour ship as notes. The code lives in one `textkit.py` file beside an empty package folder, which works but is not the layout the scaffold set up. 23 contract lines could not be checked at release, since a library call follows none of the release's probe forms.

**How others do it:** not researched for this run.

**Added value:** a release probe that can call a library function and compare its return value would check this family's contract the way the HTTP probe checks a service's.

## run-eb5cffb8, fullstack-bookmarks-py, 2026-11-03: hidden 0/8, own suite 38/38

**To improve:** the product starts only when its folder is named `bookmarks`, because `start.sh` imports `bookmarks.app` through the parent folder. A customer unpacking it under any other name gets an import error. The harness's start check ran it from a folder with the right name and passed it; the scorer copies it to `product/`, as a customer would, and failed. The fixer did repair the earlier start fault in one attempt once LF.545 told it.

**How others do it:** not researched for this run.

**Added value:** start the product from a copy under another name, as it is delivered (LF.547); a Python pack rule that the app module is never addressed through the project folder's name.

## run-a69ff175, notes-api-hono, clean 1 of 3, 2026-11-03: 9/9

**To improve:** the product passes every hidden test and still reads non-deliverable, because a release probe reports `PUT /notes/:id` outside 200 or 404. A customer reading that label would not ship a working product. The suite also missed one deliberate change on line 30 of the service, which ships as a note.

**How others do it:** not researched for this run.

**Added value:** a release probe that sends a write with a valid body, or marks a bodiless write unchecked as it already does for POST (LF.509); the label then means what it says.

## run-8ac0e9c0, tasks-api, 2026-11-03: 10/10, non-deliverable

**To improve:** a design-stage contradiction (a missing Authorization header answered 422 by the framework's default, 401 by the error catalogue) was correctly ruled on at 07:03 and the ruling was thrown away by a word-for-word quote check. The contradiction then cost three reverted fixes, eight open defects and three unit tests shipping failing, in a run whose hidden tests all pass. The re-plan added a testing work order rather than changing the failing code.

**How others do it:** not researched for this run.

**Added value:** LF.550 keeps such rulings; the remaining cost is the re-plan shape (deep review, code finding 3). A run at full hidden marks with a settled contradiction would have read deliverable.

## run-7570da3a, fullstack-bookmarks-py 1c, 2026-11-03: 7/8 at a green suite

**To improve:** the setup stage built the whole product and the suite passed 22 of 22 on it, so no build sprint ran; the filter field had only a placeholder, the suite found it by that placeholder, and the hidden test by label timed out. A replayed proven setup gave the run a derived pack with no page patterns, so LF.534's checks were silent. 4 h 17 of wall time, 56 minutes of it design and 70 in setup.

**How others do it:** not researched for this run.

**Added value:** LF.552 gives derived packs the browser pack's page checks. A stack pack for this family would remove the setup stage and most of the time; it is the strongest remaining case for one.

**Run review 2026-11-03: notes-api-hono 1c (run-625064d3), 9/9 hidden, no false acceptance, finished 10:38 JST.** To improve: the release still lists 8 interface contract lines unchecked and no review read the code, so a full score rests on the locked suite alone. Added value next: the usable flag and the clean-install gate from the deep review. Separately, the Settings page saved a key that could not work and gave no reason; the settings check now shows the provider's own message before a run starts.

**Run review 2026-11-03: notes-api 2a (run-9747df55), 9/9 hidden, no false acceptance, mutation 0.625, 96 min (10:53 to 12:30 JST), mixed versions (LF.556 deployed mid-run).** To improve: two fix stages and over 30 minutes went at a correct product because a pytest test counted a list other tests wrote to; the shared-list check read only JavaScript. LF.556 now reads Python too, and in this run it reopened the suite, QA repaired it, and the same product passed 13 of 13. How others do it: test isolation per test (a fresh store or a transaction rolled back) is the common answer; ours names the fault instead, because the shared service is the run's own. Added value next: a stable stage opening and no mid-stage history rewrites, the largest steady waste today (about 0.6M uncached tokens on the slow model).

**Run reviews 2026-11-03 14:15 JST.** web-todo 1b (run-37d4fe76, the slower model): 10/10 hidden, no false acceptance; 8 page defects in its first round, 3 fixed and 5 closed by measurement once a fix covered them; about 2M uncached prompt tokens from changed stage openings were its largest cost. fullstack-bookmarks-py 2a (run-c54c3d41): failed at the suite after 84 minutes: the second runner's command asked Playwright for a report in a form it does not read, and five rounds were told only where the report was missing. LF.557 now names the command and gives each runner's JUnit form. How others do it: test frameworks are set up from a template whose reporter is fixed; ours lets the suite author declare it, so the harness must check it. Added value next: check a declared runner's report form at the lock, before any round.

**Run review 2026-11-03: fullstack-bookmarks-py 2b (run-e6542099), 3/8 hidden, false acceptance, finished 15:59 JST (mixed: LF.558 and LF.559 deployed mid-run).** The page drew each bookmark as a div where the brief says each is an item of a list, so all five page tests failed. The suite found records by a class and passed 25 of 25. The harness has a check for exactly this, and it raised it during the suite review; the suite then reached the round cap and was locked with the finding open, and nothing carried it on to the build, the reviews or the release. To improve: a too-lenient finding open at the lock must become something the build answers for, not disappear. How others do it: accessibility linters check list and table semantics on the product itself rather than through the tests. Added value next: check the delivered page for the record kind the brief names when the suite cannot be made to.

**Run review 2026-11-03: fullstack-bookmarks-py 2c (run-0743adbc), 8/8 hidden, no false acceptance, 16:30 to 18:53 JST (mixed: LF.561 to LF.563 deployed mid-run).** The page drew list items this time, so LF.560 rightly stayed quiet. What cost time: three suite rounds that collected nothing because the commands named files in the wrong folder (LF.562 fixed it in one round once its message arrived), and two wrong blocking cross-file defects (Python Playwright not counted; the suite's own manifest asked for a test script) that sent fixers to rewrite the page twice, harmlessly this time (LF.563). How others do it: test discovery is fixed by convention (one folder, one runner), so a path mistake cannot happen; ours lets the writer declare commands, so the harness must say where they run. Added value next: the replayed proven setup should install into a project environment (two setup attempts lost about 25 minutes).

**Run review 2026-11-03: RC1 notes-api-hono 1 (run-7e3d3acb), 9/9 hidden, no false acceptance, mutation 0.833, 18:55 to 19:44 JST on the frozen bf23015.** The first counted release-candidate result. One real defect: the product read its data folder when the module loaded, so its own unit tests could not point it elsewhere; the second fixer found and fixed the cause in about 15 minutes. Tool failures were twice the recent average (the architect's doc reads already done for it, counted as refusals); they cost nothing but inflate the KPI, so the KPI should not count an intended refusal as a failure. How others do it: lazy configuration is the common idiom for testable services. Added value next: count intended refusals apart from real tool failures in the KPI.

**Run review 2026-11-03: web-todo 1c (run-aceb831c, the slower model on :1234), 9/10 hidden, false acceptance, 14:19 to 22:53 JST (mixed; paused 30 min by the owner).** Lost: "a task completed while filtered to active leaves the active list". After the build, the harness found one locked test that could not pass and reopened the suite; the repair made it worse (1 problem, then 3) and took about 2.5 hours on this model, then the harness deferred AC-9 (the Done checkbox) as untestable, and the hidden test of that behaviour failed. To improve: a suite repair may never leave the suite worse than it started; the previous suite comes back instead, and a criterion is deferred only when no repair could test it. How others do it: test repair is usually scoped to the failing test with the rest frozen. Added value next: that rule, first in the Fix batch. Also: model errors 7 against a mean of 0.6 and prefill twice the usual, from the slow model's long prompts.

**Run review 2026-11-03: RC2 tasks-api 1 (run-cdfc8a19), 10/10 hidden, no false acceptance, 20:46 to 23:23 JST (28 min of it queued for a worker).** The held-out family, first try on the frozen version. Its only trouble was the product's own unit tests: one expected a request object to refuse an empty field, while the product refuses it at the route; the sprint was planned again after two rounds, and a fixer then settled it and two unit-test fixes were proven by measurement. Waste: 28 minutes queued for a worker slot while the model server sat idle (grown to three slots live). How others do it: unit tests that pin down an internal choice are usually left to the team; ours treats a red unit test as a defect, which costs a re-plan when the acceptance suite is nearly green. Added value next: keep three worker slots by default.

**Run review 2026-11-04: web-todo 1 (run-32bffa53, :1234), 10/10 hidden, no false acceptance, 22:57 to 01:10 JST (mixed: LF.565 to LF.567 deployed mid-run).** The test that cost run 1c its point (a task completed while filtered to active leaves the active list) now passes. The last defect, a filter test, survived three fixers; the harness then sent its test to dispute, the ruling found the test wrong (it unticked an item the Active filter had rightly hidden), QA repaired only that test, and the product stood. Contrast with 1c, where a false finding led to a worsening repair and a deferral. The run also showed the slower model at about 2 h 15 m for this family. Added value next: the rule that a repair may never leave the suite worse, so a bad repair can never end in a deferral again.

**Run reviews 2026-11-04 02:55 JST.** RC3 web-todo 1 (run-49ceb94d, :1234, counted): 10/10, no false acceptance, 1 h 35 m. The check for a locator that stops matching once its test edits the item reopened six edit tests before any fixer ran; after their repair two short fix rounds cleared the real defects. fullstack-bookmarks-py 1 (run-5a3a8dcc, :8888, mixed): 8/8, no false acceptance, 3 h 20 m. Its suite's shared API fixture called a test library with an argument the installed version rejects, so 18 tests failed before reaching the product, and six fixers spent about 45 minutes on the product until a dispute sent the suite back; LF.568 now names such a shared-setup failure at once. LF.557's message also earned its keep: a report written one folder too deep was fixed in a single round. Added value next: the Fix batch (LF.568, a repair that may not worsen the suite, three worker slots) after RC3.

**Run reviews 2026-11-04 04:05 JST (RC3, counted, f33ea83).** notes-api-hono 1 (run-0dd4c424): 9/9, no false acceptance, 58 min; three suite writers, then the product was built clean in one drafting pass and needed no fix round. web-todo 2 (run-c02293f3, the slower model): 10/10, no false acceptance, 58 min; a quick start (design and suite each passed their first review), one fix held and two more defects closed by measurement. Both show the frozen version doing what it should with nothing to triage. Added value next: keep the candidate running; RC3 is 3 of 3 full.

**Run review 2026-11-04 12:15 JST.** RC3 notes-api 2 (run-0245e825, :1234, mixed): 9/9, no false acceptance, mutation 0.583. Its locked suite fell from 17/17 to 3/17 with clean code because a deliberate change put back within the same second left Python's compiled copy of the change running (LF.573, deployed into it); the audits had read stages, not suite numbers, so the fall went unseen for a round, and LF.574 now keeps every measurement and names the same product measuring worse. Cost against the last five runs: 3 replies lost to the output cap, 4 model errors, 36% of file reads repeated - the slower model, not a harness fault. How others do it: build tools such as Bazel key their caches on content hashes rather than file times, the general cure for this class; the harness now gives a put-back file a later time, and restoring by content is the stronger follow-up. Added value next: a suite score that falls on an unchanged product should hold the milestone review, not only be logged.

**Run review 2026-11-04 14:02 JST.** RC3 tasks-api 2 (run-0e6c0986, :8888, mixed): 10/10, no false acceptance. Eight of its eleven defects closed by measurement without a fixer; the run then waited about three hours on a model server that aborted on its large plan-review request after the host restart, and finished once the owner fixed the server. Its 48 model errors exposed a measurement fault the owner spotted on the pressure card: an errored request stayed open, so the next reply was timed from it, pauses and restarts included (overall speed shown 7.8 tokens/s, real 33.4; LF.577). How others do it: tracing tools such as OpenTelemetry close a span on error as well as on success, so a failed call never lends its start to the next one; the harness now does the same in all four places it pairs requests with replies. Added value next: show the run's paused and errored time beside the speed, so a slow figure says why.

**Run review 2026-11-04 15:10 JST.** RC4 notes-api-hono 1 (run-6b01808f, :8888, counted, ee48b84): 9/9, no false acceptance, 60 min. The suite passed its first review and the product passed it at the first test round (17/0); the rest was test strength: one unit-test setup fault closed by measurement, one mutant killed by a new test the harness proved, and one (`||` made `&&` in `app.ts`) shipped as a named gap after two tries. The clean run shows the frozen version doing its job. How others do it: mutation tools such as Stryker report a survivor and leave it to a person rather than spending a round on it; the harness's two-try cap with a named gap is the same trade. Added value next: carry a surviving mutant into the next sprint's testing work as a named item instead of only the release notes.

**Run review 2026-11-04 17:30 JST.** RC4 notes-api 1 (run-cf0ddc97, :1234, mixed): 8/9, a false acceptance. The brief says once that a missing or empty title is refused; the suite tested that on create only, and the product accepts an update that empties the title. Earlier runs' lock notes named the same gap (no test of `PUT` with an empty title), so it is a recurring hole, not bad luck. The run also shipped 44 failing unit tests (mutation 0.083) and a fixer added an unrequested, unauthenticated `DELETE /notes` that clears everything, to isolate its tests. How others do it: API fuzzers such as Schemathesis derive negative cases from the contract for every operation that takes a field, rather than trusting hand-written tests to cover each one. Added value next: the harness's release probe should do the same for refusal rules - empty each field the specification refuses empty on every write route and expect a 4xx - and a fixer should not add a route the interface contract does not name.

**Run review 2026-11-04 18:00 JST.** RC4 web-todo 1 (run-a135c8cf, :8888, mixed): 10/10, no false acceptance, 2 h 46 min. About 70 minutes went to fixing a product against a filtering test that gave its locators `'^B$'` as text, which no page can match; LF.578 sent it back to the suite writer, who corrected all six lines in two minutes. The test LF.569 made the suite write (act on an item while a filter is on) then caught a real fault, which three fix attempts could not close and the re-planned sprint did. Costs above the recent mean: 39% of file reads repeated, 5 defects left open, 1 fix reverted. How others do it: Playwright's own linter (eslint-plugin-playwright) flags misused locator options statically; the harness now does the same for this case. Added value next: run the text checks on a suite before its first review, not only at a measured round, so a broken locator never reaches a fixer.

**Run review 2026-11-04 18:17 JST.** RC5 tasks-api 1 (run-d1e03017, :1234, counted, 0751b4f): 10/10, no false acceptance, 48 min. The suite needed one rewrite before its review passed; the product passed it after three defects (one fixed, one closed by measurement), and the release named two unit tests still failing and two suite gaps (start.sh's DATA\_DIR, the list's item shape). Costs above the mean: 9% of tool calls failed, mutation 0.583. How others do it: test-generation tools such as Hypothesis-based API testers check response shape on every endpoint rather than per hand-written test, which would close the item-shape gap the suite review named. Added value next: the emptied-field probe in build applies the same idea to refusal rules.

**Run review 2026-11-04 19:28 JST.** RC5 notes-api-hono 1 (run-3b50fd2f, :1234, mixed): 9/9, no false acceptance, 63 min. The suite was green at the first round (12/0); the rest was test strength: one mutant killed by a new test the harness proved, one fix reverted for breaking a passing unit test, and one mutant judged equivalent because it sat in dead code. LF.579's probe had what it needed here (it read `title` from the criteria and would ask both the create and the update). Costs above the mean: 3.4% of tool calls were identical repeats. How others do it: mutation tools such as Stryker mark mutants in unreachable code as 'no coverage' rather than spending a fixer on them; the harness reached the same verdict through its equivalent-mutant check. Added value next: give the emptied-field probe an example body without an `id`, so a refusal for the extra field cannot pass for a refusal of the empty one.

**Run review 2026-11-04 20:46 JST.** RC6 notes-api 1 (run-1a17cf7f, :1234, counted, a0473c4): 9/9, no false acceptance, 73 min - the family that shipped an update with an empty title this afternoon. This time the suite tested the refusal on update too, the fixer added the title check to both the create and update models, and LF.579's probe found nothing left to raise. LF.556 reopened two tests that counted every note on a shared server before a fixer spent time on them. Mutation 0.545, below the mean: the unit tests are the weak side. How others do it: property-based tools (Hypothesis) generate the invalid inputs for every model that takes a field instead of one hand-written case; the harness's probe now does that for the HTTP side. Added value next: carry the same emptied-field idea into the unit tests the testing role writes, which would also lift the mutation score.

**Run review 2026-11-05 09:58 JST.** RC6 notes-api-hono 1 (run-37f78b1b, :1234, counted, a0473c4): 9/9, no false acceptance, mutation 0.75. It paused overnight with the sprint about to be planned and, after a host restart, finished seven minutes after it was resumed - the pause and resume kept every stage's state. The design review escalated once (findings left open, the run went on with the latest design), and the release named two unit tests still failing after the remediation limit. Cost above the mean: 6% of calls were identical repeats. How others do it: durable-workflow engines (Temporal, LangGraph checkpoints) make a long run survive a restart the same way; the harness's run store already does, which this run showed. Added value next: when only unit tests fail at the remediation limit, say in the release which behaviour they covered, so a person can judge the gap without reading them.

**Run review 2026-11-05 11:17 JST.** RC6 web-todo 1 (run-a9aefc9d, :1234, mixed: LF.580-581 deployed into it): 10/10, no false acceptance, 71 min. Its first fixer rewrote a unit-test file from the failure output - the drafting-order fault LF.580 now removes. The suite's three tests of acting inside a filtered view failed against a product that filtered; two fix rounds went at the product, then the dispute ruled the tests wrong and the suite writer corrected them (16/16). Costs above the mean: 3 defects left open, 2 model errors, 6% of tool calls refused. How others do it: test-generation tools (Playwright's codegen, record-and-replay) derive a page test from what the page actually does, so a locator cannot name a state the page never reaches. Added value next: when a page test times out waiting for a control, the harness could check whether the control exists at all in the page it failed on before any fixer is sent - the same evidence the dispute used, an hour earlier.

**Run review 2026-11-05 17:47 JST.** RC11 tasks-api 1 (run-926a1029, :8888, mixed: LF.587 deployed into it): 10/10, no false acceptance, 2 h. Two of today's fixes fired and helped: LF.583 sent one weak test back before the lock (about 3.5 minutes), and LF.587 caught a test that counted every account in the product's database while the rest of the suite wrote to it (`assert 19 == 0`) - but only after four fix rounds and a re-plan had gone at a product that was right, because it was built from this run. Fix stages that took long still fixed at the same rate as short ones (measured over 155: 42% vs 43%), so slow fixers are the model's pace, not waste to cut. How others do it: test frameworks isolate state per test (a fresh database or a transaction rolled back after each one) so a count can never see another test's rows; the harness could hand the suite a per-test data folder through its fixture instead of policing counts after the fact. Added value next: that per-test isolation in the packs' acceptance fixtures.

**Run review 2026-11-04: RC3 notes-api 1 (run-fe8bb168), 9/9 hidden, no false acceptance, 41 min, counted.** Three suite writers, one build, then the product's own unit tests carried the rest: two unit-test fixes were proven by measurement, and after two rounds every acceptance test passed while some unit tests still failed; the unattended escalation released it with those recorded as known issues. The hidden tests agree the product works. To watch: a release with failing unit tests is right here, but the record should keep saying so plainly (it does, as known issues).

**Run review 2026-11-04: RC3 web-todo 3 (run-238fd986, :1234, counted), 9/10 hidden, a false acceptance, 04:08 to 05:52 JST.** Lost: "a task completed while filtered to active leaves the active list" - the same hidden test 1c lost. The suite's filter test set items done before choosing a filter; no test completed an item while the Active view showed it, and the product left the completed item in that view. The experiment TESTS\_OF\_ACTIONS\_WITHIN\_A\_VIEW, a prompt rule asking for exactly such tests, was on and the writers still did not write one. To improve: replace the prompt rule with a deterministic page check, the way the record-kind and control-name checks work - when the brief names a filtered view and an action that changes what the view shows, the locked suite must hold a test that takes the action while that view is showing. How others do it: state-transition test generation from a model of the views. First item of the Fix batch.

**Run review 2026-11-04: RC3 tasks-api 1 (run-2af46bfb), 10/10 hidden, no false acceptance, 67 min, counted.** The held-out family again full. Its first build set up its data storage so the server answered 500 to most requests (10 of 37 tests passing); round 2's fixes cleared it, the measurement then closed four defects without a fixer, and three unit-test fixes were proven by measurement. The fix loop worked as designed on a broad failure with one cause.

**Run review 2026-11-04: RC3 notes-api-hono 2 (run-7d265888, :1234, counted), 9/9 hidden, no false acceptance, 64 min.** The second family to run cleanly on the slower model. After the build, two rounds went to the product's own unit tests; both fixes that held were proven by measurement (the tests fail with the change and pass without it). Nothing to triage.

**Run review 2026-11-04: RC3 fullstack-bookmarks-py 1 (run-fd60d938, counted, :8888), 8/8 hidden, no false acceptance, 3 h 50 m.** Full marks but the slowest run of the candidate, and nearly every lost hour was the harness's own: the stale proven setup failed its replay and setup ended unproven (LF.570 sets such an entry aside); three page tests asked the whole page for a Delete control every bookmark has, and two fix rounds went at a correct product before a dispute (LF.571 names them at the first round); the repair then dropped 20 browser tests from the run (LF.572 puts the locked suite back); and the lead's next plan was refused three times for a missing testing work order. A test writer also tried 22 times to delete product files; every one was refused. Added value next: deploy the Fix batch after the candidate - this family's time should roughly halve.

## End-of-run review: 2026-11-05 evening

### fullstack-bookmarks-py 1: 6/8, a false acceptance

- **What failed.** After a successful save, the page left its Save button disabled and labelled "Saving…". A person could save one bookmark and never a second. Every locked test saved a single record per page, so the suite passed; both hidden tests that save twice from one page timed out.
- **Feature to improve.** The suites test each action once, on a fresh page. Real use is a sequence of actions in one session.
- **How other harnesses do it.** Agentic test generators (for example SWE-agent style reproduction tests and Playwright codegen flows) record a user journey of several steps, not single actions. Property-style UI testing repeats each action to catch state that is not reset.
- **Added value, built (LF.599).** The suite writer now adds two records in a row from the same page without reloading, and checks both are shown. This is a quality rule, always on.
- **Time.** About 5 h with 10 defects left open. Each fix took 30 to 45 minutes and left the defect open, on a server that reports no cached tokens. The next run on this family (L fullstack-bookmarks-py 2) runs fully on the new version.

### L notes-api 1: 9/9

- **What worked.** One undefined name broke all 17 criteria. One fix closed it, and the others closed without a fixer (LF.588 grouped them).
- **What its score surfaced.** The interface-contract probes (each line asked bare, each write with an unparsable body, each refused field sent empty) had never run on the Python service stacks, because they ran only through Playwright.
- **Added value, built (LF.600).** A pytest probe runner. On this run's stored product it cut the release lines left unchecked from 6 to 1.
- **Feature to improve.** A mutation (`True` changed to `False` in `__init__.py`) went unnoticed, and the AC-15 start-script test was locked weak. Both are already recorded as completion gaps; watch whether LF.583 (a test too weak to lock goes back once at the review limit) reaches criteria like this one.

### Across today's runs

- Suite writers trying to build the product: 106 refused writes over 30 runs. LF.597 cut it to 0 in the next run.
- Stages trying to delete the harness's scratch files: 67 tries over 30 runs (LF.602).
- Design sent back by its own construction: spec parts cited criterion ids being written at the same time (LF.601).

## End-of-run review: L web-todo 1, 10/10 (2026-11-06 11:11 JST)

- **Result.** 10/10 hidden tests, no false acceptance. Active time was 215 minutes, against a usual 70 to 100.
- **Where the time went.**
  - The suite was locked at its review limit with whole-page lookups no product could pass. They came back only after a build. This is fixed by LF.609: they go back once at the limit.
  - Four fixes were reverted while chasing an AC-13 test that wanted each record's checkbox visible during an edit. The hidden tests do not ask for that, so the suite asked for more than the brief.
- **Feature to improve.** An over-specified locked test still costs fix rounds. The brief-over-spec rule (QA\_RULE) is given to the suite writer but not to the dispute judge, which settles whether a test or the product is at fault. That gap was found in the prompt review and is queued.
- **How others do it.** SWE-bench-style harnesses validate tests against a reference solution before trusting them. Here, a test that every fix fails against, while the rest of the suite stays green, is the signal that the test, not the product, should be disputed.
- **Added value queued.** Give the dispute judge the brief-over-spec rule. When fixes for one criterion keep breaking others and get reverted twice, raise a dispute of that test instead of starting another fix round.

## L fullstack-bookmarks-py 4 - 7/8, a false acceptance (2026-11-06 23:30 JST)

- **What the product got wrong:** the brief shows each bookmark's title as a link to its URL; the page showed the title as plain text and linked the URL itself. A person sees two lines where the brief promised one link.
- **Why the harness passed it:** the locked test found the link with `locator('a')` - any link in the record - so a page linking the wrong text passed. 6 of 79 stored suites found a link the same way. Fixed as LF.642: a control found by its tag alone goes back to the suite writer before the lock.
- **Other quality signals:** mutation score 0.25 (recent mean 0.48); 2 unit tests shipped failing because a builder wrote a second app module at the project root beside the pack's own (one run only, watched).
- **How other harnesses handle it:** tools that test through the accessibility tree (role and accessible name, as Playwright's own guidance recommends) catch this by construction; our suites now must too.
- **Added value of tonight's fixes:** LF.638-639 stop tests that compare a promise from reaching fixers; LF.640-641 let a right dispute ruling reopen the suite instead of forcing a re-plan.

## L web-todo 3 - 10/10 (2026-11-07 00:04 JST, :1234)

- **Product:** right on every hidden test; mutation score 0.583 (recent mean 0.733), so its own suite is weaker than usual at catching changed code.
- **Where the time went:** 13 defects left open (mean 4.8). Two locked tests counted three records after making two; fixers could not close them, and right dispute rulings were refused by the quote guard three times (a reason after a dash, then a criterion's label). Fixed as LF.640-641; verified live when the replayed dispute reopened both tests.
- **Scoring:** first scored against the wrong benchmark - the last-started brief belonged to the other port's family. Fixed as LF.643: a run is scored against the benchmark of its own brief.
- **Feature to improve:** a test that counts more records than its own steps make could be caught before the lock by running each failing count against what the test created; for now the fixer's report plus the dispute catch it within one round.
- **How other harnesses do it:** review-and-judge loops (a second model checking a ruling) accept a judge's quote by meaning, not by exact words; ours stays word-based so an invented standard is still refused, now tolerant of glosses and labels.

## L notes-api-hono 1 - 9/9 (2026-11-07 01:50 JST, :1234)

- **Product:** right on every hidden test; acceptance green from the first round. Three changed lines its unit tests did not notice were shipped as named gaps.
- **Where the time went:** design escalated after two reviews over behaviour planned into the kept `src/main.ts` (LF.645 now shows that file to every stage); the last-sprint brief check then called `update` undelivered because the route is `app.put(...)` - an escalation and a second round of planning and four reviews on a finished product (LF.648).
- **Waste signals:** tool failures 10.9% (edit text not matching the file exactly); redundant reads 28% against a mean of 18%.
- **Feature to improve:** the end-of-run brief check should read the product the way the brief states it - routes for a service, controls for a page - not by keyword; LF.648 does this for HTTP methods.
- **How other harnesses do it:** API-first agents (spec-to-route generators) check delivery against the route table, not identifiers; that is the form LF.648 takes.

## L fullstack-bookmarks-py 6 - 8/8 (2026-11-07 05:20 JST, :8888)

- **Product:** every hidden test passes; the locked suite (21 tests) agreed exactly with the hidden one.
- **What changed from runs 3-5 (7/8, 7/8, cancelled):** the plain-page pack was chosen (LF.644); the suite found each link by the bookmark's title (LF.642) and awaited every value (LF.639); and, after a rewind to its lock, its page counts were narrowed to each test's own records (LF.651).
- **What the rewind showed:** before it, three hours of fixers bent the product around tests that counted a shared list - an unrequested delete-all route, data cleared at start, `init()` never called. Wrong tests do not only waste time; they damage the product. A check for clear-all routes the brief never asked for is queued.
- **Still weak:** backend unit tests imported `bookmarks.bookmarks.main` (LF.653 now gives the import name) and shipped two faults as named gaps.
- **How other harnesses do it:** test isolation is the suite's job (fresh data per test, or tests that look for their own records) - never the product's. Ours now enforces the second form.

## L tasks-api 3 - 10/10 (2026-11-07 04:39 JST, :1234)

- **Product:** every hidden test passes; locked suite 66/66.
- **Weak spots:** mutation score 0.167 (mean 0.58) - its unit tests patched an immutable SQLite connection and never held the code; 7 defects left open; one reply lost to the length cap.
- **Where the time went:** the architect's core was lost as an empty answer call (LF.650, 37 such losses in 10 runs) and two design reviews rebuilt it; a dispute correctly reopened two delete tests.
- **Feature to improve:** unit tests that cannot run (a patch Python refuses) should be sent back as broken tests, not fixed as product defects - as the acceptance suite's own checks already do.

## L notes-api-falcon 5 (2026-11-07, 9/9)

**To improve:** the design is written before a stack no pack covers is set up, so the specification can contradict the proven setup (here Falcon's WSGI app under an ASGI server); and fixers saw only the first frames of a long failure, so 15 in a row repeated a change that stopped the product starting.

**How others do it:** repository-setup agents treat the environment they proved as ground truth and replay it; coding agents (SWE-agent, OpenHands) show the tail of a traceback and the last error first, and carry what a failed attempt hit into the next one.

**Built (value):** LF.666 builders see the setup's proven entry code and keep it over the specification; LF.667/668 a failure keeps its raised error; LF.669 fixers after a broken-start revert are told the streak and the error (128 such reverts over 37 runs, \~9-10 h of fixer time). Five fixes were kept within 10 minutes of LF.667. Next: confirm on falcon 6 from its start; review the whole failure-evidence path (five point fixes).

## L tasks-api 4 (2026-11-07, 10/10)

**To improve:** a product whose locked suite passed 39/39 was escalated to a person instead of released (the second tasks-api run to do so after L tasks-api 2); and the release read a unit report a builder had overwritten with `--collect-only`, so it claimed the product had no unit tests.

**How others do it:** CI systems own their test reports - an agent's ad-hoc run writes elsewhere, and the gate measures fresh; release gates (e.g. merge queues) ship on the required checks and file the rest as follow-ups rather than blocking a green build.

**Built (value):** LF.670 - an empty unit report is measured again by the harness before it becomes a release gap. Next: find why a fully green locked suite still escalates (what stayed open) and settle it at release with the gaps listed.

## L notes-api-falcon 6 and 7 (2026-11-07: 0/9 and 9/9)

**To improve:** the two runs differed at setup. Falcon 6's setup stage wrote the whole product before design's builders ran, and a reused measurement skipped the start check, so a bare `python3` start shipped (0/9). Falcon 7's setup stayed in scope; its builders kept the proven async app and the product shipped 9/9 in under two hours.

**How others do it:** repository-setup agents (Repo2Run, MEnvAgent) run a generator and patch only what is missing, and a CI gate re-runs the start on every candidate rather than trusting a cached result.

**Built (value):** LF.672-673 (setup proof by smoke tests; proven code without scratch files), LF.676 (a reused measurement still runs the product's own start). Next: SF.2b (the harness runs the generator) so the setup cannot write the product.

## L notes-api-falcon 8 and 9 (2026-11-07: 9/9, 9/9)

**To improve:** falcon 9 spent about 20 minutes on a milestone send-back for a bug found by reading the code (a `KeyError` on a malformed stored record) that no test showed, and its testing work order, refused product writes for that fix, re-read the same lines six times. Planning replies ran past their cap because reply salvage could not keep the model's reasoning closed on a pinned server.

**How others do it:** review gates in CI (SonarQube, Copilot review) block on a failing check and leave reasoned findings as comments; a reviewer's finding becomes a test first, then a fix.

**Built (value):** LF.683 - the reasoning tag is read from the server the run is pinned to, so salvage can hold the reasoning closed. Next: G3 behind a switch - a milestone finding sends a sprint back only with a failing test, check or probe, and a code-reading finding becomes a test for the right role.

## Run review: L wordstats-cli 1 (run-885a8285), 2026-11-08

Hidden 8/8, locked 15/0, 62 active minutes (resumed after a 19-hour host fault), handoff 0.714, mutation 0.455. The first product released with today's handoff and release fixes.

| What to improve | What the run showed | How others do it | Value |
| --- | --- | --- | --- |
| A command-line tool's README | The README said how to install and test, never how to use the tool, and told the reader the tests needed it running in another terminal | CLI READMEs open with usage examples (clig.dev guidelines) | Fixed as LF.739: a "Using it" section from the contract's own commands |
| Mutation strength | 0.455 against a 5-run mean of 0.839; `+ 1` made `- 1` in analyzer.py survived every test | Mutation-guided test generation (Meta's ACH) writes a test per survivor | Measured switch Q.6b (survivors to QA) is queued in the measurement register |
| Contract checks for CLIs | 6 command lines of the contract were not checked at release: `python -m wordstats` is refused by the sandbox's allow-list | A CLI harness runs the declared entry point directly | Worth a fix: check command lines through the project's own interpreter path; to file |
| Design churn | Two design findings left open by an escalation, one settled by DR-8 | One design review plus deterministic gates (D.3, queued as a switch) | Measured with D.3 |

## Run review: L tasks-api 6 (run-ed4e910f), 2026-11-08

Hidden 10/10, quality 7/7, locked 33/0, handoff 0.75. The first service released with today's handoff and release fixes; one round of tests passed with 0 defects and no fixer ran.

| What to improve | What the run showed | How others do it | Value |
| --- | --- | --- | --- |
| Data the product wrote | `tasks.db` shipped beside the code: the product ignored DATA\_DIR, which its milestone review recorded as a risk, not a fix | Release builds from a clean checkout so run-time files never ship | Fixed as LF.740: databases the run wrote are removed, again after the release's re-measure |
| A risk the review recorded instead of fixing | "Database path ignores DATA\_DIR" was marked blocking yet shipped as a risk in fast delivery | Reviews that block only on evidence (M7, behind its switch) | M7's on arm will show whether evidence-gated findings get fixed instead |
| Thinking aloud in shipped tests | `# Actually, in SQLite, if you insert NULL...` in tests/test\_db.py | A lint pass before handoff (PR.6, queued as a switch) | Found by the handoff score; PR.6 measures a fix |
| Suite disputes | 3 locked tests reclassified under dispute | Dispute rulings by standard id (Q.5) | Q.5 needs a model-up build; queued |

## Run reviews: L web-todo 6 (run-daab28e9) and L notes-api-hono 3 (run-9a18d077), 2026-11-08

web-todo 6: hidden 10/10, locked 18/0, handoff 0.857, mutation 0. notes-api-hono 3: hidden 9/9, locked 11/0, handoff 0.857, mutation 0.5; its design escalated after the second review (DR-6), as the other runs' did.

| What to improve | What the run showed | How others do it | Value |
| --- | --- | --- | --- |
| A page that runs code its entry file does not hold | web-todo's page ran its program inline; the 410-line `src/main.js` was loaded by nothing, fixes went into it, and all 12 mutations of it went unnoticed | One entry per page, enforced by the bundler's module graph | Fixed as LF.742: named to builders, fixers and the release |
| False contract warnings on page controls | 7 "does not keep its interface contract" warnings for controls that appear once a task exists; 13 runs carried it, 12 scored 1.0 | Browser checks that set up state before looking (Playwright fixtures) | Fixed as LF.741: named unchecked when the criterion's own tests passed |
| Design points left open at an escalation (hono) | 3 design findings left open, including a deferred feature the brief requires | One design review plus deterministic gates (D.3) | Measured with D.3 |
| Handoff check misses | hono's start runs a program that reads PORT; the check looked only in `start.sh` | - | Fixed as LF.743 |

## Run reviews: L notes-api 5 (run-4b3287dd) and L notes-api-falcon 10 (run-bec09178), 2026-11-09

notes-api 5: hidden 9/9, handoff 1.0, mutation 0.333, 7 defects left open. falcon 10 (no stack pack): hidden 9/9, handoff 1.0, locked 27/0; its setup stayed within its four framework files and proved at the second attempt.

| What to improve | What the run showed | How others do it | Value |
| --- | --- | --- | --- |
| A proven custom setup kept for the next run | Proven, then not kept: its smoke tests import the layer's own package marker, which the entry did not carry | Devcontainer features keep the whole layer with the setup | Fixed as LF.745 |
| Suite writers going after the product | 14 refused writes to `main.py` on a reopened suite; the refusal said the product is built later | Role-scoped tool permissions with a reason that says what to do | Fixed as LF.748; refusals fell to 1 after the deploy |
| False "deferred, unproven" warnings | 4 criteria marked unproven whose tests passed at release; 29 runs carried such lines on a green suite | Report what the final run proves, not what an earlier one did | Fixed as LF.749 |
| Mutation strength on notes-api | 0.333; two `routes.py` changes went unnoticed | Survivors to QA (Q.6b, a switch) | Measured with Q.6b |

## fullstack-bookmarks-py 9 (run-1e6f6436-5f8c-4eb9-8e00-8cd87eeabcd1) and wordstats-cli 2 (run-3f858a3b-236a-493e-aeeb-5176285571a4), scored 11-09 05:05 JST

**fullstack-bookmarks-py 9:** 8/8 hidden, handoff 1.0. The release closed with 26 defects still open. The re-measure blamed clean-ups for failures that were already failing, which LF.750 fixes: only tests that passed before now count against a clean-up.

**wordstats-cli 2:** 8/8 hidden, handoff 0.833. The LF.739 README section "Using it" worked: it listed the product's command lines, and the configuration check was skipped because the product has no settings. The handoff point it lost was a thinking-aloud comment in the code.

**Feature to improve:** comments that think aloud. 2 of the 8 products with a handoff score shipped one (tasks-api and wordstats-cli). Other harnesses (Aider's lint step, SWE-agent's edit linting) clean comments in a final pass after the code is written. Here, the release clean-up could flag comments that read like reasoning ("wait", "actually", "let me") and have the builder rewrite them. Added value: a cleaner handoff on about one product in four, at no cost in hidden score.

**Fixes that fired:** LF.739 (the README), LF.748 (refused suite writes fell from 14 to 1) and LF.750 (now live).

## web-todo 7 (run-e5a3faea-ab9c-4a11-88d0-940f58a7f2c3), scored 11-09 06:30 JST

**Result:** 10/10 hidden tests, handoff 0.857, locked suite 18/18. It ran on 760ae09a: LF.751 to LF.754 could not be deployed into it, because Docker Desktop's compose call hung on two deploys.

**The handoff point it lost:** the README does not name the product's configuration.

**Feature to improve:** the interface contract's page lines. 11 of this run's contract lines were never checked, because they "follow none of the contract's three forms", and 87 of 274 scored runs carry such lines. The model names a real element but not in the exact form: a file after the path (`page / index.html textbox "Title"`), an attribute after the name (`type="text"`), or the element instead of its role (`input` for `textbox`). Other harnesses that let a model write checks (spec-driven test generators, schema-first API tools) normalise what the model wrote against the known vocabulary rather than reject the whole line. Added value: page checks at release on about a third of runs that now have none. A lenient parse must accept only known roles, so that a CSS selector is never read as a role.

**Design:** escalated after the 2nd architecture review, with three major findings left open. That makes 6 of the last 7 runs, and is the reason D.3 and D.7 are next to measure.

**Fixes that fired:** `SETTLE_SPEC_CONTRADICTIONS` acted, AY.1 localised 5 defects, every draft was accepted at the first pass, and no reply was lost to the output cap.

## textkit-lib 1 (run-169d7c18-946b-4629-b77b-ee994c238422), scored 11-09 07:06 JST

**Result:** 8/8 hidden tests, handoff 0.833, locked suite 9/9, in 22 minutes, on 760ae09a. It escalated after its 2nd architecture review: 7 of the last 8 runs have.

**The handoff point it lost:** the README says how to install and test the library, never how to use it.

**Feature to improve:** all 7 of its contract lines were command lines that say what they print (`-> stdout 'hello-world' exit 0`), a form the contract did not have. So none was checked at release, and the README's "Using it" section (LF.739), which is built from the contract's command lines, had nothing to show. LF.756 reads that form and checks the printed text. CLI-testing tools (bats, cram, the trycmd/snapbox style of snapshot test) all pair a command with its expected output, so this matches how such checks are normally written. Added value: release-time checks and usage examples for every library and command-line product.

**Watch:** a mutation score of 0.417, against a 5-run mean of 0.8. The sprint had no fix round left for the surviving mutants: two of them changed a single boolean, and no test noticed.

## notes-api-hono 4 (run-40245e5a-b379-474e-a421-367094706e6b), scored 11-09 07:56 JST

**Result:** 9/9 hidden tests, handoff 0.875, locked suite 11/11, on 760ae09a. It escalated after its 2nd architecture review: 8 of the last 9 runs have.

**The handoff point it lost:** the README names no setting. 4 of the last 11 handoffs missed this point, for two causes:

- specifications wrote their settings in prose (`- Environment Variable: PORT (number) - ... Default: 3000.`), which the README writer did not read;
- the scorer counted "Environment Variable: None" as a setting, failing a static page that reads none.

LF.759 fixes both. The same lesson as for the contract lines: the writer should read the forms models actually produce, not one exact syntax.

**Watch:** mutation score 0.286, against a 5-run mean of 0.633, the second low score in a row after textkit-lib 1 (0.417). One mutant changed `&&` to `||` in `storage.ts`, and no locked test noticed. I'm watching whether the mutation-to-test path (the sprint's spare fix rounds) is being squeezed out by the fix rounds before it.

## notes-api 6 (run-26daea11-0c30-4f17-99b9-29ef34419e28), and tasks-api 7 (run-5814234a-99dc-44f1-ae3b-bba743ac92f5), scored 11-09 09:06 and 08:05 JST

**notes-api 6:** 9/9 hidden tests, handoff 1.0, locked suite 10/10. It ran mixed: it started on 760ae09a, and LF.751 to LF.760 reached it at 08:31 and LF.762 at 08:51. It is the first release with a full handoff since the README fixes. It lost a sprint to a false interface clash: a test's module docstring still mentioned a removed name, so the clash check held the defect open. LF.762 fixes that check.

**tasks-api 7:** the run failed, yet its product scored 10/10 hidden tests and held 7/7 brief edges. The product's own root `conftest.py` skipped a locked test, and the suite writer, which may write only inside `acceptance/`, could not take the hook out. After five rounds, the run failed as "proves nothing". So the product never released: no README, no CI file, handoff 0.375. A fixer had also added an unauthenticated `POST /__reset__` that wipes all data, for the tests' clean-up. Three fixes came from this run:

- LF.757: builders, fixers and the architect are told the product ships every route it has.
- LF.758: the Python packs run the suite with `--confcutdir=acceptance`, so a product `conftest.py` cannot touch the locked suite.
- LF.760: a suite repair that runs out of rounds keeps the last locked suite and goes on to release with a gap, instead of failing the run.

**Feature to improve (filed, low priority):** contract write lines that succeed only with a body are never checked at release. That is 160 lines over 104 runs. The example bodies the specification gives could be sent. But this gap preceded a lost hidden test in 13% of runs, against a 20% base rate, so it ranks below the other open items.

## wordstats-cli 3 (run-55a58483-b0a8-4cc4-86c9-57f54de33380) and fullstack-bookmarks-py 10 (run-57a4b355-9a99-4d4c-afa7-e5e73d90173e), scored 11-09 09:40 JST

**Results:** both scored 8/8 hidden tests with handoff 1.0. With notes-api 6, that is three full-handoff releases in a row since the README fixes (LF.739, LF.751, LF.759).

**wordstats-cli 3:** LF.756 read every command line of the contract, but none ran: each was `python -m wordstats ...`, refused by the sandbox as arbitrary code. LF.763 lets `python -m` run the workspace's own module, and is deployed. It escalated after its 2nd architecture review: that makes 10 of the last 12 runs.

**fullstack-bookmarks-py 10:** locked suite 31/31, no escalation. It ships 10 of its own unit tests failing, and no code, milestone or security review ran, because the sprint was accepted at an escalation (DR-11). The second point is a quality gap worth watching. A sprint accepted at an escalation skips every review that reads the code, so a release can go out with no code review at all. Other harnesses (SWE-agent's review loop, Aider's lint and test step) always run at least one code-reading pass before shipping.

**Closed as noise:** the "mutation score regression" warnings. Over 14 runs the score ranges from 0.0 to 1.0 (mean about 0.54), on only 5 to 12 mutants each, so one or two survivors swing it. It is not a trend.

## tasks-api 8 (run-16b93e3a-0ceb-41a4-b721-3c2ea147e4bf) and M9 on wordstats-cli 4 (run-4c98359a-2354-4cf7-bb3b-52e504cd63da), scored 11-09 11:00 and 11:33 JST

**tasks-api 8:** 10/10 hidden tests, 7/7 brief edges, handoff 1.0, locked suite 38/38. This is the family that failed last night. This time no product file skipped a locked test and no test-only route was added, so LF.757, LF.758 and LF.760 held.

**wordstats-cli 4: 6/8 hidden tests, a false acceptance.** The brief says "Words are compared in lower case". The product counted case-insensitively but printed each word as first seen ("The 3"), while the hidden tests expect "the 3". The suite never pinned down the printed case, so it passed 20/20. The brief says *compared*, not *printed*, so this is an ambiguity that neither the architect's design review nor the suite writers resolved. It's the first such loss, so I'm noting it rather than building a fix yet. If it recurs, the fix is a review question: "for each rule about how values are compared, does the output show the compared form?" That is the kind of brief-ambiguity check spec-first harnesses do before building.

**Measurement:** this run was meant as M9's first on arm, but the switch never reached the model, because no judgement model is configured. That's fixed in LF.768, and the run is void as an arm.

**Contract command lines:** LF.763 worked, and the lines ran at release for the first time. But 5 were reported as broken, because their expected output held placeholders (`words: <n>`) or descriptions (`"words": n`, "same as AC-6"). LF.769 reads placeholders as any value and reports described output as unchecked, not broken.

## Afternoon of 11-09: the M9 pairs, falcon 11 and the wrong-test loop (scored up to 20:05 JST)

**Runs:**

- M9 on wordstats-cli 6 (run-aaf136ca-bc9a-4994-90bc-3e91175b39ae): 7/8 hidden, a false acceptance (the JSON shape of `--top`).
- M9 on wordstats-cli 8 (run-19fb2b9f-36c6-48f2-9103-d3933643f9ec): 8/8.
- M9 off wordstats-cli 9 (run-bbbf1e3d-e8a2-4b95-9444-a10c66700051): 8/8.
- M9 off wordstats-cli 7 (run-023f2c45-ce40-41f5-a0f6-da04679b0bd0): 8/8, but 358 active minutes.
- L notes-api-falcon 11 (run-6fbbf838-6b3e-482f-9f8c-4d5367c89ff0): 9/9.

All released with handoff 1.0.

**The costly failure of the day:** suite writers counted characters by hand (24 for a 23- or 25-character string). The products counted right, and fixers "fixed" them for hours. Four harness faults stacked up:

- tests typed their numbers: fixed by LF.772, so counts are now computed (`len(text)`);
- right dispute rulings were refused for paraphrasing: fixed by LF.771 and LF.776 (switched), so the test's own criterion is quoted;
- a fixed test past the reclassification cap was re-planned against: fixed by LF.778, so it is carried to release;
- the M9 review missed it, with or without reasoning, so it was not the switch.

Other harnesses avoid this class by deriving expected values from the input, as property-based testing does, rather than by hand.

**Built today beyond fixes:** sampling by mode (LF.774 and LF.775). It derives three modes from the model card for any model, can be set in a settings panel, and is on for Qwen3.6 on both ports with identical values since 17:37. Also the generated per-switch register (LF.767), with "no signal" for the 51 switches whose firing cannot be read.

**M9 so far:** 1 false acceptance in 2 on arms, 0 in 2 off arms. It stays off, and pair 3 is running.

## 2026-11-10: L web-todo 8 (7/10) and L fullstack-bookmarks-py 11 (8/8)

The web-todo loss came from two faults the harness saw but did not enforce: filter controls shown as "All (0)" where the brief names "All", and an "Add task" control disabled until a title is typed.

- **Feature to improve:** an open page-check defect at release does not block it. The disabled-control defect was raised every round, its fix reverted twice (it broke the product's own empty-title message), and the run shipped with it open.
- **How other harnesses do it:** none checks a page's accessible names against the brief; Copilot and Devin rely on the user's CI, which would not catch this either.
- **Added value:** LF.792 makes the renamed control a defect every round, so the fixer sees it in round 1 instead of the customer finding it. Next: decide whether an open page-check defect blocks release, and measure LF.792 on L web-todo 9.

## 2026-11-10: L web-todo 9 (10/10)

The same family that lost 3 hidden tests last run passed all 10: the product named its filters exactly as the brief does, and the suite asked for them by those names.

- **Feature to improve:** the README named no setting because the specification wrote its port as `PORT (default: 3000).` and the README writer did not read that form; fixed as LF.797. The accessibility defect was still left open after a re-plan; LF.795 now gives its fixer the files.
- **How other harnesses do it:** Copilot and Devin leave the README to the agent; none checks it names the product's settings.
- **Added value:** a stranger can start the product on the right port from the README alone.

## 2026-11-10: L wordstats-cli 14, L notes-api-hono 3, L fullstack-bookmarks 4 (all full)

Three more families scored full with handoff 1.0, including wordstats-cli, where the brief's casing rule had been overridden twice before.

- **Feature to improve:** fullstack-bookmarks 4's own suite passed 86% while the hidden tests passed 100%: the product was better than its suite measured, so a fix round chased tests that the brief does not need. Worth checking which visible tests failed and why.
- **How other harnesses do it:** none keeps a locked suite separate from hidden checks; their agents run the repository's own tests.
- **Added value:** four of four learning runs since the brief-wording fixes (LF.796-800) scored full, against four false acceptances in the 30 runs before.

### L fullstack-bookmarks-py 13 (run-9d2bf366), 2026-11-11: 8/8, handoff 1.0

- **What went well:** one sprint attempt. The page's accessibility defect was fixed on the first try, and the AC-17 refusal case was fixed in its second round. All 11 drafted files were accepted at the first pass, and the release probes ran (6 of 6 server-error checks).
- **Features to improve:** (1) The release reported a false contract break (`DELETE /api/bookmarks/1 -> 204` asked of a product holding no record 1). Fixed as LF.818. (2) Four review notes were left open at the lock on tests that check less than their criterion: AC-2 ordering read from the API, not the page; AC-4 and AC-10 filtering; AC-9's link text. The product passed the hidden tests anyway, but these are the shape of a missed regression. (3) The design review took two rounds again, with 98% of its output spent on reasoning.
- **How other harnesses do it:** contract-test tools (Schemathesis, Dredd) treat example values in a path as instances of a templated route and create fixtures first. LF.818 brings the release probe in line with that.
- **Added value:** the release's own report is now trustworthy for numbered records, so an owner reading the gaps sees no false alarm on a product that is right.

### L tasks-api 10 (run-63db1e89), 2026-11-11: 10/10, quality 7/7, handoff 1.0

- **What went well:** two sprints. The milestone review caught a real defect (a database connection leak) and sent it back; the fixer found a real sign-in defect (a second sign-in deleted the account's earlier tokens). Mutation-guided tests added real unit tests, and two later findings were closed without a fixer because those tests already caught them (LF.823).
- **Features to improve:** (1) Two mutation changes were still unnoticed by the locked suite at release (`==` made `!=` at line 79, `or` made `and` at line 147): the product passed every hidden test, but those two behaviours have no test holding them. (2) Two interface-contract lines (response body shapes for AC-8 and AC-21) followed none of the contract's three forms, so nothing could check them at release; the contract has no form for a body's shape. (3) The design review escalated again after two rounds.
- **How other harnesses do it:** contract tools (OpenAPI with schema validation, Pact) state a response body's shape as a schema and check it on every call; a body-shape line form for the interface contract would let the release probe check what AC-8 and AC-21 say.
- **Added value:** a gate family ran end to end at full marks on today's fixes, including the new mutation and reasoning-cost changes, with no harness defect left open.

### L fullstack-bookmarks 5 (run-b7b8ae49), 2026-11-11: 8/8, handoff 1.0

- **What went well:** the product was right on every hidden test. The QA lead's dispute caught three unpassable locked tests across two attempts, each with the right reason.
- **Features to improve:** (1) The suite writer wrote two kinds of unpassable test, each twice in the run: a text locator (`getByText('Gone')`, `getByText('First')`) matching both a link and a tag, and a test assuming the shared service starts empty. The writer is told both rules; the dispute is what catches them, at the cost of re-plans. (2) Because the sprint closed at an escalation, no code, milestone or security review ran, and AC-2 and AC-8 ship deferred with no passing test behind them. (3) Strict-mode locator failures are measured in 3 of the last 40 runs: rare enough that the dispute stays the net for now.
- **How other harnesses do it:** Playwright's own guidance is role-based locators with `exact: true` or a test id for anything a test checks once; a lint over the suite (e.g. eslint-plugin-playwright's rules) flags loose text locators before a run.
- **Added value:** the product shipped right; the release report says plainly which two criteria no test proves, rather than calling them verified.

### L textkit-lib 4 (run-db55fd26) 8/8 and L web-todo 11 (run-45cef9f4) 10/10, 2026-11-11

- **What went well:** textkit-lib built and passed in one sprint after its design escalation. web-todo got to a right product on the 4-bit build after three sprint-1 attempts; the dispute correctly kept the filter tests (fair), and the reasoning caps cut its per-attempt cost from 2-7 minutes to under one.
- **Features to improve:** (1) The design escalation in textkit-lib, bookmarks 5 and tasks-api 10 was caused by the harness's own deferral check, not the reviewer: fixed as LF.830 and LF.831. (2) web-todo's page check and a test pulled the same element opposite ways for ten rounds, because the rewrite path never saw the other fix: fixed as LF.832. (3) web-todo's KPIs regressed (16 replies lost to the cap against a mean of 3.8; identical-call rate 5.4% against 0.4%): the 4-bit build's struggle with one front-end bug. A higher-bit build on :1234 remains the owner's open action.
- **How other harnesses do it:** SWE-agent and OpenHands keep a run-level memory of what was already changed and why; our fixes-to-keep section is that memory, and it now reaches every path that writes code.
- **Added value:** fewer false escalations means more sprints get their code, milestone and security reviews.

### L notes-api 7 (run-6ee6e730), 2026-11-11: 9/9, handoff 1.0

- **What went well:** the product passed every hidden test and its locked suite (22/0). Once tests-only mode was off, the fixer fixed the real bug it had diagnosed but been forbidden to touch (a helper returning three values to callers expecting two).
- **Features to improve:** (1) Two unit tests ship failing, and the sprint closed at an escalation, so no code review ran. (2) Two source files (207 lines, `database.py`, `routes.py`) are imported by nothing the product runs: the build left a parallel structure behind. (3) The design review blocked on setup-owned files it was never told about (fixed as LF.833).
- **How other harnesses do it:** coding agents that run a dead-code or import-graph pass before review (e.g. vulture for Python) catch unused modules at build time rather than at release.
- **Added value:** the release report names the dead code and the failing unit tests plainly; nothing is hidden behind the green suite.

### L web-todo-react 1 (run-7a727629), 2026-11-11: 10/10, handoff 1.0

- **What went well:** the first learning run of the React family. One fix round: of 10 defects, 2 fixes resolved all of them and 8 closed without a fixer; milestone review accepted. On the 4-bit build, with the thinking-off cap and the fixes-to-keep for rewrites in place from the start.
- **Features to improve:** (1) The design review was approved and then overturned by the workflow's own check on five unreadable interface-contract lines (`page text "..."` with no path, `page viewport ...`); the measured `HARNESS_FINDINGS_RECHECKED` switch targets exactly this. (2) Its mutation score was 0.6 (one earlier run of the family scored 0.917): too few runs to call.
- **How other harnesses do it:** UI test generators that write a typed locator per element (role, name, path) avoid free-form contract lines; the contract's three forms are that, and the architect still writes lines outside them.
- **Added value:** a new stack family reached full marks on its first learning run.

### L notes-api-js 1 (run-6d1c3399), 2026-11-11: 9/9, handoff 1.0

- **What went well:** the first learning run of the Node notes API reached full marks with one sprint; one test round raised a single mutation finding, and the retention check correctly removed two test files that proved nothing.
- **Features to improve:** (1) The design review escalated on real contradictions inside the specification, and the revision added a new one; LF.836 now revises sections one finding names together. (2) Five suite-review notes were left open at the lock: four ask for the exact error body (`{"error": ...}`), a fair gap; one asks for an exact list length, which on a shared service would make the test unpassable - rare (6 of 736 open notes across all runs), so no filter is built.
- **How other harnesses do it:** contract tests that assert the error body by schema (a JSON shape check per status) close the error-body gap without hand-written assertions.
- **Added value:** the release names each weaker test plainly, so a person knows which behaviours rest on the hidden suite alone.

### L wordstats-cli 17 (run-2b67f0be), 2026-11-11: 8/8, handoff 1.0

- **What went well:** one sprint, two defects (a unit test and a mutation finding), both fixed first time; locked suite 14/0. The design revision settled the blocking finding and three of four major ones - the first run of revising together the sections one finding names (LF.836).
- **Features to improve:** (1) The intake stage spent 12 minutes writing a tool call's closing tags over and over: intake replies are now capped (LF.837). (2) The one finding the revision missed named the decisions section as "ADR-06": fixed as LF.838. (3) The identical-call rate was 8% (3 of 37 calls), a small sample.
- **How other harnesses do it:** inference servers offer repetition guards (llama.cpp's DRY sampler, repetition penalties) that stop a looping reply at the source; a per-stage token budget is the harness-side guard that works on any server.
- **Added value:** a command-line family at full marks with the design review settling most of its own findings in one revision.

### L notes-api-falcon 11 (run-6ff5ddd0), 2026-11-11: 9/9, handoff 1.0

- **What went well:** a stack with no pack (a "proven setup" chosen after design) reached full marks; 6 of 13 defects closed without a fixer once the product started.
- **Features to improve:** (1) Five fixes were reverted: the setup serves a package (`notes_api/main.py`) while the specification, written before the setup existed, put `app.py` and `storage.py` at the project root, and fixers kept importing `notes_api.storage`. Measured in 3 of the last 80 runs, so watched rather than built. (2) The design review escalated on a contradiction between two sections revised in separate calls, fixed as LF.836. (3) KPI regressions: 5 fixes reverted against a mean of 0, one reply lost to the cap.
- **How other harnesses do it:** agents that scaffold first and plan into the scaffold (e.g. project templates in Copier or cookiecutter, then planning) avoid a plan that disagrees with the layout it lands in.
- **Added value:** a framework without a stack pack still ships a right product.

### L web-todo 12 (run-b3e4f96b), 2026-11-11: 10/10, handoff 1.0

- **What went well:** the same brief and the same 4-bit build as web-todo 11, nine hours later. Sprint 1 cleared in two fix rounds (about 45 minutes) instead of three attempts over most of the day: 9 of 15 defects closed without a fixer, the empty-state defect was fixed first time with no ping-pong (LF.828, LF.832), and no fix stage salvaged more than two replies (LF.819-829). Locked suite 23/0.
- **Features to improve:** (1) The design review still escalated, on real contradictions in the specification and an interface line in no checkable form. (2) Three defects were left open after round 1 and closed in round 2; the round count, not the harness, set the pace.
- **How other harnesses do it:** per-attempt budgets and memory of earlier fixes (what we now give every path that writes code) are what agent benchmarks credit for stable repair loops; today's pair is a direct measure of it.
- **Added value:** a run that cost most of a day this morning now costs under two hours on the same model.

### L tasks-api 11 (run-c6b5bce1), 2026-11-11: 10/10, quality 7/7, handoff 1.0

- **What went well:** the gate family at full marks again, over two sprints, with a 38-test locked suite. The revert guard caught two fixes that broke what worked (93 and 36 tests). A mutation finding was closed without a fixer by a test an earlier fix wrote (LF.823).
- **Features to improve:** (1) Ten of the project's own unit tests ship failing beside a green acceptance suite; sprint 2 ended with only unit tests red and a fix that broke 36 of them. That is the shape `TESTS_ONLY_WRITES` was built for; it was taken off for cost this afternoon, so unit-test outcomes are watched against it. (2) Mutation score 0.27 against a mean of 0.72, and 39% of reads repeated: the testing specialist repeated identical searches (fixed as LF.839).
- **How other harnesses do it:** some keep the suite the product is judged by apart from the developer tests and repair the latter in a separate, tests-only pass (our measured `UNIT_TESTS_REPAIR_PASS` design), rather than restricting the first fix.
- **Added value:** the release names all ten failing unit tests, so a maintainer knows what to fix first.

### L fullstack-bookmarks 6 (run-a94d704a), 2026-11-11: 8/8, handoff 1.0

- **What went well:** one sprint on the 4-bit build, all 10 drafted files accepted at the first pass, and a contrast defect fixed by using the specification's own design token rather than dimming. Locked suite 11/0.
- **Features to improve:** (1) Ten unit tests ship failing - the third run in a row since tests-only first fixes were switched off. Measured across the day (0 of 9 runs with it on, 3 of 8 with it off), so it is back on (LF.840). (2) Mutation score 0.25 against a mean of 0.61: an 11-test locked suite misses most deliberate changes. (3) The design review escalated after two rounds.
- **How other harnesses do it:** a harness that keeps its own tests green beside the judged suite, rather than letting a fixer rewrite the product to satisfy a unit test, is the pattern tests-only first fixes enforce.
- **Added value:** today's switch experiment was measured and reversed within six hours, on numbers, not opinion.

### L notes-api-hono 6 (run-f8d4e2af), 2026-11-11: 9/9, handoff 1.0

- **What went well:** design passed on the second review with no escalation - the first time today a revision settled every finding. One sprint: real validation fixes (non-object JSON bodies now answer "invalid JSON body"), and a mutation finding correctly closed as equivalent. No unit test ships failing.
- **Features to improve:** (1) A 10-test locked suite is the smallest today; the hidden suite passed, but fewer tests mean fewer behaviours held. (2) Three fix rounds for a small API.
- **How other harnesses do it:** a suite-size floor per criterion count (at least one test per criterion, plus one per error case the contract names) is a common acceptance-suite heuristic; worth measuring before adopting.
- **Added value:** the design-review fixes made today show up as a clean first pass on a small API.

### L fullstack-bookmarks-py 14 (run-2f129659) 8/8 and L web-todo-react 2 (run-d239b5da) 10/10, 2026-11-11

- **What went well:** both survived a host GPU fault mid-run and resumed in place with no loss. bookmarks-py fixed a real defect (FastAPI served Vite's index page but not its built assets) and shipped with every unit test green - tests-only first fixes back on. web-todo-react's unstable test (passing alone, failing in the whole suite) was recognised as the test's fault and repaired rather than fixed in the product.
- **Features to improve:** (1) web-todo-react 2 shipped with one locked test red (title editing) after every attempt on the 4-bit build; the hidden suite passed, so the locked test asked for more than the hidden one. (2) Mutation scores 0.25 and 0.5, below their means: small locked suites. (3) bookmarks-py escalated at design on real findings the revision only partly settled.
- **How other harnesses do it:** flaky-test quarantine (run alone vs in the suite, then isolate) is standard in large CI systems; ours does it inside the run, before a fixer is sent.
- **Added value:** a crash of the host's desktop cost minutes, not runs.

### L textkit-lib 5 (run-0c7ac86e) 7/8 and L textkit-lib 6 (run-98fafcd0) 8/8, 2026-11-11

- **What went wrong in 5:** the brief said `title_case` keeps "the whitespace exactly as it was"; the specification and product split words on spaces only, all 48 locked tests used spaces, and the hidden test with a tab failed - a false acceptance. Its README also lacked any usage: the architect left the interface contract empty (2 of the last 60 specifications).
- **What changed:** LF.842 tells the suite writer and its reviewer that a criterion about a kind of input (whitespace, punctuation, separators, digits) is tested with more than one member of it. Run 6 on the same brief wrote tab cases for `title_case` and `word_count` and reached 8/8, locked suite 61/0.
- **Features to improve:** run 6's interface contract lines are descriptions, not commands (`AC-2 command slugify conversion -> exit 0`), so none could be checked at release; such lines precede a lost hidden test in 12% of runs, near the base rate, so watched.
- **How other harnesses do it:** property-based and equivalence-class testing (e.g. Hypothesis strategies over a whole character class) is the standard answer to a test that only ever tries one member of a class.
- **Added value:** a false acceptance traced to its root, fixed in general, and re-checked on the same brief within an hour.

### L wordstats-cli 18 (run-e5f4f9c4), 2026-11-11: 7/8, handoff 1.0 - false acceptance

- **What went wrong:** the brief says `--top N` prints the top words *instead* of the counts, and with `--json` prints only `{"top": [...]}`. The specification gave `--top N --json` that output and `--json --top N` the counts as well - two results for one command, by option order alone. The design review passed it, the suite tested both lines, the product printed the counts, and the hidden test failed. The morning's Measure batch lost the same test (wordstats-cli 15a); LF.807 had moved the architect toward the brief's "instead" in one line but not the other.
- **What changed:** LF.843 compares every command line in the specification; the same arguments in another order with another result is a major finding at design review, so the revision must pick one result - the brief's - and the settle call rules on it if it survives.
- **Features to improve:** mutation score 0.167 on a 13-test suite, and the first run on the new IQ4\_NL build: more runs on it are needed before comparing ports.
- **How other harnesses do it:** CLI test generators that derive cases from a parser specification (argparse, click) test option permutations as one behaviour; a contract that names a command once per behaviour avoids the trap entirely.
- **Added value:** the one recurring false acceptance of the day now has a mechanical check upstream of the suite.

**L notes-api-js 2 (run-274d1ea0), 9/9, 12 Nov 00:37 JST.** *Improve:* the release left 6 interface-contract lines unchecked because the probe made no record to read back (`GET /notes/:id`, a write with a body) - a probe that creates its own record through the contract's write line first would check them. The design escalated on a library version the architect invented (`express v3.0.1`) - the same invented-detail pattern LF.590 addressed for limits. *How others do it:* contract-testing tools (Schemathesis, Dredd) chain a create before each read of an id. *Added value:* a third suite-level rule (LF.845) now ties a mode's output to the brief's whole form, closing the gap behind three wordstats false acceptances.

**L notes-api 8 (run-96a84970), 9/9, 12 Nov 01:30 JST.** *Improve:* the acceptance suite caught 0 of 2 mutants (the unit tests caught both) and 32% of reads were repeats - the suite proves the brief's behaviour but not the code's edges. *How others do it:* mutation-guided test generation (e.g. Meta's ACH) writes a test per surviving mutant. *Added value:* the run was green at its first test round, with no fix round - the cleanest notes-api run of the day, and the first design pass without failed reads of starter files (LF.844).

**L wordstats-cli 19 (run-787a3f4c), 8/8, 12 Nov 02:17 JST.** *Improve:* it took four harness fixes (LF.843-847) and three rewinds to close one gap - a mode whose output replaces another's. Two prompt rules did not move the suite; the deterministic check did on its first case. The milestone review still spends a round on locked-suite quality it cannot act on; it is now recorded as a gap. *How others do it:* spec-conformance checkers (OpenAPI response validators, JSON Schema `additionalProperties: false`) hold an output to its whole declared form rather than to the presence of a key. *Added value:* the wordstats family's one recurring hidden-test loss (three runs) is now caught before the build, by reading the brief's literal outputs.

**L tasks-api 12 (run-3a8d00f4), 10/10, 12 Nov 03:04 JST.** *Improve:* the plan for sprint 2 went out unready after three attempts - the lead was told only that it had 4 decisions for 8 carried items, never which ones (LF.848 now lists them). The first fixer of a mutation finding ended at its call budget with nothing to show. *How others do it:* planning agents (e.g. SWE-agent's issue triage, Devin's plan checklist) keep carried work as a numbered checklist the next plan must tick or decline item by item. *Added value:* a two-sprint authenticated API went from brief to 44 locked tests and a full hidden score in \~90 minutes with 2.5% tool failures.

**L fullstack-bookmarks 7 (run-75511fa9), 8/8, 12 Nov 04:29 JST.** *Improve:* it was accepted at an escalation with "no review read the product's code" among its gaps, a gap that preceded a lost hidden test in 16% of runs; two of its locked tests were wrong and found only by a dispute after a fix round. *How others do it:* test-generation pipelines (e.g. Meta's TestGen-LLM) run each new test against a reference build before accepting it, which would have caught the two wrong tests before the lock. *Added value:* the harness's own suite checks sent the first suite back with seven concrete problems (shared-list counts, a tag locator, an unnamed control, an untested filtered view) - all fixed before any product code ran.

**L wordstats-cli 20 (run-d2c01d2d), 8/8, 12 Nov 04:47 JST.** *Improve:* the suite's own helper lost a `+` and six tests could never pass; the reclassification cap let only two be repaired, so two criteria shipped deferred though the product met them - one broken helper should count as one repair (backlog). The 4-bit fixer re-sent identical edits many times. *How others do it:* mutation-testing tools validate a test oracle against a known-good build before trusting it; a helper computing expected values would be checked the same way. *Added value:* the JSON-with-`--top` gap that cost three earlier runs was caught by the harness unaided on its first suite draft.

**L notes-api-hono 7 (run-665859fa), 9/9, 12 Nov 05:57 JST.** *Improve:* a locked test held the product to an internal file name (`notes.json` must exist at start) rather than to observable behaviour; the dispute upheld it and a fixer bent the product to it - harmless here, but a test of storage internals ties a product to one design. Redundant reads 23% (5-run mean 13%). *How others do it:* black-box API test suites (e.g. Postman/Newman contract tests) test persistence by restarting and reading back through the API, never by inspecting files. *Added value:* the 4-bit model on :1234 delivered a TypeScript/Hono service to a full hidden score in \~60 minutes with 1.9% tool failures.

**L textkit-lib 7 (run-477755ed), 8/8, 12 Nov 06:36 JST.** *Improve:* the second prompt rule of the night (LF.842, "test a kind of input with more than one member") was ignored by the suite writer and reviewer alike; like LF.845 it needed a deterministic check (LF.852). Lesson for the harness: a quality rule a model must remember to apply is a candidate for a check that reads the test. Mutation score 0.667 against a 0.883 mean. *How others do it:* property-based testing (Hypothesis, fast-check) generates inputs from a whole character class instead of one hand-picked member. *Added value:* the textkit family's recurring false acceptance (tabs in `title_case`) is now caught before the build, not by a hidden test after release.

**L textkit-lib 8 (run-0d3a4fd3), 8/8, 12 Nov 07:35 JST.** *Improve:* the product passed every acceptance test early, then the run spent most of its 49 minutes on mutation findings and one re-planned sprint - mutation work on a 4-bit model is the costliest part of a small library run. *How others do it:* mutation tools (mutmut, Stryker) are usually run as a report with a threshold, not as a gate that loops fixers. *Added value:* the suite writer tested whitespace beyond the space without being told, and the whitespace check (LF.852) stood behind it in case it had not.

**L web-todo 13 (run-97f30e2b), 10/10, 12 Nov 07:49 JST.** *Improve:* the night's costliest run (\~2 h 55 min, 230 tool calls, 32 defects left open, 4 fixes reverted) on a product the hidden tests passed in full. At least one of its two failing locked tests was wrong: it deleted the record at the top of a newest-first list and expected the other to stay - a position the test never fixed. Fixers were sent after it for over an hour. *How others do it:* Playwright's own guidance is to locate by role and text, never by position; Testing Library's queries have no positional form at all. *Added value:* the escalation did its job - it deferred the unprovable criteria and released a right product rather than looping.

**RC15 notes-api 1 (run-76cc1045), 9/9, 12 Nov 08:45 JST.** *Improve:* clean - one fix round, no failed tool calls, 26 minutes from suite lock to release; repeated identical calls (3.5%) are its only flagged KPI. The lead's plan was sent back once for naming the data file in scope with no work order for it. *How others do it:* plan validators in agent frameworks (e.g. task-graph linting in CrewAI flows) check every named artifact has an owner before dispatch. *Added value:* a Flask notes service to a full hidden score in \~43 minutes on the 8888 model, through the frozen harness.

**RC15 tasks-api 1 (run-92c99813), 10/10, 12 Nov 10:13 JST.** *Improve:* one suite fault - a session fixture copied into a second test file with the same username - cascaded: 18 setup errors whose reason the finding cut off (LF.853), a dispute capped at 3 repairs that deferred two right criteria, then three rounds where the harness called a successful fixture repair "not changed" (LF.854). One shared cause was handled test by test throughout. Mutation score 0. *How others do it:* pytest's own model keeps shared fixtures in one conftest per directory; test-repair tools fix the shared fixture once and re-run every dependent. *Added value:* despite the cascade the product reached 33/33 locked, 10/10 hidden and 7/7 edge cases on the 4-bit model.

**RC16 fullstack-bookmarks-py 1 (run-dbf5babe), 8/8, 12 Nov 10:47 JST.** *Improve:* the harness's own page check misread a right product - it looked for list items only in markup, and the page set `role="listitem"` from its script - and the sprint was planned again three times with every locked test passing (LF.855). A deterministic check that disagrees with a green suite and the product's own code should be the first suspect. Mutation 0.25. *How others do it:* accessibility checkers (axe-core) read the rendered accessibility tree, not the source, so how a role was set never matters. *Added value:* the suite checks caught three real test faults before the lock (a filter for a value never sent, an untested filtered view).

**RC16 wordstats-cli 1 (run-855d2fe0), 8/8, 12 Nov 11:00 JST.** *Improve:* clean - 36 minutes, 1 failed tool call; only the prefill share (8.4 against 5.2) is high, the cost of long prompts on the 4-bit model. *How others do it:* prompt caching (llama.cpp's slot reuse, provider prompt caches) cuts the re-read of an unchanged prefix. *Added value:* the family that lost its JSON-with-top hidden test three times now passes it routinely - the suite check (LF.846) catches the weak test on the first draft.

**RC16 textkit-lib 1 (run-73d45df7), 8/8, 12 Nov 11:34 JST.** *Improve:* nothing material - 28 minutes, no failed tool calls, the product passed its first test round. Redundant reads 7% (5-run mean 5%). *How others do it:* small-library pipelines elsewhere usually stop at a unit-test pass; here the acceptance suite, the whitespace check and the release reviews all ran and still finished inside half an hour. *Added value:* the textkit family's tab-in-`title_case` gap, once a false acceptance, was caught on the first suite draft by LF.852 on the frozen code.

**RC16 notes-api-hono 1 (run-4ac89f9d), 9/9, 12 Nov 12:00 JST.** *Improve:* the milestone review blocked on SIGTERM/SIGINT handlers - a requirement the architect added (ADR-10) and the brief never asked for - costing a full extra drafting and review pass; the brief-over-spec review that would have caught it at design is off by default. Mutation 0.18 against 0.72. *How others do it:* spec-driven tools (e.g. GitHub Spec Kit) keep a scope check that flags requirements with no source in the brief before planning. *Added value:* a dispute rewrote a wrong health test and the suite relocked with nothing else changed - the targeted-repair path held.

**RC16 notes-api-js 1 (run-bc3eecd1), 9/9, 12 Nov 12:55 JST.** *Improve:* the QA lead flagged a test counting a shared list at round 3, but the suite locked at its limit anyway and was reopened after drafting once the harness's own check measured it (\~10 min). The same review also pushed a test from the brief's "400 or 422" to the spec's single 400 - harmless here, but it is the specification overriding the brief. *How others do it:* test isolation per test (fresh storage per test, as Playwright projects or pytest tmp dirs give) removes shared-list counting altogether. *Added value:* no KPI past 1.5x its mean - an unremarkable run on the 4-bit model, which is the goal.

**RC16 tasks-api 1 (run-f78ba2fa), 10/10, 12 Nov 14:27 JST.** *Improve:* 90 minutes and 17 fix stages for a two-sprint API whose suite reached 57/57; the prefill share hit 22.3 (mean 6.8) and identical calls 7.5% - the 4-bit model re-read long contexts on every fix stage. *How others do it:* agent harnesses (e.g. OpenHands' condenser) summarise older turns so each step sends a short context, and llama.cpp's slot reuse caches an unchanged prefix. *Added value:* every edge case the brief names held (7/7) and the hidden score was full on the 4-bit build.

**RC16 web-todo 1 (run-64bd1cd1), 10/10, 12 Nov 14:44 JST.** *Improve:* 2 h 38 for a single-page app the hidden tests passed in full: three locked edit tests held a record by its old title and sought the new one inside it - no product could pass them - and the fixers were sent first, about 20 fix stages before a dispute rewrote two and deferred one past the cap. Redundant reads 53%, 3 fixes reverted. *How others do it:* Playwright's guidance re-finds an element after an action that changes it; test-repair agents re-run a disputed test against a known-good build before blaming the product. *Added value:* the escalation released a right product rather than looping; LF.856 (built, held for the Fix batch) now names this exact test fault from its failure message.

**RC16 fullstack-bookmarks 1 (run-5bdf94b7), 8/8, 12 Nov 15:56 JST.** *Improve:* two locked page tests (filter by tag, the save-list-filter-delete flow) were wrong and found only after two fix rounds; the dispute rewrote both rightly and the suite went 17 -> 20/20. *How others do it:* a dry run of each new page test against a stub page before locking (the harness has `spec_dry_run` for some patterns) catches tests that cannot pass before any product exists. *Added value:* no failed tool calls and no KPI regression across 65 minutes of a full-stack build on the 8888 model.

**RC16 notes-api-falcon 1 (run-3c6f48ca), 9/9, 12 Nov 17:11 JST.** *Improve:* 2.5 hours and 13 defects left open: four locked tests failed through the suite's own unique-name prefix (the test sent `ac-<time>-Title` and expected `Title`) - one cause the cap counted as four - and the milestone review held the sprint for a malformed-record rule the architect adopted (DB-4) that the brief never asked for. Prefill share 14.6 against 7.2. *How others do it:* test-data factories (factory\_boy, faker) return the value they made, so a test compares against what it sent rather than a literal. *Added value:* a framework with no stack pack, set up by the agents themselves on the 4-bit model, still reached a full hidden score.

**RC16 web-todo-react 1 (run-6a6a14b7), 10/10, 12 Nov 18:03 JST.** *Improve:* 1 h 55: a dispute rewrote two locked tests and deferred a third past the cap, a fix that broke 10 passing tests was rightly reverted, and the milestone review held the release for the brief's 500-line cap - the page styled everything inline and left \~100 lines of unused CSS. *How others do it:* linters with unused-selector rules (stylelint, PurgeCSS) flag dead CSS mechanically; a line budget check at drafting would catch it before review. *Added value:* the brief's hard size limit was enforced at release, not left to chance - a stated constraint the hidden tests do not check.

**notes-api 1 (run-36555b59), 9/9, 12 Nov 18:20 JST.** *Improve:* clean - about an hour on the 4-bit model, no failed tool calls, one fix round; only the prefill share (6.9 against 4.4) is above its mean. *How others do it:* a simple CRUD service is where most harnesses stop; the value here is the release reviews running on it anyway. *Added value:* the last family of the sweep landed full, so every benchmark family has now scored full on today's harness.

**tasks-api 1 (run-6ff14cae), 10/10, 13 Nov 02:23 JST.** *Improve:* the milestone review held sprint 2 for token revocation at sign-in, a rule the architect added and the brief never asked for (the third such hold in a day); one reply was lost to its length limit. *How others do it:* scope traceability (each requirement linked to a line of the brief, as in requirements-management tools) lets a reviewer tell a brief requirement from an addition. *Added value:* two sprints, 20/20 locked, every edge case of the brief held (7/7) on the 4-bit model.

**RC18 wordstats-cli 1 (run-5ea7a3ba), 0/8 - false acceptance, 13 Nov 03:56 JST.** *Improve:* the product was right (19/19 locked) and the harness broke it at the last step: a release tidy-up deleted the pack's untouched `__main__.py`, judging by text that nothing imported it - Python runs it for `python -m`. The re-measure saw all 19 fail and still released, marked non-deliverable. A tidy-up should never be able to break a product: if the measurement after it fails, it is undone (LF.861). *How others do it:* release pipelines run the final artifact's smoke test as a gate, and tree-shakers keep entry points declared by the runtime, not only those referenced in code. **fullstack-bookmarks-py 1 (run-d87d7155), 8/8:** the dead-page round (LF.858-859) and five rightly deferred test faults; the product was right throughout once its script loaded.

**RC19 wordstats-cli 1 (run-60ea8418), 8/8, 13 Nov 05:12 JST.** *Improve:* clean - 54 minutes, no KPI past 1.5x, a single sprint. *How others do it:* most harnesses would stop at the green suite; the value here is that the release's own tidy-up is now measured and undone if it breaks anything. *Added value:* the same family that shipped dead an hour earlier (0/8) now ships whole - both regressions of the night, the weak JSON test and the release tidy-up, are caught by checks rather than by luck.

**RC19 textkit-lib 1 (run-ffadb8fc), 8/8, 13 Nov 05:44 JST.** *Improve:* tool failures 2.7% and a prefill share of 8.5 (mean 4.9) on the 4-bit model; otherwise a 28-minute run passing its first test round. *How others do it:* libraries this size are usually verified by unit tests alone; here a 31-test acceptance suite was written, checked and locked first. *Added value:* the whitespace check (LF.852) caught a spaces-only suite on its first draft, again - the gap behind textkit's one false acceptance stays closed.

**RC19 fullstack-bookmarks-py 1 (run-2af25177), 8/8, 13 Nov 06:25 JST.** *Improve:* 2 h 7: the page's own startup request answered 422 (a product bug the load check put on every criterion's defect), then the last two tests - rewritten by a dispute - kept failing while four fixes were reverted for breaking others, and the run escalated with both deferred; both behaviours were in fact right. *How others do it:* when fixes for two tests keep breaking each other, a human would look at whether the tests contradict each other before fixing the product again. *Added value:* the full-stack family scored full for the third run running on today's harness.

**RC19 notes-api-js 1 (run-d39df8f6), 9/9, 13 Nov 07:08 JST.** *Improve:* tool failures 12% (mean 7%) on the 4-bit model; a dispute called three tests wrong, including one holding notes to exactly the brief's three fields - arguably right by the brief, harmless here since the hidden tests check only that the fields are present. *How others do it:* contract-first API tools (OpenAPI with `additionalProperties`) decide up front whether extra fields are allowed, so neither the suite nor a dispute has to guess. *Added value:* an Express notes service to a full hidden score in 83 minutes.

**RC19 web-todo 1 (run-b13b7ac7), 10/10, 13 Nov 08:30 JST.** *Improve:* a dispute rewrote the last failing test with `hasText: /^Filter test active$/`, which can only match a list item whose whole text is its title; the fixer then removed the visible words from the Edit and Delete buttons (keeping their accessible names) so the test would pass. The hidden score held, but the product got worse to satisfy a faulty test - the cannot-pass check LF.862 names it the test's fault instead. *How others do it:* Playwright's docs recommend `getByText` or `hasText` with a plain string (substring) for records, never a whole-text anchor on a container. *Added value:* 6 to 26 of 28 in one fix round.

**RC19 tasks-api 1 (run-fb10a44d), 10/10, 13 Nov 09:11 JST.** *Improve:* 1 h 54 and tool failures 7.5% (mean 3.8%) on the 4-bit model for a one-sprint authenticated API; 6 of 26 tests at the first round. *How others do it:* scaffolds that ship a working auth module (e.g. FastAPI's security templates) leave the agent only the domain routes. *Added value:* every edge the brief names held (7/7) and the gate family scored full again on the RC19 build.

**RC19 notes-api-hono 1 (run-003d543f), 9/9, 13 Nov 09:27 JST.** *Improve:* the suite locked with three of its own faults still open (a start-script test breaking on its own code, a test counting a shared list, a restart test on data it never wrote) and was reopened for six tests after the build; mutation 0.455 against 0.655. *How others do it:* a test suite is usually linted and dry-run before it becomes the gate; here the checks ran but the lock went ahead at its round limit. *Added value:* 30/30 at the first measurement after drafting and released in 48 minutes.

**RC19 notes-api 1 (run-d4d901f4), 9/9, 13 Nov 10:43 JST.** *Improve:* none material - 84 minutes, 33/33 at the first measurement after drafting, no KPI past its mean. *How others do it:* this is the shape a mature harness aims for on a small service: one design pass, one suite, one build, one release. *Added value:* it closes RC19 at 8 of 8 families full on one frozen build, the cleanest release-candidate round so far.

**RC19 fullstack-bookmarks 1 (run-0238dd0d), 8/8, 13 Nov 10:58 JST.** *Improve:* a correct fix for a no-body 500 was split by the harness and its test kept without the test library it declared, costing two sprint attempts (fixed as LF.863); a reviewer note about acting inside a filtered view repeated three rounds without a test being added. *How others do it:* harnesses that revert part of a change usually revert by dependency unit (code plus the manifest it needs), not by file kind. *Added value:* the split now keeps what the kept tests need, so a right fix reaches the product a round sooner.

**RC21 wordstats-cli 1 (run-d9e4574c, mixed), 8/8, handoff 0.833, 13 Nov 12:05 JST.** *Improve:* the specification's interface contract came back empty (its commands were written under API and Event Contracts), so the README never said how to run the tool and no contract line was probed (fixed as LF.867: the section is asked for again); 2 unit tests shipped red over `--top 0` after the sprint was re-planned 3 times and escalated. *How others do it:* spec-first harnesses validate required sections before downstream stages consume them, re-asking just the empty one. *Added value:* every release now carries a contract its probes and README can use.

**RC20 web-todo-react 1 (run-ba1d9ae3, mixed), 10/10, handoff 1.0, 13 Nov 12:17 JST.** *Improve:* two pack faults cost most of its 1 h 29 - unit-test type errors failed the production build (LF.865) and Testing Library never cleaned up between tests (LF.866, 11 of 22 unit tests red on a right product); the rest was a hard-coded grey that failed contrast, reverted twice. *How others do it:* Vite's own React template splits the app and test type-check configs and starter kits enable vitest globals for Testing Library; packs should ship the conventions the ecosystem already settled. *Added value:* the next React run starts with both fixed, so its fixers work only on the product.

**RC25 textkit-lib 1 (run-cd7df61a, mixed), 7/8 - false acceptance, 13 Nov 12:55 JST.** *Improve:* the design escalation let a self-contradicting example into the suite, and the dispute that cleared it also called a right test wrong; its rewrite copied what the product returned (LF.870 now catches that shape; the judge's misjudgement itself is open, with LF.869 recording ruling reasons). *How others do it:* test-repair loops in other harnesses guard against "fixing the test to match the code" by requiring a rewritten assertion to be justified against the specification text, not the observed output. *Added value:* a reclassified test can no longer quietly lower the bar to the product's current behaviour for this whitespace case.

**RC25 web-todo-react 1 (run-29a32727, mixed), 10/10, handoff 1.0, 13 Nov 13:54 JST.** *Improve:* the remaining waste was 16 unit tests failing on missing page matchers (LF.872, for the next React run) and a CSS transition that made an opacity check read a mid-animation value; the suite still never toggled a record while a filter was on (the review note stood). *How others do it:* React starter kits ship jest-dom with vitest and turn off transitions under test; both are setup conventions, not product work. *Added value:* the first React run on today's pack fixes went green with a meaningful mutation score (0.875), where the last scored 0 on broken-build noise.

**RC28 textkit-lib 1 (run-e50a5dd9, mixed), 8/8, handoff 1.0, 13 Nov 14:01 JST.** *Improve:* the design escalated on a package path the harness itself described wrongly (LF.873), and two locked tests asserted a text and a length that disagree (LF.874 reopened them); after the re-plan the testing stage asked eight times to re-run tests that already passed. *How others do it:* test generators that emit both a literal and a derived property usually cross-check them before saving; here a static check does it at lock and round. *Added value:* the brief that gave the morning's false acceptance now completes clean, and a whole class of impossible tests is caught without a model's judgement.

**RC31 notes-api-js 1 (run-b7fd8303, learning), 9/9, handoff 1.0, 13 Nov 15:05 JST.** *Improve:* the design escalated on an adopted request-size limit the function contracts contradicted, and its contradiction rulings were both rejected for quotes not word for word (LF.875 now keeps the quotes); the drafted code imported a package it never declared, closed by one rewrite. *How others do it:* dependency-aware generators add the manifest line in the same edit as the import; here the language-service check catches it at the first round. *Added value:* 59 minutes from brief to a full score, with the bad-body probe catching and closing a 500 on its own.

**RC32 wordstats-cli 1 (run-bcdc6779), 8/8, handoff 1.0, 13 Nov 15:57 JST - the first release-candidate run on the frozen build.** *Improve:* one locked test miscounted its own input (17 for an 18-character text), caught by the dispute and corrected; the drafted unit tests named a relative file. *How others do it:* generators that compute expected values from the input in the test (len(text)) instead of writing the number avoid the arithmetic slip entirely. *Added value:* 40 minutes to a full score, with the README's usage and the contract's command lines in place since LF.867.

**RC32 textkit-lib 1 (run-f4f91943), 8/8, handoff 1.0, 13 Nov 16:27 JST.** *Improve:* the architect again wrote a self-contradicting `truncate` example (now settled for the criterion), and its unit tests shipped failing after the sprint escalated. *How others do it:* spec generators that derive examples by running a reference implementation of the stated rule avoid this class of slip; here the harness catches it at review. *Added value:* on the brief that gave this morning's false acceptance, two of today's checks (LF.874, LF.852) fixed the suite before it locked, and the run finished clean.

**RC32 notes-api 1 (run-9de81b4a), 8/9 - false acceptance, 13 Nov 17:16 JST.** *Improve:* the locked suite tested the empty-title refusal on create only, and the probe built to catch exactly that (empty each refused field on every write) skipped because it found request examples only in the contract sections, which held error shapes (fixed as LF.878). *How others do it:* contract-testing tools (schemathesis, dredd) generate request bodies from the schema rather than from prose examples, so a missing example never silences a check. *Added value:* the release now probes every write with the brief's refused-empty fields whenever the spec shows a request body anywhere.

**RC31 fullstack-bookmarks 1 (run-2b7e877e, learning), 8/8, handoff 1.0, 13 Nov 18:22 JST.** *Improve:* 4 h 27 for a right product: the API router was never mounted (one cause, 15 defects), then about 2 h of fixers on locked tests that fetched before opening the page, with no dispute held because no fixer named a file (LF.876 and LF.877 now catch both), then a milestone hold over adopted advice. *How others do it:* test-repair systems triage a failing test first (can it pass?) before assigning a code fixer; LF.877 moves this harness toward that order. *Added value:* the same fault in a future run is sent back to the suite writers at the lock, not to a dozen fixers.

**RC32 tasks-api 1 (run-87ab5937, learning), 10/10, quality 7/7, handoff 0.875, 13 Nov 18:54 JST.** *Improve:* the release shipped the suite's own test database (LF.880), and the probe meant to empty each refused field on every write asked nothing because the spec wrote its bodies as prose (LF.879) - the product happened to be right. *How others do it:* release pipelines build from an allow-list of the product's paths, so test artefacts cannot ship by name collision. *Added value:* two silent gaps in the release's own checks closed before they cost a hidden test.

**L notes-api 9 (run-abff4e03), 9/9, handoff 1.0, 13 Nov 20:11 JST.** *Improve:* the health route answered 500 on a fresh start before its data file existed (fixed in round 1); five tool calls were refused lookups. *How others do it:* contract-fuzzing tools derive every write's refused-field cases from the schema; this run shows the harness now does the same from the spec's own examples. *Added value:* the brief that shipped a false acceptance three hours earlier now has its blank-title refusal checked on every write before release.

**L web-todo 14 (run-f54fd703), 10/10, handoff 1.0, 13 Nov 20:21 JST.** *Improve:* a 25/25 sprint was planned again over one accessibility rule - the empty-state message sat inside the list - after a fix for it was reverted for breaking three locked tests (LF.881 now names the remedy: beside the list). *How others do it:* component libraries render an empty state as a sibling of the list by convention, so the accessibility rule and item counts never collide. *Added value:* the third run to hit this, and the last that should have to work it out.

## Run run-844673cd (notes-api-java, container mode, 2026-11-17)

**Result.** Hidden 0 of 9, quality 0 of 8, handoff 0.43, failed after its one sprint was re-planned 3 times (14:26-15:36 JST, :8888). The product's own code compiled, but a unit test named a class that did not exist (`NoteDao`), and `start.sh` built with `mvn -DskipTests package`, which still compiles the tests: the product never started for the acceptance suite or the scorer.

**What the run found.** It was the first Java run with each command in a container of its own (LR.30), and four harness defects surfaced, all now fixed and deployed:

- Maven fetches its JUnit provider at the first test, not at the install; tests run offline there, so run 1 died at its scaffold (LF.1017, a pack warm-up).
- The testing work order the harness writes put every test straight in `src/test/`, where Maven compiles nothing (LF.1020: a test mirrors its code's package; no test for `pom.xml`).
- A fixer changed the Spring Boot version; the reinstall stopped at a compile error before Maven reached its test plugin, and every later offline build failed on "Unknown host" (LF.1021: a toolchain that fetches while building has the network).
- The start compiled the tests (LF.1023: built with `-Dmaven.test.skip=true`).

**Features to improve.** (1) A product that starts should never be held hostage by its test files: every compiled-language pack should build the start without its tests, and a check could start the product from its main code alone before reporting "does not start". (2) The fixers drifted: in 70 minutes they moved from one compile error to imports of packages the project does not have (`org.springframework.jdbc`). A compile-error fix should be checked against the declared dependencies before it is kept. (3) The rule-coverage counter (LR.46) paid for itself: it named Maven, .NET and gotestsum totals as unread on their first runs.

**How others do it.** Hosted coding agents (Codex cloud, Devin) give the build its network and isolate by container rather than by cutting the network, and pre-warm dependency caches when the environment is set up; this run argues for the same split - offline only where the toolchain has no lazy fetch.

**Value to the user.** The container mode is what a hosted multi-tenant service needs. Each language's first run in it is a shakedown that costs one run and returns pack fixes that hold for every later product in that language.

**Next.** Java run 3 in container mode on the fixes; Go run 1 is live on :1234.

## Run run-666e030f (notes-api-go, container mode, 2026-11-17)

**Result.** Hidden 9 of 9, quality 8 of 8, handoff 1.0, verdict not\_deliverable (15:28-16:44 JST, :1234). The product is right; the verdict is the harness being honest about contract lines it could not check and design points the escalation left open.

**What the run found.** Three harness gaps, fixed and deployed into it: gotestsum's closing line was read by nothing (LF.1022); the Go packs never said the module path is `go.mod`'s, not the folder's, and the draft imported `notes-api/store` (LF.1024); a unit run held to the sandbox's time limit reached the fixers as "(no output)" (LF.1025). After it, the C# pack failed its scaffold check in container mode on a .NET passwd quirk (LF.1027).

**Features to improve.** (1) A pack should be scaffold-checked in the run's execution mode before its first run there, by the start command itself rather than by habit: a C# run was started on an unchecked pack and cancelled a minute later. (2) The verdict and the score disagree here (not\_deliverable with 9/9, 8/8): the release gate should say which open item it thinks costs the user something, so a reader can tell caution from a defect.

**How others do it.** Hosted agents (Codex cloud, Devin) build a per-repository environment image once and test it before a session starts, which is the same check as (1) done ahead of time.

**Value to the user.** Go now runs isolated per command with the same score it had unisolated: the container mode costs nothing in quality on this stack.

**Next.** C# in container mode on :1234 after LF.1027; Java run 3 live on :8888.

## Run run-e53e1441 (notes-api-java, container mode, 2026-11-17)

**Result.** Hidden 9 of 9, quality 7 of 8, handoff 1.0, delivered (16:12-17:50 JST, :8888): the first Java run to deliver in container mode, on the four Java fixes of the afternoon (LF.1017, LF.1020, LF.1021, LF.1023) plus the totals read from Surefire's reports (LF.1026).

**What worked.** Tests landed under `src/test/java` and ran (29 unit tests, all passing); the product built without its tests; a green round set off the probes, and two found what the locked suite could not: a body-less `POST` answered 500 (fixed), and ten creates sent at once were not all kept.

**What it shows.** The one quality test lost is that second finding: `test_notes_written_at_once_are_all_kept_with_their_own_ids`. CONCURRENT\_WRITE\_PROBE named the defect an hour before the scorer did, and three fix rounds could not close it, so the sprint re-planned twice on it. The probe is right and costs no hidden test; what it lacks is a fix the model can make.

**Features to improve.** (1) A lost-write finding should come with the pack's own way of serialising writes (a lock around the store in Java, Go and C#; a transaction where there is a database), as a short note in the defect, since the model's fixes went round the symptom. (2) The fixers called tools the stage had withheld 6 times and used `NAME=value` prefixes 3 times; the refusal text already says why, so the cost is the model's - a smaller tool list per fix stage would save those calls.

**How others do it.** Property-based and concurrency checks (Hypothesis stateful tests, Go's race detector, jcstress) find these defects mechanically; agent harnesses rarely run them. The probe is the cheap version, and its finding matches the quality test exactly.

**Value to the user.** A user gets an API that passes every hidden test and is told, before release, which concurrency defect remains.

**Next.** Rust in container mode on :8888; C# live on :1234.

## Run run-760be6cb-36d5-45f2-98ea-9a67c2133de8 (Rust notes API, container mode, 11-17 17:56-19:36 JST)

**Result:** failed. Hidden 0/9, quality 0/8, handoff 0.43. Four sprint attempts, 8 fixes reverted, 15 defects left open.

**What went wrong.** The specification fixed the entry as `build_router() -> Router<AppState>`, a router still waiting for its state, which `axum::serve` cannot run. Every later stage built to it: the technical lead re-planned to it twice and added a dependency that could not help, and the fixers patched around it. Only the builders had the Rust pack's guide, which says a plain `Router`.

**Features to improve, and what was built:**

- *Design facts from the stack reach design.* A pack can now state facts the specification must respect (LF.1035). Next: when the same compiler error survives two attempts and names a type the specification fixed, offer a specification revision instead of a re-plan.
- *Revert accounting.* Eight fixes were reverted as "it broke the install" while nothing had built before any of them: compiled stacks build the code during install. A fix is now blamed only when the install worked where it started (LF.1036). Lesson: every regression check must compare against a baseline that was actually green.
- *Call caps across attempts.* The fixer reached attempt 4 already past its 60-call cap and did nothing; the run escalated. Right when nothing changes, but a new attempt with a new plan could get a small fresh allowance.
- *Measurement.* Container-mode mutation scores were never recorded: the probe copied the workspace where the sandbox could not mount it (LF.1037).

**How other harnesses handle it (from what I know, not fresh research):** SWE-agent-style harnesses run a lint or compile check after each edit and reject only edits that add new errors relative to the file before the edit, never relative to an absolute bar. Aider runs lint and tests after each change and hands the errors back, rather than reverting. OpenHands-style agents keep edits and let the agent see the build output. Our revert-on-regression is stricter and better at protecting a green product, but it needs the baseline guard that LF.1036 adds.

**Where to add value:** a per-language "framework shape" check at specification review (entry function, test harness imports), run by the language service against a scratch file, would catch this class of error before any code is written.

## Run run-c7a00abc-1f89-4d22-a153-2341b48c4641 (Rust notes API, container mode, 11-17 19:54-21:32 JST)

**Result:** hidden 9/9, quality 8/8, handoff 1.0; the run's own verdict not deliverable (AC-18 deferred, one unit test file not compiling). Run 1 on the same brief scored 0/9 two hours earlier.

**What changed it:** the design stages were told the entry's shape (LF.1035); no fix was thrown away for an install that was already failing (LF.1036: 0 reverts against 8); and four of the Rust pack's known compiler errors were given their cause in the defect itself (LF.1038-1041). The handler-order error was open for two attempts and closed in the first round after its cause was attached.

**Features to improve:**

- *Known errors are the cheapest lever for compiled stacks.* Each one is a phrase and a sentence of cause in the pack, and each closed a loop that cost a whole sprint attempt. Next: harvest them - when a compiler error survives two fix rounds, record its phrase and the fix that finally closed it as a candidate known error for review.
- *Build output is not source.* The release checks and the mutation probe read cargo's `target/doc` (LF.1042, fixed in the shared walker).
- *The design gate's contradiction matcher is noisy.* 43 "says opposite things" findings over the last 4 runs, mostly false: a denial about one endpoint ("DELETE: no response body") is paired with every other endpoint's body. Next: scope a denial to the names it is about.
- *A unit test file that does not compile ships.* The locked acceptance suite passed while `tests/crud_test.rs` did not compile; the verdict said so, but nothing went back to fix it.

**How other harnesses handle it (from what I know):** compiler-driven agents (Aider's lint-and-fix loop, SWE-agent's edit linting) feed the raw compiler error back each turn; few add curated causes. Language servers and rustc's own `help:` lines are the usual source of hints. Our known-error table plays the role of the `help:` line the compiler does not give for framework misuse (axum's extractor order, its state typing).

**Where to add value:** a per-framework known-error pack, grown from measured runs, is a moat: it turns each failed run into a permanent fix for every later run on that stack.

## Run run-2a42b19c-205a-4bd5-812c-0028762cc920 (C# notes API, container mode, 11-17 21:46-23:12 JST)

**Result:** hidden 9/9, quality 8/8, handoff 1.0, delivered - the first C# container run to deliver. Mutation 4/12 caught.

**What happened:** attempt 1 never built. A fixer wrote the program's C# into `App.csproj`; nothing had passed before, so the fix counted as breaking nothing and stood. The technical lead's re-plan drafted it again and it went green: 12/12 acceptance, then three unit tests sharing one in-memory host fixed by running them in sequence.

**Features to improve:**

- *Structural sanity of every write, not only of tests.* A manifest that no longer parses in its own format is now a revert (LF.1045). The same idea extends to any file with a checkable format the product depends on (a JSON settings file, a YAML workflow).
- *The design gate still escalates every run* on case-split denials ("is not a positive integer -> 404"). LF.1044 caps the noise at one point per denial; a denial stated as a condition should not count at all, once a rule can be found that keeps the real contradictions the tests hold.
- *A weak locked suite passes a delivered product.* 4 of 12 changes caught is the lowest of tonight's runs; the surviving changes flip a stored flag and a branch in `DataStore.cs`. Mutation-guided tests (QM.2) could be pointed at the survivors before release.

**How other harnesses handle it (from what I know):** most coding agents do not check a manifest's format separately; they rely on the next build to fail. Ours does too, but a revert keyed to a failing build only works when the build passed before - which, on a run that has not compiled yet, it never did.

**Where to add value:** a per-run "what ships" check that the delivered product's own test project builds - the handoff counts a unit test file that does not compile as a gap, but no stage is sent back to fix it.

## Run run-e8e3120f-5d67-4b47-9037-e4745c898148 (PHP notes API, container mode, 11-17 21:52-23:50 JST)

**Result:** hidden 9/9, quality 8/8, handoff 1.0, delivered; mutation 7/12 (0.583).

**What went well:** one fix closed seven defects. The JSON-parsing middleware tried to parse every request body, GET included; once it was fixed, the round's measurement found six other defects already passing and closed them without a fixer each. Mutation-guided testing then raised a change no test noticed (`||` made `&&`) and the testing role closed it.

**Features to improve:**

- *The architect's documentation lookups.* Five `read_docs` calls for "Slim" found nothing, and three guessed documentation URLs answered 404 - 8 of its 10 calls. A framework name could resolve to its registry package (`slim/slim`) and its README.
- *Re-reads within a stage.* Fixers and reviewers read the same few files three times each (8.3% identical calls against 0.5% on the last run).

**Where to add value:** a run where one root cause shows as many failing criteria is common; the harness already closes the rest by measurement, which is worth stating in the handoff as "one cause, seven criteria" so a reader sees the shape of the problem rather than seven separate fixes.

## Run run-c7b0d7ec-4406-41fe-af2f-74259ee63996 (Ruby notes API, container mode, 11-17 23:19 - 11-18 00:52 JST)

**Result:** hidden 9/9, quality 7/8, handoff 0.875; not deliverable. Mutation 6/12.

**What went wrong:** lost writes, through three sprint attempts. The store lived in a Sinatra helper (`@store ||= NotesStore.new`), and Sinatra makes a new app object per request, so every request read the file afresh. Once LF.1048 gave the defect that cause, the fixer built a shared store and a class-wide lock in `NotesStore` - but the helper every route calls still made a new store per request. The run's own probe sent 10 writes at once and passed in the last round; the hidden quality test sent 16 and got one id for all of them. The handoff lost a point for comments that think aloud.

**Features to improve:**

- *A probe as strong as the judge.* The concurrent-write probe now sends 16 at once, as the hidden test does (LF.1050); 20 dropped connections on Python's standard server, whose queue holds 5, which would raise a false defect.
- *A cause that names every place.* A known cause that says "keep one store" was followed in the store and not in the route helper; causes now name the helper too. The wider lesson: a cause should say where the fix must reach, not only what it is.
- *Lost writes recur across families* (Java run 3, this run): every service guide says so since LF.1030, but each framework hides the per-request object differently - Sinatra's app object, a Spring prototype bean, an Express handler closure.

**How other harnesses handle it (from what I know):** few agent harnesses test concurrency at all; property-based and load probes are the usual tools in human teams (k6, Locust, Hypothesis stateful tests). A concurrent probe with a fixed count is a cheap version; the count has to match the judge's or it passes what the judge fails.

**Where to add value:** a short per-framework "one process, one store" fact in each service pack - where the framework creates objects per request - would prevent the bug at drafting instead of finding it at the probe.

## Run run-b770f08f-2b04-42c9-9172-1c330717b0d9 (Java notes API, container mode, 11-17 23:56 - 11-18 01:40 JST)

**Result:** hidden 9/9, quality 7/8, handoff 1.0, delivered with cuts. Mutation 7/8 changes caught by tests that do not all fail at once.

**What went wrong:** about an hour - two sprint attempts - on a product that could not start for a reason no fixer could see. The sandbox mounts each container's `/tmp` as `noexec`; a JVM writes its temporary files there, not to `TMPDIR`; SQLite's JDBC driver unpacks its native library there and could not load it (`NativeDB._open_utf8`). The defect showed the end of the start output, which cut off just before the cause. Once fixed (LF.1051) the product started and the suite went to 9/10. The quality test lost was a non-numeric id answered 500 by a catch-all exception handler - the same test Java run 1 lost; the harness's own probe for it ran only at fully green rounds, and this sprint was accepted near green (LF.1052).

**Features to improve:**

- *Environment parity per runtime.* Each language's runtime has its own idea of where temporary files, caches and native libraries go (the JVM's `java.io.tmpdir`, .NET's diagnostic sockets, cargo's registry). The sandbox should state each of them, checked by a scaffold that loads one native library per stack.
- *A start failure shows its cause, not its tail.* A Spring start log puts the cause in the middle; the defect kept the end. The defect could keep the line that names the exception as well as the end.
- *Probes at the point of acceptance.* Any check that only runs at a green round is skipped by a sprint accepted near green; LF.1052 moves one of them. The rest (the order probe) should follow when measured.

**How other harnesses handle it (from what I know):** sandboxed agent runtimes (OpenHands, E2B) usually give a writable, executable `/tmp`; the hardening here is stricter and so has to restore what a runtime expects explicitly.

**Where to add value:** a nightly "native library" scaffold per stack - SQLite opened once in each language's container - would catch an environment gap like this before any run pays for it.

## Run run-1cef3eae-17ed-4e38-a8ae-8e97812fe352 (tasks-api sentinel, container mode, 11-18 03:39-05:50 JST)

**Result:** hidden 10/10, quality 7/7, handoff 1.0. The run's own verdict: not deliverable - one locked test reclassified under dispute, two code changes no test noticed. Mutation 3 of 12 caught (0.1).

**What went well:** one rewrite of `app.py` took the suite from four defects to 36 of 37 passing; a dispute settled the last test; the mutation-guided step then raised two changes no test noticed and the testing role added tests for them.

**Features to improve:**

- *The locked suite's strength.* Tonight's mutation scores range from 0.0 to 0.67 across ten runs; this one is the weakest. The hidden tests pass anyway, so the product is right - but a weak suite is what lets a later change break it unnoticed. Mutation-guided tests fire after green rounds only; pointing them at the survivors earlier, while the suite is being written, would raise the floor.
- *Fixers rebuilding the environment.* One fixer spent about six minutes recreating the virtualenv and reinstalling requirements, which the harness already does. Seen in 3 of the last 25 runs, 1-3 calls each: noted, not yet worth a rule.

**Where to add value:** the run's own verdict was stricter than the hidden score - the harness refused to call a product with a weak suite deliverable. That is the right default for a launch: report it to the user as "works, but its tests would not catch a regression", with the two lines named.

## Run run-1badaa8f-b4cc-425a-a27a-aa0146b7fbbd (Rust notes API, container mode, 11-18 06:00-07:22 JST)

**Result:** hidden 8/9, quality 6/8, handoff 1.0, mutation 12/12; not deliverable. Lost: an update (the criterion still failing when the sprint was accepted near green), a blank title kept, a long body refused.

**What held:** the design fixes from run 1 - `app()` returning a plain `Router` with its state applied inside - held on a fresh run with no help. The locked suite was the strongest of the night (every one of 12 changes caught).

**What it found:** a re-check bug that hid fixes - a compiler finding that had merged other reports stayed "still reported" after it was fixed, because any other error in the same file counted (LF.1055, seen in two Rust runs); and one more axum trap, a router used after `oneshot` took it (LF.1056).

**A measured switch broke its own rule:** `NEAR_GREEN_REPLANNED_ONCE` accepted the sprint near green twice, and the hidden test lost was the criterion left open. By its rule (measuring.md M14) it goes off; the change is ready and waits on the owner, since it touches `docker-compose.yml`.

**Features to improve:**

- *Near green is not green.* Two of the night's three lost hidden tests (Java 4's 500 on a non-numeric id, this run's update) came from criteria open when a sprint was accepted near green. The probes now run at near-green rounds (LF.1052); the acceptance itself should name what it leaves open in the handoff, criterion by criterion.
- *Framework defaults the brief does not mention.* A long body refused by axum's default body limit is the kind of default each pack could state once (the limit, and how a service raises it).

**Where to add value:** a per-stack list of framework defaults that bite (body limits, per-request objects, catch-all exception handlers) is the same kind of knowledge as the known-error tables, and could be written into each pack's design facts before the first line of code.

## Runs of 11-18 morning: Java 5, Go 2 delivered; Rust 4 and 5 failed

**Results:** notes-api-java container 5 (run-14e254a1) and notes-api-go container 2 (run-4886c02b) each 9/9 hidden, 8/8 quality, handoff 1.0, delivered. notes-api-rust container 4 (run-db139a37) and 5 (run-1e04154a) each 0/9.

**What the Rust failures had in common:** one framework mistake in four shapes across five runs - a router still waiting for its state (`Router<AppState>`, `Router<Extension<AppState>>`), and in run 5, the right signature with handlers reading the state through `Extension` while `app()` applied it with `.with_state`, so every route answered 500 at runtime. Each fix tonight closed one shape: causes attached to compiler errors (LF.1038-1063), the declaration held at every round (LF.1064), and now the product's own words for a route-wide 500 (LF.1067 - checked live on run 5's product: "Missing request extension: Extension of type `AppState` was not found").

**Features to improve:**

- *Show the product's answer, not the test's verdict.* Playwright failures carry "Expected 201 / Received 500" and nothing else; the body usually names the cause. LF.1067 brings one body to a route-wide 5xx; a further step is to attach the body to every status mismatch the suite reports.
- *One cause, one fixer.* LF.1066 found that the harness had never grouped Playwright status failures into one cause - nine fixers chased one 500. A pattern worth auditing for every runner's output format, not only the ones measured.
- *Escalations on every design.* Twelve of twelve runs since yesterday evening escalated their design on case-split "contradictions". LF.1044 cut the noise to one point per denial; the escalation is still a fixed cost of about two minutes a run.

**How other harnesses handle it (from what I know):** HTTP-level agents that see the raw response (curl in a shell) get the body for free; harnesses that test through a framework's test client lose it unless the assertion prints it. The lesson here is general: every check's failure should carry the evidence a human would look at first.

**Where to add value:** a per-stack "framework mistakes" table is now the single biggest lever for compiled stacks - Rust's has thirteen entries tonight. Publishing it with the pack, and growing it from every failed run, compounds.

## notes-api-csharp container 3 (run-e8053d6e, 18 Nov 13:49-16:44 JST)

Result: hidden 9/9, quality 8/8, handoff 1.0, mutation 0.67, delivered at an escalation.

**Features to improve.** The product was right long before the harness said so. Four sprint attempts and 34 defects left open came from the harness's own unit tests and a broken start the fixers kept re-introducing, not from the product's behaviour. Three things would have ended it in about an hour: a gate that proves the product builds and starts before per-defect fixers are sent; a fixer that keeps its best working state instead of handing over its last broken edit; and a batch revert that removes only the fixer that broke the build.

**How other harnesses do it.** Factory and Anthropic's long-running harness keep the builder and the evaluator apart and feed back only grouped causes; OpenHands and Agentless choose among candidate patches from a checkpoint by test results and never commit a regression; Aider and v0 repair compile errors with targeted edits and deterministic fixers before any whole-file regeneration.

**Added value if built.** These are deep-review items A1-A3, B3/B4 and 1.5, now in wave 1 (bundle 1) and wave 2. Measured by: share of fix attempts that close a defect (about 30% today), share of runs that re-plan (48%), and false reds such as this one.

## notes-api-php container 2 and notes-api-rust container 6 (18 Nov, both 0/9)

Result: both failed with products that never started for long; hidden 0/9 and quality 0/8 each.

**Features to improve.** Both runs lost to a framework API the model remembers wrongly: Slim methods that do not exist, and an axum test client and state type that do not exist. Each mistake was found only by a test round 5-15 minutes later, and per-defect fixers kept writing new code on a product that would not start. The fixes now deployed attack each link: a golden example on the pinned version shown to builders and fixers; the stages writing the specification told how unit tests call the app; PHPStan for Slim so the compile check names an invented method at the write; rewrites kept only when the compiler reports fewer errors; and one start fix before any per-criterion fixer.

**How other harnesses do it.** v0 injects version-specific knowledge and curated examples and rewrites imports from real exports; Aider and v0 repair with targeted edits and deterministic fixers; Cursor's apply model and the LSP-in-the-loop products check every edit before it lands.

**Added value if built.** Measured by the next two Rust and PHP runs on 532dba3: whether the product starts by the first test round, and how many rounds and reverts it takes. These two families are the clearest before-and-after for waves 1 and 2.

## notes-api-php container 3 (run-c5d6a8a5, 18 Nov 20:09-21:00 JST)

Result: hidden 9/9, quality 8/8, handoff 1.0, mutation 0.64, delivered, 44.8 active minutes, 0 reverts.

**Features to improve.** The build is now the easy part on this family; the design is the slow part. The design review escalated with about eight "the specification says opposite things" findings that were mostly not contradictions (shutdown, error handling, database queries), and the run carried them to release as notes. The typed contract in wave 3 (one record of routes, shapes and errors from which the document is rendered) removes their source. The second slow spot is the acceptance suite's authoring and review passes before any code.

**How other harnesses do it.** Spec-driven tools (Kiro, Spec Kit) keep requirements and design as separate short documents with each task traced to a requirement, rather than one long specification restating each fact; Anthropic's planner is told to specify what and why, not granular how.

**Added value if built.** The same family went from 0/9 in 5.2 hours to 9/9 in 45 minutes on one change of version; PHP container 4 confirms or refutes it on the same version. The next measurable gain is design time: from about half of this run's minutes toward a few.

## notes-api-rust container 7 (run-cbf36159, 18 Nov 20:09-22:35 JST)

Result: hidden 0/9, quality 0/8, failed after three sprint attempts, 134 active minutes.

**Features to improve.** The harness got past every infrastructure layer in this run - the design no longer planned a test client axum lacks, an offline build failure was no longer mistaken for the environment, a feature the crate lacks was answered with the real list, and a hand-written lock file was refused and regenerated. What remained was Rust code the local 35B model could not make compile within the rounds. A re-plan rewrote files and started over each time; wave 3's targeted re-plan and the harness-driven fixer aim at that, and the model itself is now the main variable.

**How other harnesses do it.** Aider's architect/editor split and the "smart friend" pattern route the hardest reasoning to a stronger model while a cheaper one edits; v0 repairs compile errors with deterministic fixers before any model round.

**Added value if built.** The Haiku arm (judgement stages and stuck-defect escalation on `claude-haiku-5-5`, building on the local model) measures directly how much of Rust's failure is the model: a first Rust run on it is the next step once the key is entered.

## notes-api-php container 4 (run-f00ea384, 18 Nov 21:05-23:24 JST)

Result: hidden 9/9, quality 8/8, handoff 1.0, mutation 0.3, 125 active minutes, 0 reverts; its own verdict: not deliverable.

**Features to improve.** Two. The verdict was a false red: the specification chose 400 for a malformed id and the product chose 404, which the brief allows; LF.1110 now notes that mismatch instead of blocking on it. And the locked suite is weak (mutation 0.3): two deliberate changes in the service went unnoticed, and the sprint had no round left to add tests for them. The generated edge probe and the unit-test filter address coverage from the harness's side; the acceptance author still writes mostly happy-path checks.

**How other harnesses do it.** Factory's validator writes the test instrument from the desired outcome before the build and keeps it hidden; property-based tools derive edge cases from the contract rather than from a writer's imagination.

**Added value if built.** PHP now delivers on both runs of the new version; the next gains here are a verdict that matches the hidden score (measured on the next runs) and a suite strong enough that mutation stops slipping through - the hidden evaluator in wave 3 is the main lever.

## notes-api-csharp container 4 (run-1b5b8d8e, 18 Nov 22:37 - 19 Nov 01:24 JST)

Result: hidden 0/9, quality 0/8, verdict delivered, locked suite 18/18 - a false acceptance.

**Features to improve.** The run's product only works inside the harness. Faced with offline package restores (a harness bug, fixed mid-run as LF.1111), a re-planned work order had the model write a `nuget.config` pointing at the sandbox's own package cache; every in-harness check then passed. Two lessons: the harness must never let product files depend on its internals (LF.1113), and every release needs one check that runs the product the way a user would, outside the sandbox - the scorer does this, the harness's release does not.

**How other harnesses do it.** Products built in ephemeral, clean environments (Copilot coding agent, Cursor cloud agents) are verified by CI on a fresh runner, so a dependency on the build machine fails before hand-off.

**Added value if built.** A clean-room start at release (copy the product out, install from the manifests, start it, ask one route) would have turned this delivered 0/9 into a red verdict; it belongs with the release probes in wave 3.

## tasks-api container 2 (run-58e79fce, finished 19 Nov \~02:30 JST)

Result: hidden 10/10, quality 7/7, handoff 1.0, mutation score 0.545, 143.7 active minutes, 2 fixes reverted - a working product the harness wrongly marked not\_deliverable.

**Features to improve.** The product is right; the harness's final judgement was not. Its release contract probe calls each documented line without signing in, so every line about a signed-in user came back 401 and counted as broken. LF.1116 now lists those lines as unchecked with the reason. The deeper gap: the edge probe also failed to sign in (all 22 checks skipped), so neither release probe exercised the signed-in half of the API. Mutation 0.545 says the generated tests catch only about half of injected faults.

**How other harnesses do it.** Contract-testing tools (Schemathesis, Dredd, Postman collections) take an auth hook once - a login step whose token every later call carries - instead of probing each line bare. Test generators such as Meta's TestGen-LLM keep a generated test only if it raises coverage or kills a mutant.

**Added value if built.** (1) One shared sign-in step for both release probes, driven by the API's own sign-up and sign-in lines, so signed-in lines are really checked rather than listed unchecked. (2) Surface surviving mutants to the testing specialist as concrete missing assertions; a rise from 0.55 toward 0.8 is a measurable quality KPI.

## notes-api-rust hybrid Haiku 1 (run-160e0f62, 19 Nov 01:25 - 02:54 JST)

Result: hidden 9/9, quality 7/8, 88 active minutes, 3 fixes reverted, hosted spend $0.87 (146 Haiku calls) - the first full Rust score on this version, where three local-only Rust runs scored 0/9.

**Features to improve.** Two things. The product accepts a note whose title is only spaces (the release probe caught it; the one quality test lost). And the sprint spent four attempts on one defect: the entry declaration was restored in `lib.rs` while `main.rs` still called it with an argument, so every fix stopped the build and was reverted - LF.1118 now names the caller in the defect. With that fixed, the same run would likely have finished well inside an hour.

**How other harnesses do it.** Coding agents that edit across files (Aider's repo map, SWE-agent's search tools, Claude Code's own grep-first habit) find a symbol's call sites before changing its signature; refactoring tools (rust-analyzer, IDE 'change signature') change declaration and callers as one edit. A frontier reviewer on the judgement path is how hybrid systems such as Devin and Factory keep cost low: the cheap model writes, the stronger one plans and judges.

**Added value if built.** (1) A whitespace-only check in the emptied-field probe for every required text field, raised before release rather than at it. (2) The hybrid arm costs under $1 a run against a $30 budget: run Rust and C# again on it to see whether the judgement tier is what lifts the hard languages, and price a hosted fixer for escalated defects next.

## web-todo container 1 (run-3cc0ed29, 19 Nov 02:37 - 05:10 JST)

Result: hidden 10/10, quality 6/6, delivered, handoff 1.0, mutation 1.0, 129 active minutes, no reverts.

**Features to improve.** The first draft wired the form handler to an id the page did not have (`add-task-form` against `<form id="add-form">`), so nothing could be added and 40 of 46 tests failed; the harness had a check for exactly this but graded it a hint (LF.1121 now makes it a proven defect). Then the per-defect re-measure ran the same eight browser files 53 times on an unchanged product (LF.1122). About 30 of the 129 minutes went to these two.

**How other harnesses do it.** Front-end agents (v0, Bolt, Lovable) render the page in a browser after each generation and read console errors and dead handlers directly, rather than inferring from tests; test runners such as Jest and Vitest cache per-file results keyed by file content.

**Added value if built.** A single browser load of the page right after drafting, reporting unbound handlers and console errors to the drafting fixers, would catch this class within a minute instead of a full suite round.

## notes-api-csharp hybrid Haiku 1 (run-04f2aa30, 19 Nov 03:19 - 05:10 JST)

Result: hidden 9/9, quality 8/8, delivered, handoff 1.0, mutation 0.8, 101 active minutes, $1.31 hosted - the first full C# score this harness has made.

**Features to improve.** Two harness bugs cost the first two sprint attempts: Haiku's replies (thinking plus text blocks) were written into five source files as their Python form (LF.1124), and the harness's own as-delivered start ran offline from an empty home, so .NET restored against an unreachable source and the product was reported as not starting in every round (LF.1125). The product itself was right once its files were real.

**How other harnesses do it.** SDK-based agents read a reply's text through the SDK's text accessor rather than the raw content, which is a list for every frontier provider; CI systems that check a clean start (GitHub Actions, Heroku buildpacks) restore with network first, then start.

**Added value if built.** A provider-conformance test pass - one short scripted run against each hosted provider before a measured run - would have caught LF.1114, LF.1115 and LF.1124 before they cost a run.

## notes-api-rust hybrid Haiku 2 (run-82f66a50, 19 Nov 05:15 - 08:52 JST)

Result: hidden 9/9, quality 7/8, delivered with cuts, handoff 0.857, mutation 1.0, 111 active minutes, $1.45 hosted.

**Features to improve.** The product accepts a note title made only of spaces (`is_empty()` without a trim) - the same gap Rust Haiku 1 shipped. The harness has a probe for exactly this, but it never ran: the architect wrote every contract line in a form the reader did not accept, so the contract was empty (LF.1127). Earlier in the run, the specification itself designed `app(store)` against the stack's `app()` - the cause behind every recent Rust failure, now caught at the design review (LF.1126).

**How other harnesses do it.** OpenAPI-first tools (Stoplight, FastAPI's schema, Schemathesis) make the contract machine-readable by construction - a schema, not prose lines - so there is no form to get wrong; property-based API testers generate blank and whitespace strings for every required string field by default.

**Added value if built.** Two candidates: (1) ask the architect for the contract as structured fields (method, path, statuses, note) rather than a line format the reader must parse - removes this class of loss entirely; (2) treat whitespace-only as empty in the emptied-field probe for every required text field, which now runs once the contract reads.

## tasks-api container 3 (run-af4108e6, 19 Nov 05:16 - 10:45 JST)

Result: hidden 10/10, quality 7/7, not deliverable, handoff 1.0, mutation 0.27, 315 active minutes, 4 reverts, 40 defects left open.

**Features to improve.** The product works for every hidden test but leaks a SQLite connection on every request (the dependency opens one and never closes it), so under the locked suite's longer sequence requests queue on "database is locked" and time out. Eleven fix attempts across two sprints never closed it; the harness showed the lock error in 8 of 25 fixer requests. Five of the run's hours went to this one defect.

**How other harnesses do it.** Framework-aware linters catch this class statically: FastAPI's own docs and tools such as Ruff's FastAPI rules and Semgrep's resource-leak rules flag a dependency that returns an unclosed resource instead of yielding it; Devin-style agents run a short load loop after a fix to see whether a hang reproduces.

**Added value if built.** A per-language resource-leak check in the stack packs (Python: a database or file opened in a request dependency without `yield`/`with`/close) raised as a proven defect pointing at the exact function would have named the cause on the first round. Second: when the same defect survives N attempts with the same evidence, end the sprint with the cut sooner - measured here at about four hours spent after the cause was clear.

## notes-api-csharp hybrid Haiku 2, judgement only (run-e68d3ce9, 19 Nov 09:10 - 10:51 JST)

Result: hidden 3/9, quality 4/8, failed after two re-plans stalled, 98 active minutes, $0.43 hosted.

**Features to improve.** The local build refused valid request bodies with 400 (24 tests across 11 criteria) and its API unit tests started the program without `PORT`, crashing the test host. The harness described the crash as "Failed: 0" until LF.1128. With Haiku only judging, the local build did not recover - against 9/9 for the Haiku-built C# run.

**How other harnesses do it.** Products such as Cursor and Copilot Workspace route the code-writing step, not only planning, to the strongest model available, and use smaller models for retrieval and summarising.

**Added value if built.** A measured per-language routing table: which languages the local model builds alone and which need the stronger build model - the hosted data so far says Rust and C# need it.

## notes-api-rust container 8, local only (run-eaed36e7, 19 Nov 10:55 - 12:00 JST)

Result: hidden 0/9, quality 0/8, failed - the product never compiled.

**Features to improve.** Every harness cause behind earlier Rust failures is now handled and fired here (LF.1126, LF.1130, LF.1131, a dependency pinned to the toolchain), yet twelve borrow-checker and ownership errors stayed after three attempts. This is the local model's Rust.

**How other harnesses do it.** Rust-focused agents lean on the compiler loop with `cargo check` after every edit and on `cargo fix`/clippy suggestions applied mechanically; some (e.g. RustAssistant research) feed the compiler's suggested fix back verbatim.

**Added value if built.** (Corrected 12:20: `cargo fix` and `clippy --fix` apply only warning suggestions and refuse code that does not compile, so they would not have fixed these errors.) The real option is applying rustc's own machine-applicable suggestions for errors - the "consider changing this to be mutable: `mut conn`" class - from its JSON output before a fix round; a larger change, worth it only if local Rust stays a target. The cheaper path the hosted data supports is routing the Rust build to the stronger model.

## web-todo hybrid Haiku 1, judgement only (run-249303db, 19 Nov 11:04 - 12:52 JST)

Result: hidden 9/10, quality 6/6, delivered - a false acceptance; handoff 0.833, mutation 0.67, 96.5 active minutes, $0.18 hosted.

**Features to improve.** The last fix of the run, for the Done control, updated the row in place (toggling a class) rather than re-rendering the list, so a task completed while the list is filtered to active stays in the active view. The locked suite had no test that changes an item while a filter is on, so 27/27 passed and the product shipped broken in one common flow.

**How other harnesses do it.** UI-generation tools built on frameworks (React, Svelte) avoid the class by construction: the view is a function of state, so a filter is re-applied on every change. Test generators for list UIs (Playwright's codegen patterns, model-based testers such as XState's test model) cover state-change x view-mode combinations explicitly.

**Added value if built.** Two cheap levers: (1) browser-pack guidance in `seed.py` - a state change re-renders through the same filtered render, never patches one row; (2) a suite-review rule for any product with filters: at least one test changes an item while a filter is applied. Measure on the next web runs before making either a check.

## notes-api-csharp container 5, local only (run-d74ff9cb, 19 Nov 12:06 - 13:33 JST)

Result: hidden 9/9, quality 7/8, not deliverable (correctly), handoff 1.0, mutation 0.67, 83 active minutes, 2 reverts - the first full local C# score.

**Features to improve.** Sixteen notes created at once are not each kept with their own id - the harness's concurrent-write probe found it, two fixes were reverted and the third did not hold, and it is exactly the quality test the product lost. A SQLite-backed service needs one connection strategy with a busy timeout or serialised writes; the local model did not reach it.

**How other harnesses do it.** Load-aware reviewers (k6 or Locust smoke steps in CI, Devin-style concurrency checks) catch lost writes the same way; stack templates (ASP.NET's own SQLite samples, EF Core) default to a connection per request with WAL and a busy timeout.

**Added value if built.** Stack-pack guidance for the C# (and every SQLite) pack: one connection per request, WAL mode, a busy timeout, and an insert that returns its row id in the same statement - the pattern that makes concurrent creates each kept. It would have saved three fix attempts here and belongs in the pack, not the core.

## notes-api-go container 1, local only (run-7880a2c0, 19 Nov 13:39 - 15:05 JST)

Result: hidden 9/9, quality 8/8, delivered, handoff 1.0, mutation 0.9, 73 active minutes, no reverts.

**Features to improve.** The product is complete. The time lost was the first sprint attempt: the drafted `go.mod` did not match the imports, every build stopped at "go mod tidy", and the fixers had no network to run it - the re-plan rewrote the module file and recovered. One unit test (a port already in use) was left as a completion gap.

**How other harnesses do it.** Go tooling treats `go mod tidy` as part of every dependency change (gopls offers it as a quick fix; CI templates run it with `-diff` to fail on drift), so a module file never reaches a build out of step with the imports.

**Added value if built.** Built already as LF.1134: every Go pack's install runs `go mod tidy` with the install's network before building. Next measurable step: a fresh Go run should never raise "updates to go.mod needed".

## notes-api-php container 5, local only (run-34ea7163, 19 Nov 15:52 - 17:24 JST)

Result: hidden 9/9, quality 8/8, delivered, handoff 1.0, mutation 0.89, 89 active minutes, no reverts, no defects left open.

**Features to improve.** None in the product. One fix round was lost to the harness: Composer rejected a package name in `composer.json`, printed its usage text after the one error line, and the fixer was shown only the usage text; a later round found a stale lock file and regenerated it.

**How other harnesses do it.** CI log summarisers (GitHub Actions' problem matchers, Buildkite annotations) extract the error lines from a tool's output rather than its tail, so a long trailer never hides the cause.

**Added value if built.** Built as LF.1136. A next step worth measuring: when Composer, npm or Cargo reports the lock file out of step with the manifest, remove the lock and install once more automatically, as the harness already does for a lock refused on a checksum.

## notes-api-ruby container 1, local only (run-7a5a4556, 19 Nov 17:29 - 22:13 JST)

Result: hidden 9/9, quality 8/8, delivered, handoff 1.0, mutation 0.75, 267 active minutes.

**Features to improve.** The product is complete; the time was not. The Gemfile asked for `sqlite3 ~> 1.0.2`, a version RubyGems never had; every install failed; the install note first showed only Bundler's platform list, and QA, repairing one test of a reopened suite, spent a 22-minute round validating against a product that could not install and tried six times to edit the Gemfile it may not write. A survived restart added two resumes.

**How other harnesses do it.** Dependency-aware agents (Renovate's manifest updates, Dependabot) resolve a version against the registry before writing it, never from memory; CI systems gate later stages on a green install step rather than letting tests run against an uninstalled product.

**Added value if built.** Built as LF.1138 (the registry's real release named for Bundler, Composer and NuGet) and LF.1139 (QA told the product does not install). The remaining step is the first one: have the drafting stage look a dependency's version up before writing a manifest line, so an invented version is never written.

## web-todo container 3 (20 Nov, run-0080bed4) - 10/10, 6/6, delivered

**Features to improve.** (1) Accessibility fixes: a colour-contrast finding took four fix rounds because the remedy told the fixer to keep the page's own colour names while the failing colour was one of them. Now the harness computes the nearest shade that meets the ratio and says to change the colour where it is defined (LF.1144). (2) Design review: it spent about 2 minutes and 60k reasoning characters finding the specification's API section and function-contracts section contradicting each other; a mechanical comparison before review (extending LF.1126) would find these for free. (3) Internet lookups: the web search had been returning nothing for weeks (the general engines refuse a private instance); fixed for the developer sources (LF.1140), and a full plan for lookups when agents are stuck is Appendix 10 (WL).

**How other harnesses do it.** Accessibility-aware coding agents (and linters such as axe DevTools' guided fixes) propose the concrete passing colour rather than restating the rule; coding agents with search (Claude Code, Cursor, Devin) search the exact error text and prefer Q&A and issue trackers - the shape WL takes, triggered by the harness rather than left to a small model's initiative.

**Added value.** A computed remedy turns a judgement call into a one-line change, which is what a small local model handles reliably; the same principle (the harness computes, the model applies) is behind the registry version notes (LF.1132/1138) and should guide the next fixes.

## Java container 2 (20 Nov, run-e382df47) - 0/9, 0/8, failed

**Features to improve.** (1) Stack decisions: the stack selector invented a database setup ("SQLite via H2's SQLite compatibility mode") that does not exist, and every later stage treated it as fact - the specification wrote SQLite settings into H2's URL, so a fixer's correct change would contradict the specification. A stack decision should be checked before the specification is written: one engine named as running "via" another's mode goes back. (2) Failure evidence: a start failure's real error was buried under stack frames (fixed: LF.1145), and the pack's known cause was added only after the per-defect call ceiling was spent (fixed: LF.1147 - new harness knowledge earns one more attempt).

**How other harnesses do it.** Agents that build on frameworks (Devin, OpenHands, Copilot Workspace) verify a chosen dependency set by installing and starting a minimal skeleton before planning on it; the harness's start-first check does this for the scaffold, but not for the database choice the specification adds later.

**Added value.** A stack choice checked against what exists turns a three-attempt failure into a one-minute correction at the start of the run; it is also where the internet lookups planned in Appendix 10 (WL) would help most - a search for "H2 SQLite mode" says at once that there is none.

## Ruby container 2 (20 Nov, run-1a8bcfcf) - 9/9, 8/8, delivered

**Features to improve.** (1) Context hygiene: every stage was shown \~780 installed gem files under `vendor/bundle`, and the project memory held the gems' source as project files - fixed for Ruby, PHP and Go by reading the per-language table of tool-filled folders (LF.1148). (2) Edge validation: the one defect was a number accepted as a title; the edge probe caught it and it was fixed in two rounds - a type check written into the golden example would remove the round entirely.

**How other harnesses do it.** Coding agents index the repository with the project's own ignore rules (`.gitignore`, the package manager's vendor path) before building a context; this harness now derives the same from its language table, which also covers a project with no ignore file.

**Added value.** 63.7 active minutes against Ruby container 1's 267 on the same brief: the version-lookup and install-failure fixes (LF.1138/1139) meant nothing to recover from, and a smaller listing keeps every request shorter.

## Java container 3 (20 Nov, run-9c875db7) - 9/9, 8/8, delivered

**Features to improve.** (1) Unit tests: the sprint was accepted with failing unit tests recorded as known issues - the product was right and its own tests were not; a delivered product whose unit suite is red is a handoff cost for whoever maintains it. (2) Fix targeting: the first fix for a start failure rewrote `pom.xml` although the output named a missing folder; LF.1149 now says it in plain words when it recurs.

**How other harnesses do it.** SWE-agent-style harnesses keep the failing command's own error line as the first thing a fixer reads, and re-run the exact failing command after each edit; the harness now leads with the stated error (LF.1145) - the same evidence-first shape.

**Added value.** The same family on the same night went from 0/9 to 9/9 with every quality test: the difference was the evidence the fixer was shown, not the model.

## PHP container 6 (20 Nov, run-bf4765fa) - 9/9, 8/8, delivered

**Features to improve.** (1) Diagnostics the harness runs for itself: the start probe, in container mode, had been sending a malformed request (`GET ../health`) because an argument rewrite meant for the model's commands also touched the harness's own - so a product that started but failed every request was reported as silent, its real error unshown (LF.1150). The harness's own measuring commands deserve their own end-to-end test against a real served product, not only unit tests of each piece. (2) Framework versions: a Slim 3 middleware shape in a Slim 4 project failed every request; now a known error (LF.1151), and a natural first case for the WL lookups (Appendix 10).

**How other harnesses do it.** Harnesses that verify by running the product (SWE-bench-style evaluators, OpenHands) keep their own probes outside the agent's tool layer, so nothing written for the agent's convenience can change what the probe sends.

**Added value.** 41.6 active minutes for a full score - with the probe fixed, the next start failure on any stack comes with the product's own error line, which is what made Java go from 0/9 to 9/9 tonight.

## C# container 7 (20 Nov, run-f37cd853) - 9/9, 8/8, delivered

**Features to improve.** (1) The harness's own checks against its own packs: the C# compiler check looked for a project file at the project's top, and the C# pack never puts one there - so every C# rewrite had gone uncompiled since the check was built (fixed: LF.1152). Each pack's scaffold should be run through every harness check once, mechanically, so a check that cannot see a pack's layout fails a test instead of a run. (2) Error-handler wiring in minimal APIs was written wrong twice in a row (`IApplicationBuilder.ErrorHandler`, assigning to `Run`); if it recurs, the C# pack's known errors should carry the right shape.

**How other harnesses do it.** Agent harnesses that edit compiled code (Aider's lint-and-fix loop, SWE-agent's edit linting) run the compiler or linter after every edit and feed the errors straight back before the turn ends - the loop this harness has, which the pack's layout had silently switched off for C#.

**Added value.** With compiler feedback, attempt 3 reached 18 of 18 criteria in two rounds; attempts 1 and 2 without it spent three minutes and three rounds each walking from one compile error to the next.

## Go container 3 (20 Nov, run-2be2b208) - 9/9, 8/8, delivered

**Features to improve.** (1) Documentation lookups: the architect asked twice for `modernc.org/sqlite`'s usage and was told nothing existed - only GitHub-hosted Go modules had a source (fixed: LF.1154, pkg.go.dev). This is the internet-lookup gap in miniature: the model did look things up; the lookup had nowhere to go. (2) Language rules the error message does not state: Go's "is not in std" for a mistyped module path cost two attempts (fixed: LF.1155) - the fourth such pack explanation tonight (H2, Slim, C# layout, Go), which argues for the WL plan's harness-driven lookup of the exact error when no pack explains it.

**How other harnesses do it.** Coding agents with documentation tools (Context7, Cursor's docs index) resolve a package to its canonical documentation site per ecosystem - pkg.go.dev for Go, docs.rs for Rust - rather than only the repository README.

**Added value.** Attempt 3 passed every criterion from its first round; the time lost was in attempts 1 and 2, both to errors a one-paragraph explanation settles.

## tasks-api container 5 (20 Nov, run-ea01f85c) - 10/10, 7/7, delivered with cuts

**Features to improve.** (1) Wrong locked tests: two acceptance tests passed the sign-in response's JSON object where the token string belonged, so the product's 401 was correct and the tests could never pass; the dispute called them wrong, but both were past their repair cap, and about an hour went on re-planning around them. A mechanical check of a dispute's claim - re-run the disputed test with the repair it proposes and see whether it then passes against the same product - would let the harness accept such a sprint safely, or repair the test, instead of grinding. (2) Mutation score 0.33: the unit tests pass but catch few deliberate changes; the sprint's own check found one such change and asked for tests - a stronger push there would raise it.

**How other harnesses do it.** Benchmarks that grade with hidden tests (SWE-bench, the harness's own scorer) treat the visible suite as advice, not the definition of done; agents that write their own tests (Devin, OpenHands) re-validate a test that fails against a plausibly correct product before trusting it.

**Added value.** Every hidden and quality test passed - the product was right; the cost was time, 175 active minutes against container 4's 96, almost all of it after the product was done.

## Ruby container 3 (20 Nov, run-62a7d976) - 9/9, 8/8, delivered

**Features to improve.** (1) The harness's own tools are documented by the harness: the acceptance author needed one fact about Playwright's request API (a raw body is a string `data` with its content type), its documentation lookup returned the package README, and it searched the installed source for twelve minutes. Playwright is the harness's acceptance runner, so the answer now ships in the suite guide (LF.1156); the same holds for any tool the harness itself runs - say how to use it rather than leave it to a lookup. (2) Nothing else held it back: 18 of 18 after one round, every quality test, no defect left open.

**How other harnesses do it.** Agent frameworks that hand a model a fixed toolset (OpenHands, SWE-agent) describe each tool's arguments in the tool's own description - the model never has to discover its tools' behaviour.

**Added value.** 56 active minutes for a full score - Ruby went from 267 minutes (container 1) to about an hour, twice in a row, after tonight's install and listing fixes.

## web-todo container 4 (20 Nov, run-09fc4306) - 10/10, 6/6, delivered

**Features to improve.** (1) Fix-round length: round 1 carried five defects in pairs and took 35 minutes; one fixer used all 17 of its calls without writing its answer (the AC-1 add form), yet the round still closed four of five criteria. A fixer that reaches its call limit with no write could hand its findings to the next pair rather than end empty. (2) What worked: the computed contrast shade (LF.1144) closed the accessibility defect in one 2-call rewrite - container 3 needed four rounds for the same finding.

**How other harnesses do it.** Linters with autofix (axe DevTools, stylelint) apply a computed value; the harness now hands the model the value instead of the rule.

**Added value.** A full score with every quality test, and the one defect that cost container 3 four rounds closed at once.

## PHP container 7 (20 Nov, run-aa3693b6) - 9/9, 8/8, delivered

**Features to improve.** (1) A shared 500 cost a whole attempt: the harness grouped 19 failing tests into one shared-cause defect correctly, but the fixer did not find the common code path in two rounds; the re-plan's fresh draft did. Naming the first frame of the product's own code in the 500's log (where the error was raised) would point the fixer at it. (2) Mutation gaps were fixed one fixer per gap in the same file (15 min); a single fixer per file, behind a switch, is filed.

**How other harnesses do it.** Fixers in mature agent loops are handed the server log line for a failing request, not only the HTTP status - the error and its location travel together.

**Added value.** Full score, every quality test; PHP is 2 of 2 full tonight (container 6: 41.6 min, container 7: 77.6 min).
