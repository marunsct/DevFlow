# Product review: wordstats-cli 18 (11-28)

run-55a9cdbb-c64b-42e3-8760-c191dc40ba47. Qwen 3.6 35B on two llama.cpp servers, local model only, parallel
execution, a second run live beside it. 03:12 to 03:48 JST. One version throughout (LF.1503-1632).

## Score
| Measure | Result |
|---|---|
| Hidden tests | 8/8 |
| Brief's edges | 6/6 |
| Verdict | delivered; handoff 1.0 |
| Locked suite | 12 passed, 0 failed |
| Mutation check | 3 of 3 caught |
| Release | completed with 17 gaps |
| Time | 35 min wall; model busy 97% |
| Model | 77 calls, 210k output tokens (48% reasoning), 1.44M input (45% from cache) |

The container 17 and inkling runs of this brief scored 6/8; this one compares words in lower case as asked.

## What went wrong or cost time
- Most of the 17 gaps are "the specification says opposite things" findings (trailing newline listed four times,
  positive integer three times); the design escalated. Whether they are real is being measured.
- The suite was locked with three findings open (no test of `--json` with `--top`; one hard-coded count; two
  identical tests).
- 45% of input from cache; redundant reads 12% against a 5-run mean of 7%.

## To add or improve
1. The contradiction findings (being checked).
2. Send an open "no test exercises this part of the criterion" finding back to the author before the lock.
