# Why the harness fails medium briefs, and what makes it handle them (deep review, 2026-11-24)

Five read-only investigations of the failed medium-brief run (run-8f0be29e, a task management dashboard: FastAPI, React,
JWT; 13 criteria, 97 locked acceptance tests; 24 h 15 min; ended at 17 of 97) and of the harness code: time and flow,
planning and decomposition, the fix loop, the acceptance suite against the product, and the harness's scale limits and
history. Times are JST. Numbers are measured from the transcript, the workspace and `.harness/` unless marked inferred.

## The answer in one paragraph

The product was not far off: with the specification's own rate limit lifted and three small code fixes (a doubled route
prefix, a list query that raises, tables created at start) **82 of 97 tests pass** - reproduced on a copy. The harness
could not get there because (1) its specification added a sign-up limit of ten an hour that its own locked suite, which
signs up about 88 times a run from one address, can never run under, and nothing checks that the two can both be true;
(2) sprint 1 (sign-up and sign-in) ended with 5 of its 18 tests passing and the run "deferred and continued" into a
sprint whose every test signs up first; (3) the fix loop judges a fix only by the suite's pass count, so correct fixes
that moved the failure from 500 to 404 scored as failures and two correct fixes were reverted because they exposed a
second latent fault; (4) every stage carried about 50,000 tokens of plans in a 54,000-token input ceiling, so 63% of
model calls only read files; and (5) the caps that bound a run (time budget, calls per stage, steps per run) are flat
or checked too late. The same weaknesses exist on small briefs; a small product is forgiving of them.

## What the 24 hours bought

| Measure | Value |
|---|---|
| Time that moved the pass count | 14 min (two fix stages, both logged "left open") |
| Time after the last change of the count (17 at 08:33 on 11-23) | 933 min, 64% of the run |
| Model calls that only read or listed files | 1,323 of 2,100 (63%), 49% of model time; `main.py` read 226 times |
| Suite authoring and repair | 382-425 min (about 29%); four lock versions; the cause never touched |
| Fix stages | 34: 9 "fixed" (none verified; one made no write), 20 left open, 5 reverted (2 of them correct fixes) |
| Defect ids never shown to a fixer | 17 of 38, including the only two naming the doubled prefix and the rate limiter |
| Stage work re-done after mid-run deploys | about 214 min over 15 deploys (the stage in flight restarts from an empty conversation) |
| Sprint time budget | 126 min; sprint 2 ran 891 (the budget is read only when an attempt ends) |
| Against a delivered small run (tasks-api 15) | 7.9x the time, 11.5x the input tokens, 1.5x the input per call |

Corrections to the first write-up (`reports/product-reviews/2026-11-24-medium-brief-task-dashboard.md`): the final split
of the 80 failures is 37 direct 429, 18 "Login rate limited" thrown by the suite's helper, 13 404, 8 "Login failed 401",
4 other - not "66 of 92 on 429" (a mid-run reading); LF.1243 therefore never fired on this run (37 of 80 is under its
half), and LF.1244's mid-round deploy made the round skip the defects it was meant to put first.

## Findings by angle

### A. Specification and plan
1. **The specification adds behaviour the brief never asked for, and nothing reconciles it with the suite.** A security
   suggestion (rate limits) was "adopted"; the suite needs it never to fire; one spec test case wants the sixth login
   refused. A fixer named the collision at 08:42 on 11-23 and could do nothing: the spec mandates it, the suite is locked.
2. **Criteria taken from a medium brief are headings** ("Assign tasks to team members"); the model invented every detail
   behind 97 tests, unevenly (27 tests for one criterion, 1 page test in all). The specification's interface contract
   was empty, and spec, suite and code disagreed on route prefixes and token fields.
3. **A sprint that fails is deferred and the next one starts, whatever it depends on.**
4. **The run used the `thorough` path** (4 of the last 150 runs); the bounded work of the fast path (three files a work
   order, one file a call, role from file kind) was not in use: one order gave eight files to the "database" role.
5. **Sprint count is capped by criteria count**, so a larger brief gets larger sprints.

### B. Acceptance suite at this size
6. **Whole suite written and locked before any code, and all of it run at every measurement**, including the 53 tests
   not due until sprint 3 - which ran first (alphabetical) and spent the sign-up allowance before sprint 1's own tests.
7. **One account per test, no shared fixture; seven divergent copies of the helpers**; the author recorded "files pass
   alone, the full suite times out" and the suite was locked anyway, "with these still open".
8. **Repairs treat causes as per-test faults:** the dispute diagnosed the limiter correctly 15 hours in; the repair added
   a 3-second retry against a one-hour window. Four tests assert things no product could give.
