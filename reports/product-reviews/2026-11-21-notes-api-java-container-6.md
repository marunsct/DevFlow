# End-of-run product review: notes-api-java container 6 (2026-11-21)

Run run-f7668f78-1b3e-43bd-a43f-59bf47bacb50, notes-api in Java/Spring, qwen3.6-35b-a3b-mtp@iq4_nl on :1234, 07:17-08:58 JST. Switches on: `WEB_LOOKUP_WHEN_STUCK`, `SUMMARISE_LATER_WITH_HEADROOM`.

**Score:** hidden 9 of 9, quality 8 of 8, **delivered**, handoff 1.0, no false acceptance. **94.2 active minutes**, 133 model calls, no fix reverted, 5 defects left open, mutation score 0.571. KPI flag: redundant reads 21.7% (mean 11.9%).

## Against notes-api-java container 5 (same brief, model and harness except LF.1202-1203)
| | Java 5 | Java 6 |
|---|---|---|
| Active minutes | 178 | 94 |
| Model calls | 329 | 133 |
| Identical-call rate | 36% | (redundant reads 21.7%) |
| History rewrites | 29 | 13 |
| `summarised_later` records | - | 1 |
- Java 6 was about half as long and used 40% of the model calls. The later-summarising switch fired once (at 08:28 JST, 44,267 tokens); its trace showed it buys 8,067 tokens of input room on this model, and the rewrite rate per minute was close to Java 5's. So the saving is mostly not the switch: Java 6 met fewer defects (acceptance was green at 08:10, 53 minutes in) and Java 5 had two fixers on two criteria for about 45 minutes. One pair of runs; not attributable.
- Redundant reads fell from 85% to 22-61% after the read-guard fix (LF.1202); still the largest single waste.

## Added value
Proof that a Java delivery can take 94 minutes on :1234; the measurement of the switch is "fired once, small room". `REPLY_ROOM_SIZED_PER_ROLE` (LF.1204), the larger lever, is on for the next Java run.
