# End-of-run product review: C# container 8 (2026-11-20)

Run run-d2d6fd42-550f-41ed-b38d-698d2ae706d2, notes-api in C#/.NET, model unsloth/Qwen3.6-35B-A3B-MTP-GGUF on :8888, finished 11:57 JST.

**Score:** hidden 9 of 9, quality 8 of 8, delivered, handoff 1.0, no false acceptance. (The KPI row is re-read after the 12:16 deploy; the worker was down when the score ran.)

## What cost time
- About 30 minutes on mutants that hung the test run: each ran to the sandbox's full timeout. Fixed for the next runs by LF.1162 (a mutant's run is capped at three times the unchanged run, floor 60 s).
- Mutation gaps in one test file were sent to a fixer one at a time. LF.1163 (`MUTATION_GAPS_BUNDLED`, off until measured) sends the gaps of one file to one fixer.
- QA tried to write unit tests and product code outside `acceptance/` three times (refused, as designed); a fixer ran `dotnet test` while the terminal was withheld (refused once).

## Features to improve
- The mutation stage is the largest remaining time sink on compiled stacks: measure `MUTATION_GAPS_BUNDLED` on the next C# and Java runs.
- Cache share is 74% of 4.6M input tokens; `opening_changed` x9 cost 190k uncached tokens, mostly in principal_architect (20% cached). The opening of that stage changes between its calls; worth a look in the next prompt-cache review.

## How others do it
Mutation tools (Stryker, PIT) cap each mutant by a multiple of the baseline test time and batch survivors by file; LF.1162 and LF.1163 bring the harness to the same shape.

## Added value
A compiled stack delivered with full hidden and quality marks; the fixes found here make the same work cheaper rather than change the outcome.
