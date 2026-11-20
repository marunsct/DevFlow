# End-of-run product review: fullstack-bookmarks container 2 (2026-11-21)

Run run-8808daaa-78d7-4964-810e-7d95ea9b4747, fullstack bookmarks (browser page and Express service), unsloth/Qwen3.6-35B-A3B-MTP-GGUF on :8888, 01:22-03:12 JST. Switches on: `FIX_ORDER_CRITERIA_FIRST`, `WEB_LOOKUP_WHEN_STUCK`.

**Score:** hidden 8 of 8, quality 6 of 7, **delivered**, handoff 1.0, no false acceptance. **107.5 active minutes** (fullstack-bookmarks 1: 289), 182 model calls, 1 fix reverted, 13 defects left open, mutation score 0.364 (mean 0.57). The quality test lost: "fields of the wrong type are refused and the service keeps answering".

## Fix order (`FIX_ORDER_CRITERIA_FIRST`)
- Fired once, in round 1 (01:56 JST): "10 moved ahead, 2 after them". The fixers worked the failing criteria first, and acceptance went from 13 of 15 to all green within about 85 minutes; the run then went through two suite repairs after disputes and finished at 16 of 16.
- Compared with fullstack-bookmarks 1 (289 minutes, not deliverable on two false release blockers since fixed), this run is 2.7 times faster and delivered. The two differ in model (:8888 against :1234) and in the fixes deployed in between, so the switch's own share is not separable from one pair. One more arm on a page brief.

## What was lost
- The quality test: a wrong-typed field (for example a number for the title) is refused with an error that keeps the service answering. The edge probe covers wrong-typed bodies on the interface contract's write lines; this product's page and service seem to have been checked only at those lines, and this field is not among them. A look at which of the probe's cases the contract left out would show the gap.
- Mutation score 0.364: several mutants survive; 13 defects left open at the end are mostly unit-test findings.

## Added value
A delivered fullstack product in under two hours with one quality edge lost - the best fullstack result of the project so far.
