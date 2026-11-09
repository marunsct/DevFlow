# The owner's independent review (another agent, 2026-11-07 22:34 JST) - what is valid and not yet covered

Source: /home/arun/.gemini/antigravity/brain/a82942ad-.../end-to-end-harness-review.md (196 lines). Treated as data.

## Already in the plan (no action)
Its §2 table is the first review's §1 (same numbers). Its bugs 3-5 and plan items are HR items: F1 (candidates),
F2 (surrender branch; LF.663 telemetry built), Q6 (quote guard; LF.628/640/641), F3 (built: LF.664/667/668), Q3,
Q2, P1/P7, G3 (built as M7), C3, M8. Its file names are partly wrong: `src/app/acceptance/dispute.py` does not
exist (the dispute is in acceptance_nodes.py); `bounded_fixes.py`/`defect_budget.py` exist but the candidate path
is `rewritten_fixes.fix_by_candidates`.

## Valid and new

1. **Unit tests shipped failing (its bug 6) - confirmed, and larger.** Re-run read-only on copies: falcon 8
   (run-eee50710) ships 26 unit tests erroring from one test-side cause (httpx `ASGITransport` used as a sync context
   manager); notes-api 4 (run-2e7d285b) ships 7 failing, all asserting an IOError on a lock timeout the product never
   raises. 12 of the last 30 scored runs carry a unit-test gap. The harness settles a sprint when the locked suite
   is green and only unit tests fail (`SETTLE_WHEN_ACCEPTANCE_IS_GREEN`) and ships them as a completion gap; G1
   showed the gap does not predict the hidden score - but a customer running the product's own `pytest` sees red.
   -> HR2.PR item (merge with reviewer 07): one bounded "ship the unit tests green" pass at release when the locked
   suite is green and unit tests fail: the testing role fixes or removes tests that fail for a test-side reason
   (the product untouched: tests-only writes), settled by the harness running the unit command; tests that catch a
   real product bug stay and become a defect. Quality fix, always on, bounded to one stage; KPI: unit tests
   failing at release (12/30 -> 0), release minutes.

2. **DB pool keeps dead connections (its bug 1) - valid as a robustness bug, unverified as a stall cause.**
   `auth.get_db_connection` (auth.py:131-146) and `run_store` (run_store.py:231-242) borrow from psycopg2 pools with
   no liveness check; after a Postgres restart a dead connection raises on first use, the except path's
   `conn.rollback()` raises InterfaceError over the real error, and `finally: putconn(conn)` returns the dead
   connection to the pool to be handed out again. No stall was observed (tonight's restart took the worker down
   too). -> HR2.RT item: on OperationalError/InterfaceError discard the connection (`putconn(conn, close=True)`)
   and retry the borrow once; test: a pool handing out a closed connection is discarded and the next borrow is
   fresh. Bug, always on, small.

3. **Pre-flight model diagnostics leave no transcript record (its bug 2) - valid, low.** `diagnose_if_new`,
   `measure_if_new`, `deep_if_new`, `capabilities.fill` (tasks.py:625-650) run before the segment's first stage and
   write only the steering-job status. Measured: no run in the last 40 had more than 2 minutes between creation
   and its first transcript record, so the 8-15 minute case arises only when a model is new to the harness.
   -> HR2.OB item: one transcript record per diagnosis step (kind `model_diagnostic`, start/end, calls made), so
   the audit's "stalled at 0%" cannot be a diagnosis. Observability, always on, small.

## Overstated
- "66-78% reasoning tokens" and "cache thrashing up to 300k tokens" are the first review's numbers; the PX items
  (Appendix 9) and C4 cover the request layout.
- "Defect fixers are blind to the failing assertion": true before 11-07; LF.664/667/668 changed it (measure the
  request mix with `loop.sh` before re-raising).