9. **The unit gate passes on zero tests**; every backend unit test written was later gone from the workspace (1,069
   lines; cause to trace - the work order's test path and the runner's `testpaths` disagree).

### C. Fix loop
10. **Four stacked blockers, each a one-to-five-line fix, never named as blockers**; 38 defect ids for about 7 causes.
11. **A fix is judged by the pass count alone.** A correct fix that exposes the next latent fault is reverted ("18
    passing to 0"); progress from 500 to 404 counts as nothing; a defect with no tests of its own closes on the fixer's
    word.
12. **Fixers work blind:** stale server logs (up to 10 hours), the round's cause defect absent from related prompts, 155-
    170K-character prompts that compact within five calls, and a call cap that refuses the final edit (10 attempts).
13. **Order and position:** defects carried over went first; the cursor is a list position, so a changed order skips work.

### D. Scale limits in the harness
14. **Input room:** 91,776-token slot, 32,000 reserved for the reply on every call, summarising from about 43K; the
    specification alone was about 34K tokens. No one budget covers what a request carries.
15. **Flat caps:** 40 calls a stage, 16 a fix, 3 rounds an attempt, 2 suite repairs - the same for 3 tests or 97.
16. **The outer graph's 100-step limit is in effect a whole-run budget** (it ended the Next.js run, run-418ca472).
17. **A re-plan redoes the sprint;** a mid-run deploy restarts the stage in flight from nothing.
18. **Proposed before and never built:** a walking skeleton first (its stated target: "the medium brief converges"), one
    input budget per request, specification slices by stage, the lead planning one work order a call.

## What to build, in order

Bug and quality fixes are always on; optional efficiency goes behind a switch (owner policy). Each item gets a test that
fails on the old code. The small path must stay as it is where a size threshold decides.

**Bundle 1 - stop the loop being blind (bugs; small; independent files)**
- 1.1 The fix cursor is "open and not yet worked this round", not a list position.
- 1.2 One cause for many tests counts helper-thrown errors and clusters by the first failing step, not only by status.
- 1.3 A defect is not closed on a claim: no measured pass means "unverified"; a fix with no write is not "fixed"; an
  unmeasured "fixed" does not clear the start-break note.
- 1.4 The sprint time budget is read inside the attempt (each round, each fixer), not only at its end.
- 1.5 The step limit of the outer graph resumes the run instead of failing it; every defect source is capped a round.
- 1.6 The unit gate does not pass on zero tests where tests were ordered; trace the vanished unit tests.
- 1.7 A sprint that later sprints depend on is not deferred past: the foundation is re-planned, or the run stops there.

**Bundle 2 - a foundation that is proven, and fixes judged fairly (quality; medium)**
- 2.1 Foundation smoke before the suite counts: start, the contract's sign-up and sign-in, one create, one read; while it
  fails, that one defect is raised with the live answer and the server log, and nothing else is dispatched.
- 2.2 The suite runs the due criteria, earliest sprint first; not-yet-due tests do not run in a sprint's gate.
- 2.3 A fix that breaks the start is repaired forward (the start error handed to the same fixer) before it is reverted.
- 2.4 Progress is read from the failure profile (a later step reached, another answer), not only the count.
- 2.5 Before the lock: a limit the specification adds is compared with how often the suite calls that route; behaviour
  beyond the brief that refuses a client is declined, made configurable, or given its own test.
- 2.6 The fixer is given fresh evidence (this round's answer and log), the round's cause defect, and its last call
  reserved for the write.

**Bundle 3 - room to work and work sized to the product (quality with size thresholds; larger)**
- 3.1 One input budget per request; specification sections by stage (generalises LF.1232 to every stage).
- 3.2 `REPLY_ROOM_SIZED_PER_ROLE` with `SUMMARISE_LATER_WITH_HEADROOM` measured on :1234 (built, off).
- 3.3 Sprints sized by work (about six criteria), not capped by count; thorough runs get the fast path's bounded orders.
- 3.4 Shared fixtures past a suite size; one helper module; a full-suite dry run as a lock gate.
- 3.5 A deploy waits for a stage boundary on a long run, or the stage's conversation survives the restart.

**For the owner to decide**
- 3.6 Locking the suite sprint by sprint for larger briefs (it changes what "locked once" means).
- A scored medium benchmark with hidden tests, so bundles 2 and 3 can be measured; medium runs are uncounted today.
- Whether to rerun the medium brief after bundle 1 and again after bundle 2.

## Evidence
Transcript `/app/data/transcripts/run-8f0be29e-4c22-425f-9219-46b166b93d70.jsonl` and workspace
`/app/data/workspaces/default/workspace-run-8f0be29e-*/` in the worker container; the reproduction of the five product
variants (17, 24, 30, 71, 82 of 97) was run on a copy outside the workspace.
