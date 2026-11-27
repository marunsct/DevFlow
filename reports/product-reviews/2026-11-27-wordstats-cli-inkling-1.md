# Product review: wordstats-cli on Inkling 2 Mini, run 1 (11-27)

Run `run-af51e4c9-8670-4b3a-a350-22de1a1f4c64`. Completed 09:52 JST, parallel mode, several deploys during the run.
**Hidden 6 of 8, accepted by the harness (a false acceptance).** Handoff 1.0, mutation score 0.56 (5-run mean 0.89),
160 active minutes. Quality: no part applies to a command-line product.

## The lost tests
The brief says words are compared in lower case; the product printed the first spelling seen (`The` where `the` is
expected). The UI/UX adviser recommended keeping the spelling (UX-3), the specification adopted it as a choice "the
brief leaves open", and the tests followed the specification. The same loss was seen on 11-25 with another model
(LF.1317), so the reading is not specific to this model.

## Features to improve
1. Advice that changes what the product prints, where the brief states how values are compared, needs a check against
   that sentence before it is adopted (why LF.1317 did not stop it is to be checked).
2. A UI/UX consultation for a command-line product added no checked value here and led to the loss; measure its value.
3. The low mutation score says the locked tests are weak on this run.

## How other harnesses do it
Spec-first harnesses commonly require each assumption to quote the requirement it fills; an assumption that contradicts
a quoted sentence is rejected.

## Added value
It cost the two hidden tests on this run, on a family that has lost them before.
