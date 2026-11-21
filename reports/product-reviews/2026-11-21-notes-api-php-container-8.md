# Product review: notes-api-php container 8 (run-ae213a76-1f72-4d52-88be-a86d5f95b5e2)

**Result (finished 10:43 JST, started 09:09 on :8888, about 94 minutes): delivered, hidden 9 of 9, quality 8 of 8, handoff 1.0, mutation score 0.25** (mean 0.62). KPI regressions: mutation score, one fix reverted (mean 0.2), 8 defects left open (mean 1.6).

- **What cost time.** The product did not start in three attempts (about 70 minutes). The real error sat in the start output: Slim 4's `AppFactory::create()` was given a container as its first argument. LF.1205 added that cause to the Slim known errors; it was deployed at 10:14 JST mid-run and the next rounds went through to review stages and delivery. Fixers searched the web twice during the stuck rounds (3 results each); web tools were offered but never called.
- **What it shows.** Same family of defect as Java 7 (start errors invisible or misread) but here the error was visible and only the known-cause table was missing; Java's was invisible (LF.1206).
- **Open:** the contract-line design finding (five acceptance lines in no form the checker reads) was settled by DR-4 rather than fixed, and 8 defects were left open with a delivered verdict; low mutation score means the written suite is weak on this service. Both match earlier service briefs.
- **Other harnesses:** a table of framework-specific known errors is the same idea as lint rules for common misuse; it grows by case, so keep adding only general ones.
