# Product review: wordstats-cli container 7 (run-cee2f308-d38f-4559-81be-03a21291e811)

**Result (started 08:14 JST 11-24 on :1234, finished 08:50, about 36 minutes): delivered, hidden 6 of 8, quality 6 of 6, handoff 0.83, mutation 1.0.** KPI regressions: hidden 0.75 (5-run mean 0.95), handoff 0.83.

- **Lost:** `test_lists_the_most_frequent_words` and `test_json_top_words` - the product printed "The 3" where the hidden tests expect "the 3". The brief says words are compared in lower case; the intake left "what case are words shown in" as the brief states it, and the locked tests used lower-case words only, so nothing in the run measured it.
- **Recurring (sum-recurring-notes):** the same shape on this brief in at least three runs (LF.780 told the architect a comparison rule says how values are shown; the suite writer and reviewer were never told to test it). LF.1255: a criterion comparing values in a normal form is tested with values in another form, expecting the normal form shown.
- **Gap noted:** 14 contract lines follow none of the contract's forms (command lines with quoted output), so the release could not check them.
