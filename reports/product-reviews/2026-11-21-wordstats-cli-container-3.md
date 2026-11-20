# End-of-run product review: wordstats-cli container 3 (2026-11-21)

Run run-aaefe00d-33ad-454c-83ca-a408775430a6, wordstats-cli (command-line brief in Python), unsloth/Qwen3.6-35B-A3B-MTP-GGUF on :8888, 08:17-08:40 JST. Switch on: `WEB_LOOKUP_WHEN_STUCK`.

**Score:** hidden 8 of 8, quality 6 of 6, **delivered**, handoff 1.0, no false acceptance. **23 active minutes**, 75 model calls, no fix reverted, no defect left open, **mutation score 1.0**. No KPI past 1.5 times its mean: the best run of the project on every measure.

## What the run showed
- A small brief with a full acceptance suite (18 tests) and four fix rounds on the first test round, then the end-of-sprint reviews. The earlier wordstats-cli runs on this harness (about a month ago, on a different model) failed three of eight hidden tests; the independent suite is now stronger and the checks around it (the repair record, the interface checks, the page and probe fixes of today) leave a brief of this size nothing to catch.
- A mutation score of 1.0 is rare (the project mean is about 0.6): every deliberate change to the product was caught.

## Switches
- `WEB_LOOKUP_WHEN_STUCK`: no case.

## Added value
The fastest and cleanest delivery of the project: a reference point for what "no wasted time" looks like at this size (23 minutes, 75 calls).
