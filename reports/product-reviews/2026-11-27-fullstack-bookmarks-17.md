# Product review: fullstack-bookmarks 17 (11-27)

run-a753551e-e1f4-435c-b4be-d90b18ecbbb1. Qwen 3.6 35B on two llama.cpp servers, local model only, parallel
execution, a second run live beside it. 18:39 to 21:54 JST. Mixed versions: LF.1606-1607 deployed into it at 19:25,
LF.1608-1613 at 20:28.

## Score
| Measure | Result |
|---|---|
| Hidden tests | 8/8 |
| Brief's edges | 7/7 |
| Verdict | not deliverable; locked suite 17 passed, 1 failed |
| Mutation check | 10 of 12 caught (0.82) |
| Release | completed with 8 gaps; AC-9 deferred as unpassable; AC-2 and AC-9 reclassified under dispute; no code, milestone or security review ran |
| Time | 195 min wall; model busy 93% |
| Model | 417 calls, 1.05M output tokens (66% reasoning), 14.3M input (60% from cache) |

## What went wrong or cost time
- Three locked tests could not pass for any correct product: AC-9 narrowed to list items by a title both of its
  records held; AC-2 and AC-11 kept titles starting with a prefix none of their records had. Fix stages took 176
  calls and 112 of 182 model minutes, much of it on these (fixed by LF.1614-1618, deployed after this run ended).
- Two fixers diagnosed the test in their reasoning, used every call and answered nothing.
- The dispute was shown the suite cut at 16,000 characters, without the file holding AC-9 and AC-11.
- One builder reply looped for 32,000 tokens; its cut-off file write was run and stopped only by the other builder's
  ownership of the file, and the broken version was handed to the owner (fixed by LF.1608-1610).
- Tool failure rate 12.5% against a 5-run mean of 4.9%: refused and repeated edits.

## To add or improve
1. A fixer that reaches its last call with nothing changed should be asked for its blocker in one call without tools.
2. Run the reviews before a release whose sprint was accepted at an escalation (also seen in notes-api-java 13).
