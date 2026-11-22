# Lessons review, 2026-11-22 (owner instruction: approve the valid ones, reject the incorrect ones)

Fifteen proposed lessons (L-31 to L-45) were read against the evidence each one keeps. A lesson reaches a prompt only once
approved, a few per call, so the question for each was: does the evidence show the failure the rule answers, and would the
rule do what it says in the stage that receives it? Decided by Claude on the owner's instruction (recorded as the decider in the store).

## Approved (8)

| Lesson | Stack | Rule | Why |
|---|---|---|---|
| L-32 | node-http-api | add every imported package to the manifest in the same change | Real case: `morgan` imported in `src/app.js` and declared nowhere. |
| L-33 | browser-react | same | Real case: `@testing-library/user-event` imported in `tests/app.test.tsx` and not declared. |
| L-35, L-36, L-37, L-38, L-40, L-42 | go, java, csharp, php, ruby, rust | after more than two fix attempts: read the failing test's assertion and the code path it reaches before the first edit, change what the evidence names, run that test again | Eleven runs show defects that took 3 to 15 attempts, mostly "the product does not start". The measured fixes that worked (Java 9, tasks-api 12 and 13) read the printed error and changed what it named; the rule says that. Caveat: in the one-file rewrite mode a fixer cannot run a test, so "run it again" applies only where tools exist. |

## Rejected (7)

| Lesson | Why |
|---|---|
| L-31 (python-library), L-45 (browser-javascript) | The evidence is wrong. The check flagged `textkit` (the product's own package) and `glob` as undeclared imports, from `tmp-inline-<hash>.py` and `.cjs` files, which are the harness's scratch files for a command's inline code, not the product. The rule itself is fine and stands through L-32/L-33; these two had no real case. The scan now skips those files (LF.1225). |
| L-34, L-39, L-41, L-43, L-44 (reverted fix: run the unit and acceptance suites before answering) | The evidence shows reverts caused by a fix that left the product not building or not starting, which a build or start check catches; running the whole acceptance suite inside a fix attempt costs minutes, is not available in every stage, and the harness already runs both suites after every fix and reverts what breaks. The rule would add cost for a failure it does not address. |

## Follow-up built

- **LF.1225:** the undeclared-import scan skips the harness's `tmp-inline-<hash>.<ext>` scratch files (a test fails on the old code). Before it, any inline command's scratch file could raise a dependency defect on the product and propose a lesson from it.
- The two approved rule texts are two lines each and use none of the banned words (the store checks this when a lesson is proposed).
