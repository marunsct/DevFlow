# End-of-run product review: fullstack-bookmarks container 1 (2026-11-20)

Run run-5d08754b-a470-44d9-be3c-8f4baffb66d1, fullstack bookmarks (browser page and Express service), qwen3.6-35b-a3b-mtp@iq4_nl on :1234, 14:29-19:25 JST. Switches on: `WEB_LOOKUP_WHEN_STUCK`, `WEB_TOOLS_AFTER_TWO_FAILED_FIXES`.

**Score:** hidden 8 of 8, quality 7 of 7, handoff 1.0, no false acceptance; **verdict not deliverable**. 289 active minutes, 463 model calls. KPI flags: prefill-to-decode 19.6 (mean 8), 7 replies lost to the length cap (mean 3.2).

## What cost time
- **About two and a half hours on one unpassable locked test**: `[AC-4] filter is case-sensitive` expected `filter({ hasText: 'case-work' })` absent beside a 'case-Work' item; the runner's string text match ignores case and matches part of the text. Three sprint attempts went to a product that already filtered correctly, and a dispute called the test right. LF.1196 (deployed 18:38) flagged it at the next round: reopened 18:53, rewritten to `/^case-work$/` in one call, locked again 7 s later, then 44 of 44.
- The slow :1234 model: 48 replies answered from their reasoning, 7 cut at the cap.

## Why "not deliverable"
- `AC-20 page / message "Failed to delete bookmark"`: the strict contract parser took `message` as an ARIA role, so the release probe asserted `getByRole('message')`, which no product can meet, and AC-20 had no locked test to excuse it. A false blocker - being fixed (a page line naming no ARIA role, or an alert/status message, is reported as not checked).
- The browser page check: "an item added was gone after the page was reloaded". The locked reload test (which creates through the API) passed; to be checked whether the UI's add path persists.

## Switches
- `WEB_TOOLS_AFTER_TWO_FAILED_FIXES`: fired once failed fixes were counted across attempts (LF.1191-1192); offered 3 times, called 0 times.
- `WEB_LOOKUP_WHEN_STUCK`: searched "TypeError: Cannot set properties of null (setting 'textContent')", 3 results.

## Added value
Full hidden and quality marks on the larger fullstack brief, and the run that produced the `hasText` check and the run-wide failed-fix count.
