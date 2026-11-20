# Review: how a sprint ends (2026-11-14)

Four fixes in one day to the decisions at a sprint's end: LF.891 (a sprint failing only later sprints' tests is not
sent back), LF.903 (a green best attempt put back settles), LF.904 (an accessibility remedy that kept a green sprint
open) and LF.905 (a locked test lost is not bought back with unit tests). Three came from one run, L fullstack-bookmarks
8, whose sprint 1 took four attempts with its locked suite at 28 or 29 of 29 throughout, and shipped 8/8 hidden.

## What the cases share

1. **The definition of done is the locked suite, but four rules weigh it against other things one at a time.**
   The net-gain rule weighed acceptance and unit tests as equals (LF.905); the settle rule read the measurement before
   the best attempt came back (LF.903); the measured-suite gate counted later sprints' tests (LF.891). Each rule was
   right alone and wrong in its place in the sequence.
2. **The end of an attempt is decided from more than one measurement.** The round's own run, the best attempt's
   saved result and the run made after a put-back can each be the "last result"; which one a rule reads depends on
   where it sits in `workflow`'s re-plan path.
3. **Page findings are product defects, but they block a green sprint with no remedy attached** (LF.904's case): the
   remedy list grows one rule name at a time.

## The change to make instead of a fifth patch

- **One decision at the end of an attempt, from one measurement.** Put the best attempt back first (if worse), measure
  once, then ask in order: are all due locked tests green (later sprints' and deferred criteria excluded)? Are the
  open defects only unit tests or findings read from files? Then settle; else re-plan. LF.891, LF.903 and the settle
  rule become three clauses of that one function, with one test table.
- **The locked suite outranks everything a worker wrote**, stated once in `net_gain` and in the decision above, not
  rule by rule.
- **Accessibility remedies by rule family** (which elements may hold which), not by rule name, if a further name
  appears.

Order: build the single end-of-attempt decision at the next run boundary after the RC count, with a test per clause
that fails on the old code; it is a quality change (always on).
