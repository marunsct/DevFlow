# End-of-run product review: notes-api container 2 (2026-11-21)

Run run-a6b50450-0a17-49d9-a1aa-d8d7a957aef3, notes-api in Python, qwen3.6-35b-a3b-mtp@iq4_nl on :1234, 02:02-04:02 JST. Switch on: `WEB_LOOKUP_WHEN_STUCK`.

**Score:** hidden 9 of 9, quality 8 of 8, **delivered**, handoff 1.0, no false acceptance. **119 active minutes**, 195 model calls, no fix reverted, 6 defects left open (mean 2.8). Mutation score **0.0** (mean 0.75); with the project's own unit tests 0.33.

## What the run showed
- A clean Python delivery on the :1234 model: all 13 acceptance tests passed from the first test round (02:42 JST); the remaining 80 minutes went on unit-test and code-check defects (three sprint attempts, two fixers in parallel) and the end-of-sprint reviews.
- The mutation result is the finding: of 12 deliberate changes to the product, the locked acceptance suite caught 2 by breaking the start, none by a specific test; the unit tests caught 4 in all. The run's mutation-guided round raised 11 gap defects and fixed some of them, but the score on the delivered product stays low: the acceptance suite checks the interface's lines, and the code behind them (validation edges, ordering) is held by unit tests the same model wrote.
- Identical tool calls 5.7% (mean 1.8%): repeated file reads in the fix rounds, the pattern seen in Java 4.

## Switches
- `WEB_LOOKUP_WHEN_STUCK`: no case.

## Added value
A delivered Python service in two hours on the slower model. A flag for later: a full-marks delivery with a mutation score of 0 says the tests prove the interface, not the code, which is what the hidden and quality tests also check; both passed here.
