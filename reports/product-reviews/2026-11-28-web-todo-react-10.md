# Product review: web-todo-react 10 (11-28)

run-250d21ef-17a6-44a9-a242-419c55f695d0. Qwen 3.6 35B on two llama.cpp servers, local model only, parallel
execution, a second run live beside it. 03:55 to 06:22 JST. Mixed versions: deploys into it at 05:00 and 05:26.

## Score
| Measure | Result |
|---|---|
| Hidden tests | 10/10 |
| Brief's edges | 6/6 |
| Verdict | delivered with known defects; handoff 1.0 |
| Locked suite | 23 passed, 0 failed |
| Mutation check | 6 of 12 caught (0.46) |
| Release | completed with 9 gaps; 2 locked tests reclassified under dispute |
| Time | 147 min wall; model busy 77% |
| Model | 310 calls, 622k output tokens (61% reasoning), 9.53M input (61% from cache) |

## What went wrong or cost time
- The review after the accepted escalation ran for the first time (LF.1644) and read only the sprint's diff: its
  blocking finding said a stylesheet import was missing that another, unchanged file already had. The fix pass added
  a duplicate, and the release is marked as having known defects (a fix is being built).
- The sprint was planned again and accepted at an escalation; the last fix round changed nothing while its answer
  said it had.
- Tool failure rate 9.0% against a 5-run mean of 2.8%; 3% of output lost to cut replies; one repetition loop.
- A development-only dependency carries a critical advisory (`tinypool` 1.1.1).

## To add or improve
1. Review findings that rest on the product, not on the diff (being built).
