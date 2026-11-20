# End-of-run product review: web-todo container 5 (2026-11-21)

Run run-42484a4f-bd51-4d3d-9d6c-6c8cb0ea80ba, web-todo (browser page), unsloth/Qwen3.6-35B-A3B-MTP-GGUF on :8888, 03:16-04:40 JST. Switches on: `FIX_ORDER_CRITERIA_FIRST`, `WEB_LOOKUP_WHEN_STUCK`.

**Score:** hidden 10 of 10, quality 6 of 6, handoff 1.0, no false acceptance; **verdict not deliverable**. 82 active minutes, 164 model calls, 3 fixes reverted (mean 0.2), 5 defects left open (mean 3), mutation score 0.5.

## Why not deliverable
- The release page probe: at a 360px-wide screen the page is 347px wider than the screen and scrolls sideways. The probe adds an item with a long name and measures; a long unbroken word without wrapping would do this. A real product defect that neither the acceptance suite nor the hidden tests check. It fits the quality of the brief's small-screen line; to be confirmed against the brief whether it asks for small screens (the probe only runs when it does).

## Fix order (`FIX_ORDER_CRITERIA_FIRST`, second arm)
- Fired at 03:58 JST: 14 defects moved ahead, 1 after. Acceptance went from 5 of 29 to all 29 passing in about 45 minutes of fix rounds (03:58-04:23) - the fastest green of the page runs; the run then spent the rest on sprint 2.
- Two page arms with the switch on (fullstack-bookmarks 2, this run) both reached full hidden marks in under two hours; the only page run without it that finished was on a different model and a different brief. A third arm on :1234 would separate the model.

## Added value
A page product green in 67 minutes, with a real small-screen defect reported honestly. Plan: with two arms and no cost seen, `FIX_ORDER_CRITERIA_FIRST` is a candidate to turn on after one :1234 arm.
