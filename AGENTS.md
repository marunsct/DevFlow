# Agent instructions

This repo is a LangGraph / Deep Agents harness that builds software products
from a brief. It runs under a **standing, never-stopping improvement loop**:
1. Run a benchmark.
2. Audit the run.
3. Fix the harness in general.
4. Add tests.
5. Commit, push and deploy.
6. Run the next benchmark.

**Start at [docs/HANDOVER.md](docs/HANDOVER.md).** Its §0 says exactly what to
do first. Then read [docs/monitoring-handover.md](docs/monitoring-handover.md)
§0 for the mechanics and the full run history.

Rules that are never optional (details and reasons in the handover):

- **The model is the owner's.** Run `scripts/loop/loop.sh ready` before every
  run. If it does not exit 0 with `ALL READY`, start nothing. Never load a
  model or change the owner's model or settings.
- **Fixes are technology-, framework- and product-agnostic.**
  - Stack-specific guidance goes only in `src/app/plugins/seed.py` or a stack
    pack.
  - No run ids in code, comments, prompts or tests.
  - Each new prompt rule gets a test banning the whole words task, tasks,
    to-do, todo, button, click and checkbox.
- **Every fix gets a test proven to fail on the old code.** Run the full suite
  with `scripts/loop/loop.sh suite`; only the three S3 tests in
  `tests/test_codebase_seeding_api.py` may fail. Do not edit `src/` while it
  runs.
- **Deploy a verified fix into the live run** (owner instruction 2026-10-10;
  details in `docs/HANDOVER.md`).
  - In a run's first 40 minutes, a bug means: cancel, fix, deploy, restart.
  - Later: fix it in general, prove the test fails on the old code, run the
    suite, push, then `loop.sh deploy` mid-run and `loop.sh resumed`. Orphan
    recovery resumes the same run, so it is not held on a defect already fixed.
  - Only a major bug cancels a run after its first 40 minutes.
- **Keep the owner's features:**
  - dynamic agent-instruction injection;
  - the parallel/linear toggle;
  - the sprint summary;
  - work orders, templates and the Sprint Record.
- **Commit and push after every change:** `git push main harness-hardening-session`.
  The remote is named `main`. Keep both handovers current in the same commit.
- **`docs/logs.md` was removed by the owner on 2026-10-19.** Its review points are
  covered in `docs/improvement-plan.md` Part 22.4. Do not recreate it in git.
- **Secrets:**
  - Never print `.env` values.
  - Never use the admin account; the loop uses the operator account in
    `docs/HANDOVER.md` §3.
  - Never kill the owner's GPU or model processes.
- **Report times to the owner in JST** (UTC+9). Containers and transcripts log
  UTC.
