# End-of-run product review: notes-api-csharp container 10 (2026-11-21)

Run run-bdea5f76-b2aa-4dd6-ae0f-0a7a1ded3ced, notes-api in C#/ASP.NET, unsloth/Qwen3.6-35B-A3B-MTP-GGUF on :8888, 06:37-08:11 JST. Switches on: `WEB_LOOKUP_WHEN_STUCK`, `SUMMARISE_LATER_WITH_HEADROOM`.

**Score:** hidden 9 of 9, quality 8 of 8, **delivered**, handoff 1.0, no false acceptance. **91.7 active minutes** (C# 9 on :1234: 73; C# 8: about 80), 203 model calls, **4 fixes reverted** (mean 1), 10 defects left open (mean 4.4), mutation score 0.417 (mean 0.86).

## What the run showed
- Four fixers were reverted by the harness for breaking the build (two at 07:39 and 07:45 JST, both reverts of an attempt at the last criterion AC-18, invalid input refused without storing anything): one dropped a SQLite using-directive's namespace (`Microsoft.Data`), one wrote a C# static local function the compiler refuses (CS8421). The revert and checkpoint safeguards held; each cost about 6-10 minutes. A fixer's compile error is the product's own, so no pack fact was added.
- The last criterion took three sprint attempts and a dispute; all 20 acceptance tests were green at 08:12 JST.

## `SUMMARISE_LATER_WITH_HEADROOM`
- On, but no `summarised_later` record and only 1 history rewrite in 94 minutes: the :8888 window is large and its requests never reach even the usual trigger, so the switch had nothing to change here. The test of it is on :1234 (notes-api-java container 6).

## Added value
A delivered C# product in 92 minutes with full marks; a clean demonstration of the revert safeguards on four breaking fixes. Mutation score 0.42 again says the tests prove the interface more than the code.
