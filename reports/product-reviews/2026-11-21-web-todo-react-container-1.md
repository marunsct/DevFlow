# End-of-run product review: web-todo-react container 1 (2026-11-21)

Run run-a75f7767-6eb3-4bac-9a31-a8a82ecd4b3f, web-todo-react (React page product), qwen3.6-35b-a3b-mtp@iq4_nl on :1234, 19:33 JST (11-20) to 01:43 JST, about 6 hours of wall time. Switch on: `WEB_LOOKUP_WHEN_STUCK`.

**Score:** hidden 9 of 10, quality 6 of 6, **not deliverable**, handoff 1.0, **false acceptance: true** (the run released with AC-3, AC-10, AC-13 and AC-14 deferred while its own locked tests for them failed; the hidden test lost is the edit-and-reload one). **364 active minutes**, 563 model calls, 14 fixes reverted (mean 1), 32 defects left open (mean 9), mutation score 0.5.

## What cost time
- About five hours on three criteria (edit a title, add/edit/delete, keep the list after a refresh) that waited behind unit-test regressions in the first attempt, then failed three sprint attempts. Fix order: `FIX_ORDER_CRITERIA_FIRST` (LF.1201, off here) targets the wait; the same brief on the faster :8888 model reached all green in 74 minutes (web-todo-react 2).
- The locked edit-title test finds the task by the title text its own edit mode hides; LF.1200 gave the QA lead and the dispute that finding and the fixers the hint; the judge ruled the test right twice and the fixers did not keep the title visible while editing. The local model on :1234 did not act on either.
- The run ended by deferring the four criteria ("defer AC-10, AC-13, AC-14, AC-3 and continue") and releasing - not delivering, and flagged as such.

## Switches
- `WEB_LOOKUP_WHEN_STUCK`: searched `TypeError: Cannot set properties of null` early (3 results); not a factor in the outcome.
- LF.1200: delivered to the QA lead, the dispute and two fixers; not effective on this model.

## Added value
The run that exposed three harness bugs worth fixing (the case-insensitive text match, the text-hidden-by-action trap, the failing-criteria-last order) and a limit: a hint to a small model does not replace a harness rule. Decision pending: whether a suite finding that three product fixes have not cleared should reopen the suite (a rule, not advice), measured behind a switch.
