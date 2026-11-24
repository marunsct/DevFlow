# Product review: notes-api-csharp container 16 (run-c46d5d9a-7ca1-483a-a6a8-50df08625f3f)

**Result (started 00:23 JST 11-25 on :8888, finished 01:03, 40 minutes; mixed versions - LF.1296-1298 deployed into it at 00:44): delivered, hidden 9 of 9, quality 8 of 8, handoff 1.0; locked suite 10 of 10.**

- **The first run with stack facts and the toolchain-fit check (HK.1-HK.2).** `.harness/stack-facts.json` named each dependency's newest release and the newest this toolchain builds.
  - Microsoft.Data.Sqlite's newest, 11.0.0, needs a newer .NET than SDK 8.0.428; the sheet named 10.0.15. The NU1202 case took several rounds on an earlier C# run.
  - The product pinned 8.0.11, which fits.
- **The probes asked what they should.**
  - The kept-when-empty probe asked 3 writes and probed all 3 (on Hono, before LF.1283, it asked nothing).
  - The round-trip probe probed 2, including the long value LF.1298 now judges.
  - Nothing was lost.
- **Outbound gate (HK.5):** one registry query left the machine, through the gate.
