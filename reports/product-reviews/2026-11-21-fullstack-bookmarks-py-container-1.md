# End-of-run product review: fullstack-bookmarks-py container 1 (2026-11-21)

Run run-ef06e436-eca3-47a9-b3c6-4cc5a53574eb, fullstack bookmarks in Python (Flask service and page), unsloth/Qwen3.6-35B-A3B-MTP-GGUF on :8888, 04:49-06:25 JST. Switches on: `FIX_ORDER_CRITERIA_FIRST`, `WEB_LOOKUP_WHEN_STUCK`.

**Score:** hidden 8 of 8, quality 7 of 7, **delivered**, handoff 1.0, no false acceptance. **89.6 active minutes**, 234 model calls, no fix reverted, 2 defects left open (mean about 3), mutation score 0.5. The first fullstack Python run of the project to score full on all three.

## Fix order (`FIX_ORDER_CRITERIA_FIRST`, third arm)
- Acceptance went from 1 of 19 to 18 of 19 in the first fix round (about 40 minutes after drafting) and to 19 of 19 after one dispute and a suite repair. The record for this run was not read (the first fix round used a batch of fixers); the arm shows no cost.
- Three page-brief arms on the :8888 model have now delivered with the switch on (fullstack-bookmarks 2, web-todo 5 on a page defect, this run); none has been run on :1234, so the switch's gain over the model is still not separated. It stays off until one :1234 arm.

## What cost time
- Nothing outside the usual: a suite dispute and repair after round 2 (about 20 minutes), unit-test defects at the end. 14 of 212 tool calls failed (refusals of testing roles writing product code).

## Added value
A delivered fullstack product in 90 minutes with full marks on both hidden and quality tests; the runs of the day on :8888 are now consistently under two hours on the page and fullstack briefs.
