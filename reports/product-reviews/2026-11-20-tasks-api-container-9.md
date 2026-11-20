# End-of-run product review: tasks-api container 9 (2026-11-20)

Run run-bcf3404e-2733-4c2d-a70d-0782989a750b, tasks-api in Python, unsloth/Qwen3.6-35B-A3B-MTP-GGUF on :8888, 21:24-23:45 JST. Switches on: `QA_PROMPT_TRIMMED`, `REVIEWER_SHAPED_PLUGIN_CONTENT`, `LEAD_REPLAN_REQUEST_SMALLER` (third arm).

**Score:** hidden 10 of 10, quality 7 of 7, **delivered**, handoff 1.0, no false acceptance. **135.8 active minutes** (tasks-api 8: 83.5), 257 model calls, mutation score 0.417, 9 defects left open. KPI flags: replies lost to the length cap 2 (mean 0.2), identical calls 6.8% (mean 2.6%).

## Where the time went
- All 38 acceptance tests passed by 22:01 JST (37 minutes in). The remaining 100 minutes went on sprint 2: two lead re-plans for one unit-test regression (`test_signup_malformed_json`, passed before a fix was kept, then failed) and a mutation finding, then the end-of-sprint reviews twice.
- Two replies hit the length cap, both in the security advice review.
- The testing role was refused 13 writes outside its own files (the same pattern as every run today).

## The prompt-size switches (three arms)
- `QA_PROMPT_TRIMMED`: suite writer and review 10.5 model minutes over 21 calls (arm 2: 6.6; without it: 9.2-10.4). Across arms 2 and 3 the trim shows no saving (8.6 against 9.8 minutes, within run-to-run noise); all three runs delivered full marks. No evidence it helps; it stays off.
- `REVIEWER_SHAPED_PLUGIN_CONTENT`: fired each time; no cost seen.
- `LEAD_REPLAN_REQUEST_SMALLER`: fired on every lead re-plan; its effect on lead calls is not separable from the sprint's own length.

## Added value
Full marks again on the largest local brief, and a closed question: the QA trim is neutral on time, so it is not worth switching on.
