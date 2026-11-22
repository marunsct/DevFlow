# Product review: notes-api-csharp container 14 (run-edf4a423-708f-4b6c-84f1-db2e9ee54db2)

**Result (finished about 13:42 JST 11-22, started 12:08 on :8888, about 94 minutes): delivered, hidden 9 of 9, quality 8 of 8, handoff 1.0, mutation 0.42.** KPI regressions: redundant reads 0.55 (5-run mean 0.15), tool failure rate 6.6% (mean 3.7%) and 20 defects left open (mean 4.8).

- **What happened.** The first test round failed on `Program.cs line 37: The modifier 'public' is not valid for this item` (top-level statements); the fixers cleared it before LF.1226 (the C# pack's two top-level-statement rules, deployed 12:43) could be used, so it is unmeasured. The suite was disputed once (AC-18 "invalid input is refused without storing anything", AC-13 and the aggregate AC-16 "every operation works as the interface says"); a second sprint attempt closed AC-13 and AC-18 without a fixer and the aggregate AC-16 stayed `left open`, which LF.1227 (committed 11-23 08:00, not yet deployed) now stops raising or shipping as a cut.
- **Open:** redundant reads at 55% are the highest of any run this week, the suite author re-reading the same file inside a stage; mutation 0.42; DR-4 settled (the specification said two things about an empty string).
- **Other harnesses:** an aggregate requirement is tracked as the sum of its parts, not as a test of its own.
