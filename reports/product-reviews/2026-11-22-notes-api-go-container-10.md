# Product review: notes-api-go container 10 (run-c4649ed6-a882-4536-a3a4-4c41a430b5dc)

**Result (finished 01:08 JST, started 00:08 on :8888, about 60 minutes): delivered, hidden 9 of 9, quality 8 of 8, handoff 1.0.** KPI regressions: redundant reads 0.27 (5-run mean 0.18), identical calls 5.4% (mean 2.1%) and two fixes reverted (mean 0.2).

- **What happened.** The Go pack was chosen again (LF.1217: no `stack_setup` stage) and the layout stayed flat (`main.go`, `server.go` and later files all `package main`, LF.1218), the second Go run in a row to hold it. The first sprint's product did not build: the compiler reported `undefined: json` (87 times), `undefined: strings` (58), `undefined: strconv` (29), standard packages used without their imports, and then `Note redeclared in this block`; two fixes were reverted for code the compiler rejects and the sprint was planned again at 00:44. The second attempt started the product and the milestone passed its reviews.
- **What cost time.** About 35 minutes of compile errors in the first sprint; the import rule (LF.1219, deployed 00:51) did not reach this run's causes: the missing imports had cleared before it. 
- **Open:** DR-6 settled (the specification's product scope and its request-body section disagree); the redeclared name; a mutation score was not recorded for this run. Go now has two flat-layout runs (Go 9 and 10) after three that split.
- **Other harnesses:** a build step that runs `goimports` before the compiler removes the whole class of missing-import errors; ours leaves it to the fixer.
