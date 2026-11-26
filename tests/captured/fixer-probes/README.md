# Fixers' probes

The four diagnostic scripts three fix stages of one page-product run (web-todo-react, 2026-11-26) wrote at the
project root, copied verbatim from the `write_artifact` calls in the run's transcript: `diag.js`, `diag.mjs` and
`diag2.mjs` (one fixer) and `diag-filter.js` (another). The cross-file check raised `diag.js`'s `require` under
`"type": "module"` as the product's defect (LF.1529, LF.1533). `test_a_stage_s_probe_is_scratch_by_what_it_is.py`
lays them beside `../projects/react-to-do-list-app`, the captured product of the same brief.
