# End-of-run product review: tasks-api container 8 (2026-11-20)

Run run-17363b6a-5976-4a32-b027-c198e8ea0cdb, tasks-api in Python, unsloth/Qwen3.6-35B-A3B-MTP-GGUF on :8888, 18:38-20:12 JST. Switches on: `QA_PROMPT_TRIMMED`, `REVIEWER_SHAPED_PLUGIN_CONTENT`, `LEAD_REPLAN_REQUEST_SMALLER` (the second measuring arm).

**Score:** hidden 10 of 10, quality 7 of 7, **delivered**, handoff 1.0, no false acceptance. **83.5 active minutes** (tasks-api 5: 175, tasks-api 6: 110), 250 model calls, mutation score 0.818. KPI flags: redundant reads 30% (5-run mean 18%), tool failures 4.9% (mean 3.2%; mostly work-order ownership refusals).

## The switches (second arm)
- `QA_PROMPT_TRIMMED`: suite writer and review 6.6 model minutes over 44 calls, against 9.2 and 10.4 without it; the first arm's 52 came from the suite-repair bugs fixed since.
- `REVIEWER_SHAPED_PLUGIN_CONTENT`: fired in the reviews (1,268-4,271 characters left out); no cost seen.
- `LEAD_REPLAN_REQUEST_SMALLER`: fired for the first time (19:17 JST re-plan, sprint files held whole).
- To watch: redundant reads rose to 30%; a shorter prompt may send agents to read what it no longer says. One more arm, with the reads per stage compared, before any goes on.

## What the run showed
- The redesigned suite repair (LF.1190): a dispute found 4 locked tests wrong; the suite was reopened and locked again in 43 seconds (tasks-api 7: about 45 minutes open).
- The product did not start after drafting: one backend work order tried to write a file the plan gave the other (refused twice) - the plan's file split, not a harness fault.

## Added value
The fastest tasks-api delivery today with full marks, on the prompt-size switches and the redesigned suite repair together.
