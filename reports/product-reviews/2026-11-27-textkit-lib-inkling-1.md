# Product review: textkit-lib on Inkling 2 Mini, run 1 (11-27)

Run `run-4d1f3829-9d47-4c09-bb05-9b99cc8e3895`. Failed at 09:31 JST. Hidden tests 0/1 (collection failure), handoff 0.333.

## What failed
The test runner replayed from the stored setup for "Python, no framework" crashes on any failing or erroring test
(`junit_runner.py`, joining a value that is not a list of strings). A failing acceptance test before the build is
normal, so no report was written. The harness read this as a suite that cannot load, spent 5 suite-writing rounds on
it and failed the run. The suite writer does not own the runner, so no round could have fixed it.

## Features to improve
1. A setup is proven only if its runner reports a deliberately failing test and a raising test as failed; a stored one
   that cannot is repaired or dropped before reuse.
2. A runner crash goes to the stack setup with its traceback and does not spend suite rounds.

Both are being built as LF.1594.

## How other harnesses do it
Most coding harnesses run the project's standard test runner (pytest, `unittest`, `go test`) rather than a generated
adapter, so this failure cannot occur there. The harness generates adapters to get one report format across stacks, so
it has to check the adapter's failure path itself.

## Added value
The failure is cheap to prevent (two probe tests at setup proof) and costs a whole run when it happens.
