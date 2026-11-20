# End-of-run product review: tasks-api container 7 (2026-11-20)

Run run-2df00e65-8664-4517-8921-257c3f5e7806, tasks-api in Python, unsloth/Qwen3.6-35B-A3B-MTP-GGUF on :8888, 14:29-16:55 JST. Switches on: `QA_PROMPT_TRIMMED`, `REVIEWER_SHAPED_PLUGIN_CONTENT`, `LEAD_REPLAN_REQUEST_SMALLER`, `CONTESTED_TESTS_CONFIRMED`.

**Score:** hidden 10 of 10, quality 7 of 7, **delivered**, handoff 1.0, no false acceptance. All 62 locked acceptance tests passed at the end.

## What cost time
- The suite writer and its reviews took **52 model minutes over 173 calls**, against 9.2 (27 calls) in tasks-api 6 and 10.4 (33) in tasks-api 5.
- About 45 minutes of the suite being open came from three repair-flow bugs found in this run and fixed during it: a rewritten test recorded after its writing, so every check said "has not changed" (LF.1188); a put-back to the lock that erased the harness's own better rewrite (LF.1189); and the state of a repair kept in five places (LF.1190, after a design review: `reports/audits/2026-11-20-suite-repair-flow-review.md`).
- The suite writer was shown "The service did not start" for every test after drafting and tried six times to edit the product (LF.1188).
- Before drafting, the writing itself ran five stages against the "signs in as someone never signed up" check (26 findings; tasks-api 5 and 6 had one between them).

## Switches
- `QA_PROMPT_TRIMMED`: fired (3,810 characters left out of the suite writer's prompt). **Costly in its first arm**: the suite writer's time rose about fivefold; part of it is the repair bugs, but the writing before drafting, which those bugs did not touch, took about three times as long. Kept off; one more arm after LF.1190 before it is dropped.
- `REVIEWER_SHAPED_PLUGIN_CONTENT`: fired in the reviews (1,079-4,271 characters left out); no cost seen.
- `LEAD_REPLAN_REQUEST_SMALLER`: no case - the re-plans took the fast path, which does not call the lead.
- `CONTESTED_TESTS_CONFIRMED`: no case - both disputes stayed within the reclassification cap.

## Added value
The first tasks-api delivery today, and the run that exposed the suite-repair flow's design faults.
