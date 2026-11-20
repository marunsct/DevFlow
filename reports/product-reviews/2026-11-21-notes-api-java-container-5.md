# End-of-run product review: notes-api-java container 5 (2026-11-21)

Run run-426163d2-3d7a-4db5-90f2-24a08913ca4e, notes-api in Java/Spring, qwen3.6-35b-a3b-mtp@iq4_nl on :1234, 04:05-07:10 JST. Switch on: `WEB_LOOKUP_WHEN_STUCK`; LF.1202 (a repeat read is told so only while the model can still see the text) went live at 05:21.

**Score:** hidden 9 of 9, quality 8 of 8, **delivered**, handoff 1.0, no false acceptance. **178 active minutes**, 329 model calls, no fix reverted, 9 defects left open (mean about 3), mutation score 0.8. KPI flags: **identical calls 36% (mean 12%)**, 2 replies lost to the length cap, prefill-to-decode 14.2 (mean 8).

## What cost time
- The repeated reads: 85% of the reads before LF.1202 (04:50-05:21) repeated an earlier one, 61% after - lower, not low; no writes in the first 12 minutes after it. The summariser rewrites the conversation about every 3-5 model calls on a ~160K-character base, so the work order loses what it just read. `SUMMARISE_LATER_WITH_HEADROOM` (LF.1203, deployed 06:05, off) is the larger fix; this run did not have it on.
- The acceptance suite was green (27 of 27) only at the end of sprint 2's repair: two fixers worked on the last two tests for about 45 minutes (05:21-06:24), then the dispute and a suite repair.
- Everything else is the slow model: 741 tool calls over 3 hours.

## Switches
- `WEB_LOOKUP_WHEN_STUCK`: no case.

## Added value
A delivered Java product on the slower model, and the data behind the read-guard fix (91 of 102 repeat reads had lost their earlier text). The next Java run (container 6, started 07:17) has the later-summarising switch on: the direct comparison.
