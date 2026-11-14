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

## Follow-up 2026-11-14: one run, eight fixes

L tasks-api 13 (10/10 hidden in the end) and L textkit-lib 9 (8/8) produced eight more fixes in this subsystem in one
afternoon. They confirm the review above, and add one cause it did not name.

| Fix | What the harness did wrong | Which of the shared causes |
|---|---|---|
| LF.893 | a failing unit run's defect showed frames, not errors; 20 failures of 2 causes read as one list | 1: one cause, many failures |
| LF.894, LF.895 | a 401 and an empty list on a shared service were charged to the product (LF.889 read only a 409) | 1, and 3: a measured check widened |
| LF.896 | a run-only testing order quoting a criterion read as writing tests | (planning, not attribution) |
| LF.897, LF.898 | the put-back of tests a repair was not sent for restored broken calls to a helper the repair had changed | **new: tests judged one at a time, their shared code ignored** |
| LF.899 | a deferred criterion's defect still went to fixers; one fix broke 37 tests | **new: a criterion's deferral not consulted** |
| LF.900 | a hand-counted expected text; the dispute judge counted the slice the same wrong way | 2: the judge asked before a measured check |

What held: every check that read a measured failure (LF.893-895, LF.900) fired on the live run and moved the score
(tasks-api 34 -> 44 of 48 tests; textkit 53 -> 54 of 54). The dispute judge, a single model reply, was wrong twice
(a sign-up it called 201 that the test never checked; text[:8] counted as 9 characters).

What it adds to the change proposed above:

1. **A suite file is the unit, not a test.** A helper in a file's head is shared by its tests; a repair or a put-back
   that treats tests one by one leaves the file inconsistent (LF.898). The cause clusters proposed above should be
   formed per file and per helper, and a put-back should restore or keep a file's head together with the tests that
   call it.
2. **Every gate reads the criterion's state.** Deferred, beyond repair, later sprint and reclassified are four records
   of the same fact ("no fix stage's in this run"), read by different gates at different times (LF.899). One function
   answering "is this criterion any fixer's now?" should be what every gate asks.
3. **Measured before judged** stands: the dispute judge is asked only about failures no measured check explains, and
   is shown what those checks found.

Order, unchanged in spirit: (1) cause clusters per file and helper, subsuming LF.897-898's rules; (2) one
"whose is this criterion" answer for every gate, subsuming LF.899; (3) the judge shown the measured findings. Each is
a quality change (always on) with a test that fails on the old code; build at the next run boundary after the RC count.
