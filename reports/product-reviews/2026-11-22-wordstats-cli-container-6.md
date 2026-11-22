# Product review: wordstats-cli container 6 (run-2a421e80-ca6e-4a72-a3a6-519762830b7e)

**Result (finished about 13:25 JST 11-22, started 12:17 on :1234, about 68 minutes): delivered, hidden 8 of 8, quality 6 of 6, handoff 1.0, mutation 0.80.** KPI regressions: tool failure rate 14.5% (5-run mean 3.6%) and identical calls 4.4% (mean 1.9%).

- **What happened.** Three suite-authoring rounds, a first test round with the counting and ordering criteria open (AC-11 counts, AC-12 top words), two fixers alternating, a suite dispute that reclassified two locked tests (`test_ac1_basic_counts`, `test_ac3_json_counts`) and a delivery; DR-8 settled (the specification said two things about `--json`).
- **Cost.** The highest tool failure rate of the week (14.5%), from the two fixers repeating failing edits; the dispute path did the settling, as on wordstats-cli 4 and 5: the counting definition is the contested area of this brief across three runs.
- **Open:** a check on how the specification and the unit tests define a word before the suite locks (three runs of the same dispute).
- **Other harnesses:** a definition contested between sections is normally settled once in the specification, not re-argued in each run's suite.
