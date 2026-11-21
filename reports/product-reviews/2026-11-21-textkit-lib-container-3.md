# End-of-run product review: textkit-lib container 3 (2026-11-21)

Run run-41ca16fd-ca4d-4cf3-84ca-99a413fe92cf, textkit-lib (Python library brief), unsloth/Qwen3.6-35B-A3B-MTP-GGUF on :8888, 08:44-09:00 JST. Switch on: `WEB_LOOKUP_WHEN_STUCK`.

**Score:** hidden 8 of 8, quality 7 of 7, **delivered**, handoff 1.0, no false acceptance. **13.6 active minutes**, 47 model calls, no fix reverted, 1 defect left open, mutation score 1.0. KPI flags: tool failures 3.8% (mean 1.6%), redundant reads 10% (mean 5.9%) - both small-sample.

## What the run showed
- The fastest run of the project (wordstats-cli 3 took 23 minutes earlier today): a 38-test acceptance suite, a dispute and a suite repair after the first test round, two fix rounds. The suite-repair redesign (LF.1190) let the dispute's rewrite lock in one step.
- Both small briefs of the day (wordstats-cli, textkit-lib) scored a mutation score of 1.0: on the small briefs the model writes the tests that hold the code, on the service briefs they hold only the interface.

## Added value
A clean reference run for the library family. No harness fault.
