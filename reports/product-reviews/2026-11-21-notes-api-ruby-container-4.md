# Product review: notes-api-ruby container 4 (run-a7de0505-a9c7-4416-9f70-52324ccf6505)

**Result (finished 18:50 JST, started 17:58 on :8888, about 52 minutes): delivered, hidden 9 of 9, quality 8 of 8, handoff 1.0, mutation score 0.46.** KPI regressions: mutation score 0.46 (5-run mean 0.74) and 11 defects left open (mean 4.2).

- **What happened.** The first sprint's fix rounds ended with remediation exhausted at 18:31 (a regression in `spec/app_spec.rb`, POST /notes with invalid data); the suite was reopened by dispute and re-authored, the second round fixed the server-error defect on `POST /notes` and the spec's load error in one attempt each, the milestone passed the security and advice reviews and the release delivered. LF.1211 (deployed 18:35) was live for the second sprint; no contract-line finding appeared in it.
- **What cost time.** About 35 minutes in the first sprint's fix rounds, and the suite re-authoring; the 11 open defects are the first sprint's mutation and regression defects that the dispute settled rather than fixed.
- **Open:** a locked test reclassified under dispute (`[AC-14][AC-15] GET /health returns 200 with status ok`) and DR-6, a design finding about response bodies (the specification said a delete returns no body in one section and asserted a body in the test cases). Mutation score is below the mean on a service brief, as on PHP 8 (0.25) and tasks-api 10; counted again, now six service runs.
- **Other harnesses:** a locked-suite dispute that reopens a test the product contradicts is the cheap path; ours took one extra authoring round.
