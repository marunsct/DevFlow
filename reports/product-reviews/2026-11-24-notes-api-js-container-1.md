# Product review: notes-api-js container 1 (run-031094d4-22d6-435e-a11d-9a065098f921)

**Result (started 14:26 JST 11-24 on :8888, finished 15:16, 50 minutes; mixed versions: bundles 1 and 2 deployed into it at 14:32 and 15:09): delivered, hidden 9 of 9, quality 7 of 8, handoff 1.0, mutation 0.67 (0.92 with the unit tests); locked suite 20 of 20.**

- **What happened.** Planning with one architecture review sent back once, then an escalation. Three suite-authoring passes, then one sprint with four test rounds. All four defects were fixed in short stages:
  - The product did not start: the data directory was refused when relative (15 calls).
  - Two unit tests failed: rewritten in tests-only mode.
  - A title of only spaces was accepted: the emptied-field probe caught it and the rewrite fixed it.
  - One mutation went unnoticed: a test was added.
  - Then the security, advice and milestone reviews passed.
- **Lost: `test_a_note_deleted_twice_is_404_the_second_time` (KeyError 'id').** The product refuses an empty `body` with 400. The brief refuses only an empty title; the specification said "body: string (required)", and the first draft read that as non-empty.
  - **Sum across scored runs:** the same lost test in 5 runs of 5 families (csharp, go, java, ruby, js).
  - **Fix building (LF.1273):** a kept-when-empty probe, the twin of the emptied-field probe. Where the brief names the fields refused empty, the record's other text fields must be kept when empty.
- **Efficiency:** the redundant-read rate (0.19) and identical-call rate (0.13) were above their 5-run means (0.11 and 0.075). Four specialist commands were refused as withheld tools, and the stage went on.
- **Bundle 2 at work:** the deploy at 15:09 landed in the milestone reviews. No fix round ran after it, so its fix-judging parts did not fire here.
