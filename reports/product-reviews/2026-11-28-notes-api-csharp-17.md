# Product review: notes-api-csharp 17 (11-27/28)

run-31be509b-5f19-42d9-9add-e303e466b10c. Qwen 3.6 35B on two llama.cpp servers, local model only, parallel
execution, a second run live beside it. 20:55 to 00:09 JST. Mixed versions: LF.1614-1618 deployed into it at 22:21,
LF.1619-1624 at 23:27.

## Score
| Measure | Result |
|---|---|
| Hidden tests | 9/9 |
| Brief's edges | 8/8 |
| Verdict | delivered; handoff 0.857 (missing: start reads its port) |
| Locked suite | 18 passed, 0 failed |
| Mutation check | 6 of 6 caught |
| Release | completed with 10 gaps |
| Time | 194 min wall; model busy 61%, neither 34% |
| Model | 382 calls, 673k output tokens (69% reasoning), 13.0M input (67% from cache) |

## What went wrong or cost time
- Four fixes were reverted (5-run mean 0.4): each mutation fixer's last write left the unit tests unable to compile,
  every test then counted as broken, and no later fixer was given the compiler's errors (fixed by LF.1619-1623).
- About 11 minutes went to unrecorded calls that re-asked for an answer after a reply holding a code block beside a
  tool call (fixed by LF.1624). Idle time was 65 minutes in all, much of the rest the harness's own measuring.
- `start.sh` does not set the port and data folder defaults two specialists' adopted advice asked for; the handoff
  check reports it too.
- Three mutation findings ship as gaps. Tool failure rate 9.7% against a 5-run mean of 3.4%, mostly re-reads refused
  in fix stages.

## To add or improve
1. Record the no-tools re-ask in the transcript, so its time is not counted as idle.
2. Keep a fix stage's last call for running the test it last edited.
3. Hold `start.sh` to the port rule at the milestone, where the specialist's advice is checked.
