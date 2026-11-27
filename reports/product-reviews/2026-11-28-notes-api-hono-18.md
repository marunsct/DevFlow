# Product review: notes-api-hono 18 (11-28)

run-55aade33-a627-4459-80b9-04c734a09888. Qwen 3.6 35B on two llama.cpp servers, local model only, parallel
execution, a second run live beside it. 04:55 to 05:44 JST. Mixed versions: deploys into it at 05:00 and 05:26.

## Score
| Measure | Result |
|---|---|
| Hidden tests | 9/9 |
| Brief's edges | 8/8 |
| Verdict | delivered; handoff 1.0 |
| Locked suite | 18 passed, 0 failed |
| Mutation check | 7 of 12 caught (0.58) |
| Release | completed with 8 gaps |
| Time | 50 min wall (47 working); model busy 75%, neither 24% |
| Model | 100 calls, 233k output tokens (68% reasoning), 2.46M input (53% from cache) |

## What went wrong or cost time
- Little: no failed tool calls, no reply cut at the cap, no command at its time limit.
- Redundant reads 19% against a 5-run mean of 9%; two defects left open (mean 0.4).
- Five of 12 deliberate changes passed every test.

## To add or improve
1. Measure where the repeated reads came from in a short run like this one.
