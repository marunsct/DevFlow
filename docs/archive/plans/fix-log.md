# Fix log (append-only)

One row per completed fix, added in the commit that makes the fix, after the rows of the archived plan
(`improvement-plan-until-2026-11-20.md`, which holds every fix to LF.1159). Newest last. Not a document to read: it is
the record `loop.sh blind-spots` and the switch gate search, and the place to look up why a fix exists. The open work
is in `docs/improvement-plan.md`.

Row format (one line): `| LF.n | what was measured | what changed | the test (proven to fail on the old code) | done |`

| id | measured | changed | test | state |
|---|---|---|---|---|
| LF.1160 | Java container 4: a work order rewrote `pom.xml` without `<finalName>app</finalName>`; the build made `notes-api-1.0.0.jar` and every start said "Unable to access jarfile target/app.jar" for a whole attempt (0/18), while fixers worked on the routes | the Spring pack holds `<finalName>app</finalName>` in `pom.xml` (`required_signatures`): a pom without it is a pack-contract defect naming the file and the line | `tests/test_a_spring_build_keeps_the_jar_name_its_start_runs.py` (fails on the old pack) | done |
| LF.1161 | (WL.7) the private search had refused every query for weeks and nothing noticed: the container's health check tests only that it is up | `loop.sh ready` (and `loop.sh lookups`) asks each outside lookup source live - Stack Exchange, GitHub issues, the private search, a package registry - one line each above the model's verdict, a warning never a block; the verdict stays the last line and its exit status is kept | `tests/test_every_lookup_source_is_asked_before_a_run.py` (fails on the old `ready`) | done |
| LF.1162 | C# container 8: a mutation finding's check made the unit tests never return, and each check waited out the whole 10-minute test limit - about 30 minutes after the product passed every criterion | the unchanged unit run is timed first and each run with a deliberate change (the finding's check and the sprint probe) is held to three times it plus 30 s, at least 60 s (`sandbox.capped`); a change whose run is cut off counts as noticed, as before | `tests/test_a_change_that_hangs_the_tests_is_cut_off_early.py` (2 fail on the old code) | done |
