# Review: telling a test's fault from the product's (2026-11-12)

Six point fixes in this subsystem in one day (LF.849, LF.851, LF.853, LF.854, LF.855, LF.856), plus two filed items. This
review steps back: what the cases share, what the design gets wrong, and the change to make instead of a seventh patch.

## The cases

| Case | What was wrong | Who was wrong | Cost |
|---|---|---|---|
| wordstats-cli 20 | the suite's helper `_compute_words` lost its `+`; 6 tests failed | the test (one helper) | 4 tests past the cap; 2 criteria deferred though met |
| RC15 tasks-api 1 | `auth_token` fixture used in a file that did not define it; 18 setup errors | the test (one fixture) | 2 rounds: the finding hid the reason (LF.853) |
| RC15 tasks-api 1 | the fixture copied with the same username; second sign-up got 409 | the test (one fixture) | 3 repairs + 2 past the cap; 3 rounds of a false "not changed" (LF.854) |
| web-todo 13 | delete test acted on `items.first()` under newest-first order | the test (position) | ~1 h of fix rounds on a right product |
| RC16 fullstack-bookmarks-py 1 | the harness's own check missed `setAttribute('role','listitem')` | the harness | 3 sprint re-plans at 20/20 (LF.855) |
| RC16 web-todo 1 | edit tests sought the new title inside a filter on the old one | the test (stale filter) | 9+ fix stages on a right product (LF.856) |

## What they share

1. **One cause, many failures, handled one failure at a time.** The dispute, the cap and the repair check all count
   tests. A broken helper or fixture is one cause; counted as six, it exhausts the cap and defers right criteria, and
   a repair that fixes it is judged by test bodies it never needed to touch (LF.854).
2. **The fixers are sent first.** Every case above spent fix stages before anything asked whether the test could pass.
   The dispute runs only after a fixer gives up and blames the suite. On a right product, that order is all waste.
3. **Static text checks misfire both ways.** LF.855 (a check too narrow) and the reverted position draft (too broad)
   both read source text. The checks that held all day were the ones that read a *measured failure* (LF.853's reason,
   LF.856's locator) or compared against the brief's literal form (LF.846, LF.852).

## The change to make

- **Group failures by cause before anything else.** After a test round, cluster failing tests by the shared helper,
  fixture or locator their failures and bodies name. A cluster is one cause: one dispute item, one unit of the cap, one
  repair, judged by whether the cluster's tests pass afterwards.
- **Ask "can this test pass" before sending a fixer**, for any cluster whose failure the measured checks (LF.853,
  LF.856, the existing setup and promise checks) call the test's own. Today they run inside the round but the fixers
  are dispatched in parallel; reopen first, fix after.
- **Prefer measured evidence to source text** for new checks: a failure message, a re-run alone, a dry run with the
  product stood in. Keep source-text checks for what the brief states literally.

## Order of work

1. Cause clusters (subsumes the filed shared-helper item and LF.854's case).
2. Reopen-before-fix for a test-attributed cluster.
3. Ship with LF.854-856 as one Fix batch; measure fix stages spent on right products against tonight's runs.
