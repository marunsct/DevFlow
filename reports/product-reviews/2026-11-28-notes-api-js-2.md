# Product review: notes-api-js 2 (11-28)

run-48e11408-ecec-4acc-b169-31ddb5e79b18. Qwen 3.6 35B on two llama.cpp servers, local model only, parallel
execution, a second run live beside it. 02:25 to 04:44 JST. Mixed versions: LF.1631-1632 deployed into it at 03:11.

## Score
| Measure | Result |
|---|---|
| Hidden tests | 9/9 |
| Brief's edges | 8/8 |
| Verdict | delivered; handoff 1.0 |
| Locked suite | 18 passed, 0 failed |
| Mutation check | 9 of 12 caught (0.73) |
| Release | completed with 9 gaps; one unit test set aside; accepted at an escalation, so no code, milestone or security review ran |
| Time | 139 min wall (136 working); model busy 72%, neither 23% |
| Model | 223 calls, 706k output tokens (73% reasoning), 7.13M input (60% from cache) |

## What went wrong or cost time
- Five unit test runs hit the 300 s limit (27 minutes): a test helper never sent the request body, so each posting
  test waited out its 20 s limit, and a cut run kept no output (fixed by LF.1640-1643, deployed after this run).
- The sprint was accepted at an escalation with only unit tests failing; seven defects left open (5-run mean 2).
- Two consultation and architect replies hit the token limit in the design stage (LF.1631-1632 for the former).
- The design escalation held two "opposite things" points that were false (LF.1633, deployed after this run).

## To add or improve
1. Run the reviews before a release whose sprint was accepted at an escalation (third time on 11-27/28).
