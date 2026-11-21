# Product review: textkit-lib container 4 (run-7b7e79f9-1a1f-47e3-afda-eab01b94b042)

**Result (finished 17:55 JST, started 17:34 on :1234, 21 minutes): delivered, hidden 8 of 8, quality 7 of 7, handoff 1.0, mutation 0.67.** KPI regressions: mutation score 0.67 (5-run mean 0.97) and prefill-to-decode ratio 8.4 (mean 4.4).

- **What happened.** One mutation defect (a deliberate change at `textkit/__init__.py` line 40, `or` made `and`, that no test noticed) in the first test round; one fix; the milestone passed the security and advice reviews and the release delivered. The fastest delivery of the day and the second textkit-lib run on :1234 (container 3 took 14 minutes on :8888).
- **What cost time.** Nothing worth naming; the architect and the suite stages took most of the 21 minutes.
- **Open:** a design finding settled by DR-4 (the specification said, in two sections, both "no leading or trailing hyphens" and a rule that strips them: contradictory only in wording); mutation score below the mean on a small library brief, where earlier runs were 1.0.
- **Other harnesses:** a mutation check on small briefs is the cheap way to find a test that cannot fail; ours found one and the fixer closed it in one attempt.
