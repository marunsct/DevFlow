# Product review: notes-api-java 13 (11-27)

run-e4e5c8a4-17bc-474f-9f7a-ec4a358f2b31. Qwen 3.6 35B on two llama.cpp servers, local model only, parallel
execution, a second run live beside it. 18:41 to 20:49 JST. Mixed versions: LF.1606-1607 deployed into it at 19:25,
LF.1608-1613 at 20:28.

## Score
| Measure | Result |
|---|---|
| Hidden tests | 9/9 |
| Brief's edges | 6/8 (quality 0.75; 5-run mean 1.0) |
| Mutation check | 6 of 12 caught (0.40; 4-run mean 0.82) |
| Verdict | not deliverable; locked suite 29 passed, 1 failed |
| Release | completed with 9 gaps; AC-18 deferred, unproven; no code, milestone or security review ran |
| Time | 128 min wall; model busy 83% |
| Model | 304 calls, 657k output tokens (68% reasoning), 8.98M input (59% from cache) |

## What went wrong or cost time
- The product did not start through six fix rounds: a compile error, then two health controllers, then a hand-built
  `SessionFactory` bean that stopped Spring Boot building its entity manager factory. The specification asked for that
  class. 114 fix calls, 49 of the 107 model minutes.
- A unit test's compile error was folded into the start defect and aimed 5 of 6 rewrites at the test file; three
  rewrites were reverted for the same compiler line (fixed by LF.1611-1613).
- The sprint was planned again twice and accepted at an escalation, so the release went out without the reviews.
- `GET /notes/not-a-number` and a very large id answer 500 where a refusal is due.
- The testing specialist's reply ran away to 16,000 tokens, passed on with 30,000 characters of junk (LF.1607).

## To add or improve
1. Run the code and security reviews before a release whose sprint was accepted at an escalation.
2. Map a class name in a start trace to its source file, so the named class is offered to the rewrite.
3. Turn a recurring-cause diagnosis's files into files the fixer may write.
