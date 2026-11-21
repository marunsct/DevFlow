# Product review: notes-api-go container 5 (run-fadba1cd-d14f-499f-9e22-5db63274d566)

**Result (finished 14:11 JST, started 12:54 on :1234, about 77 minutes): delivered, hidden 9 of 9, quality 8 of 8, handoff 1.0.** KPI regressions: redundant reads 0.30 (5-run mean 0.14) and identical calls 4.0% (mean 2.5%).

- **What went well.** The product started after one fix round (start defect fixed 13:57, unit-test build failure 13:59); no reverts, no re-plan, no defect left open. The same model and server delivered Java 8 in 117 minutes against a hidden start error; Go has no such hidden-start trap.
- **What cost time.** About 55 minutes went to writing and reviewing the acceptance suite (three authoring rounds, three reviews), twice Java 8's; the fix rounds took about 15 minutes. Redundant reads are the clearest waste: 30% of reads repeated, against 14% in recent runs.
- **Open:** three lines of the interface contract were not checked at release (a write line that succeeds only when its body is accepted); counted with the earlier "contract lines no form can check" findings (PHP 8, DR-4). The server's cache is not reported on :1234, so token measures cannot be compared with :8888.
- **To measure next:** whether the suite-writing time is a pattern on :1234 Go runs (one case) and whether the redundant reads are in the suite writers (per-role audit says they re-read the contract each round).
- **Other harnesses:** a locked suite built in rounds with a reviewer is the common design; the time cost is the price of an independent suite.
