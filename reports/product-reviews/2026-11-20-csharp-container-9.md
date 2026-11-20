# End-of-run product review: C# container 9 (2026-11-20)

Run run-50a7c5cc-0c78-4035-8f2f-83d754b8e7b2, notes-api in C#/ASP.NET, qwen3.6-35b-a3b-mtp@iq4_nl on :1234, 13:03-14:24 JST, switches on: `WEB_LOOKUP_WHEN_STUCK`, `WEB_TOOLS_AFTER_TWO_FAILED_FIXES`, `MUTATION_GAPS_BUNDLED`.

**Score:** hidden 9 of 9, **quality 6 of 8**, handoff 1.0, no false acceptance. 73 active minutes, 148 model calls, mutation score 0.9. **Verdict: not deliverable**: at release the product breaks 8 interface-contract lines and the server-error and edge probes still find 500s (requests with no body, a number for a text field, malformed JSON). The two quality tests lost are the same faults (malformed JSON, a null or blank title).

## What went wrong
- **The faults that blocked release were never raised as defects during the sprint.** The rounds raised only "does not start", a compile error, a top-level-statements error and failing unit tests; the locked suite was 10/10 green; the sprint settled when its attempts ran out, and the release checks then found the 500s. Being investigated (worktree): a fault a harness probe blocks release for must be raised in a round while attempts remain.
- The suite's dry run stopped three rounds on a spec declaring `__filename` (LF.1183 gives the cause); the per-role audit's LF.1177 held that true finding back (fixed in LF.1183).
- The testing work order tried to rewrite `Program.cs` five times and was refused each time (11 such refusals in three runs today; the refusal text already names the right route).
- KPI regressions: tool failures 7.8% (mean 3.3%) - mostly those refusals; redundant reads 28% (mean 13%).

## Switches
None of the three had a case: no defect stayed stuck long enough for a lookup, no fixer failed twice, and the mutation gaps were few.

## Added value
The first quality loss today, and a verification gap worth more than the run: green acceptance and hidden tests beside contract breaks the harness's own probes see.
