# Product review: notes-api-ruby 7 (11-28)

run-04f7203e-660c-405f-b2da-8c18fb2ca9af. Qwen 3.6 35B on two llama.cpp servers, local model only, parallel
execution, a second run live beside it. 01:10 to 02:19 JST. Mixed versions: LF.1628-1630 deployed into it at 02:02.

## Score
| Measure | Result |
|---|---|
| Hidden tests | 9/9 |
| Brief's edges | 8/8 |
| Verdict | delivered; handoff 1.0 |
| Locked suite | 17 passed, 0 failed |
| Mutation check | 5 of 5 caught |
| Release | completed with 8 gaps |
| Time | 69 min wall; model busy 83% |
| Model | 187 calls, 341k output tokens (61% reasoning), 5.9M input (66% from cache) |

## What went wrong or cost time
- Little: one fix round, 2 failed tool calls in 176. Identical-call rate 0.09 against a 5-run mean of 0.04.
- The suite was locked with five review findings open, two of them saying a test asks for more than its criterion
  (a database file by name; a list order the brief does not state). Neither cost a test here.

## To add or improve
1. Send a locked-suite finding that says a test demands more than its criterion back to the author before the lock.
