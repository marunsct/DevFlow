# End-of-run product review: Java container 4 (2026-11-20)

Run run-b668a924-8ca8-4599-acb2-a1a83ac9fb7e, notes-api in Java/Spring, model qwen3.6-35b-a3b-mtp@iq4_nl on :1234, finished 13:01 JST.

**Score:** hidden 9 of 9, quality 8 of 8, delivered, handoff 1.0, no false acceptance. 244 active minutes, 326 model calls, mutation score 0.667.

**KPI regressions flagged** (against the 5-run mean): identical calls 25% (7%), model errors 5 (0), fixes reverted 4 (1).

## What cost time
- Test rounds 0-2 went to "the product does not start": a work order dropped the held `<finalName>app</finalName>`, and the defect was left open four times before a rewrite of `pom.xml` fixed it. LF.1160 (the pack holds the jar name) and LF.1169 (a build stage is told to restore a dropped held line before it returns) were deployed during this run and target exactly this; the stage-end check did not get a chance to fire here.
- The 5 model errors are outside the harness: the owner's model on :1234 was unloaded at 10:25 JST (4 errors) and one engine error at 09:51. Nothing to fix.
- 143 identical answered calls, almost all `read_file`: 76 in the testing work order, 31 in one fixer. The read guard fires only some of the time - an unchanged 5-line file came back in full, then "already read", then in full again - probably because the guard gives the text back once the stage's history was trimmed (32 history rewrites in the run). Each repeat is small; filed to check whether the guard's memory and the history trimming agree.
- Six resumes (deploys and the model unload) restarted stages that then re-read their files.

## Features to improve
- Check the read guard against history trimming (above).
- Writing the acceptance suite took 54 model minutes at 90% reasoning; the per-role audit's suite-writer fixes (LF.1177, LF.1178) and the measured QA prompt trim aim at this.

## How others do it
Coding agents that trim history (Claude Code, Aider) keep a per-file read cache keyed by content hash, so a re-read after trimming returns a short "unchanged since you read it at step N; here are the lines you asked for" rather than the whole file, or nothing.

## Added value
A second Java run with full marks; the time lost is already addressed by fixes deployed during the run.
