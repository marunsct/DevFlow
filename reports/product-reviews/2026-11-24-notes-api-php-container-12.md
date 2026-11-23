# Product review: notes-api-php container 12 (run-4702bef3-27ed-4040-a4cc-da9ad2977147)

**Result (started 04:51 JST 11-24 on :1234, finished 06:48, about 117 minutes; mixed versions to 52e7797f): not deliverable, hidden 9 of 9, quality 7 of 8, handoff 1.0, mutation 0.45.** KPI regressions: tool failures 6.6% (mean 3.5%), identical calls 8.8% (mean 3.9%), 2 replies lost to the cap, 4 fixes reverted (mean 0.6).

- **Lost:** `test_a_null_or_blank_title_is_refused_and_nothing_is_stored` - and the run's own release probe found the same fault: `POST /notes` with a title of only spaces (or a number) answered 500 with Slim's HTML error page, because the store threw `InvalidArgumentException` and the route never caught it. The defect stayed open through two attempts of one sprint (re-planned twice); the verdict is not deliverable because it was left open.
- **Fix from this run:** LF.1252 - the Slim pack's known errors now name the cause of a "Slim Application Error" (validate the body in the route, answer 400/422 with JSON, catch what the store throws), deployed 06:51 JST after the run ended.
- **What the new probes did:** the emptied-field and edge probes raised the blank title before release (LF.1242/1249 family): the harness found the fault the hidden test checks; the fixers could not close it.
- **Open:** four specification contradictions settled by rulings (business logic placement, body fields, response body, concurrent writes).
