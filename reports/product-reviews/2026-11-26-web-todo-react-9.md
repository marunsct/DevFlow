# Product review: L web-todo-react container 9 (run-5071b7ef-edad-412f-8a4c-73777a339978)

**Result: delivered - hidden 10 of 10, quality 0.93 (interface 0.78, data 1.0, service 1.0), handoff 1.0; locked suite
19 of 19.** Fast delivery, parallel execution mode; started 13:10 JST 11-26, finished 17:26 JST. Mixed versions (five
deploys while it ran, each a pause and resume). This family's three runs before it had failed overnight (a model outage,
image errors, an approval wait); this one finished.

- **Sprint 1 took three attempts.** Attempt 1 left 8 defects, rooted in a production build that failed on an undeclared
  test package and a shared acceptance step (`getByLabel('Title')`) that 19 tests stopped at. Attempt 2 left 3 (the
  AC-5 status filter twice, one contrast check), attempt 3 passed.
- **Waste:**
  - Fixers left `diag.js`, `diag.mjs`, `diag2.mjs` and `diag-filter.js` in the product; the cross-file check raised one
    (`require` under `"type": "module"`) as a defect that took a fix round. Fixed by LF.1529 (name rule) and LF.1533
    (structural rule, building).
  - Paired fixers: one batch's change to one file broke a unit test the other relied on, and was reverted (third run
    today with that pattern).
  - About a third of failed calls were re-reads of held files, each refused in one call (LF.1517 as built).
- **Quality lost:** one text/background pair under the contrast minimum, and no wording for a failure shown to a person.
- **Disputes:** one locked test (the AC-5/AC-12/AC-15 filter subsets) was reclassified under dispute.
- **Advisory:** `tinypool` 1.1.1, a development-only dependency, has a critical advisory; it does not ship.
