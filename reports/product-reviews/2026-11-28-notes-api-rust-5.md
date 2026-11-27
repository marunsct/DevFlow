# Product review: notes-api-rust 5 (11-27/28)

run-1fb341dc-89c6-4333-bae7-0ff14eb6362e. Qwen 3.6 35B on two llama.cpp servers, local model only, parallel
execution, a second run live beside it. 21:55 to 01:00 JST. Mixed versions: four deploys into it, the last
(LF.1625-1627) at 00:31.

## Score
| Measure | Result |
|---|---|
| Hidden tests | 0/9 |
| Brief's edges | 0/8 |
| Verdict | failed: the sprint was planned again 3 times and not accepted; locked suite 2 passed, 20 failed |
| Handoff | 0.43 (no readme, start or test notes, or CI file) |
| Time | 185 min wall; model busy 91% |
| Model | 515 calls, 802k output tokens (62% reasoning), 18.6M input (60% from cache) |

## What went wrong or cost time
- For most of the run the product did not compile: the extractor was written under `#[async_trait]` as for axum 0.7,
  a `tower::Limit` that does not exist was imported, and state was given to a `Router<()>`. The pack named none of
  these until LF.1625-1627, two and a half hours in.
- Every hidden test fails on database setup: "Execute returned results - did you mean to call query?" (a statement
  that returns a row run through `execute`, to be verified; a fix is being built).
- The last rounds left `tower::Limit` in place with its known cause in the request, and one fix was reverted for
  breaking the build.
- Six fixes reverted (5-run mean 1).

## To add or improve
1. The database setup cause in the Rust pack (being built).
2. Why a rewrite given the known cause left the import (being checked).
