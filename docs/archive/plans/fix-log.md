# Fix log (append-only)

One row per completed fix, added in the commit that makes the fix, after the rows of the archived plan
(`improvement-plan-until-2026-11-20.md`, which holds every fix to LF.1159). Newest last. Not a document to read: it is
the record `loop.sh blind-spots` and the switch gate search, and the place to look up why a fix exists. The open work
is in `docs/improvement-plan.md`.

Row format (one line): `| LF.n | what was measured | what changed | the test (proven to fail on the old code) | done |`

| id | measured | changed | test | state |
|---|---|---|---|---|
