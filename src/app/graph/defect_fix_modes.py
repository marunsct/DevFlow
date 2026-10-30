"""What a fix stage is allowed to write and what is kept of it, decided as the stage begins.

One place for the modes a fix stage can run in, so `workflow` makes one call as a
fix begins and one as it ends:

- `TESTS_ONLY_WRITES` (`app.tools.tests_only_writes`): the first fix of a failing
  unit test beside a green acceptance suite writes test files only.
- `MUTATION_TEST_RETENTION` (`app.acceptance.mutation_retention`): the unit tests'
  failures before a mutation finding's fix, so what the fix added can be judged.

Each is read through its own switch; with both off nothing here registers anything.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.acceptance import mutation_guided, mutation_retention
from app.tools import tests_only_writes

logger = logging.getLogger(__name__)


def _run_id(config: Any) -> str | None:
    from app.tracing import APP_RUN_ID_KEY

    return ((config or {}).get("configurable") or {}).get(APP_RUN_ID_KEY)


def _the_suite_is_green(state: Any, root: str | Path) -> bool:
    """Whether the locked suite ran, every due criterion passed and no test failed. Never raises."""
    try:
        from app.graph import acceptance_nodes, settle_when_green

        failing, _ = acceptance_nodes._failing_due(state)
        return not failing and settle_when_green.the_locked_suite_is_green(root)
    except Exception:  # noqa: BLE001 - a mode that cannot be sure the suite is green does not apply
        return False


def begin(state: Any, config: Any, cycle: Any, defect_index: int, stage_name: str) -> None:
    """Register the mode this fix stage runs in, and record it. Never raises."""
    try:
        from app.observability import defect_ledger
        from app.sprint import failed_fix_tries

        run_id, defect = _run_id(config), cycle.defects[defect_index]
        root = state["repository"].root_path
        tests_only_writes.release(run_id, stage_name)
        if tests_only_writes.enabled() and not mutation_guided.is_a_finding(defect):
            from app.graph import settle_when_green

            is_a_unit_failure = settle_when_green._a_unit_test_failure(defect, settle_when_green.the_acceptance_command(root))
            beside_green = is_a_unit_failure and _the_suite_is_green(state, root)
            first = failed_fix_tries(cycle, defect_index) == 0
            held = beside_green and first
            if held:
                tests_only_writes.hold(run_id, stage_name)
            said = tests_only_writes.explain_mode(held, unit_failure_beside_a_green_suite=beside_green)
            if said:
                defect_ledger.note(
                    "mode", stage_name, defect=defect, round_=state.get("test_round", 0), index=defect_index,
                    sprint=state.get("current_sprint_index", 0), detail=said,
                )
        if mutation_retention.enabled() and mutation_guided.is_a_finding(defect):
            mutation_retention.remember(run_id, stage_name, root)
    except Exception:  # noqa: BLE001 - a stage with no mode registered writes as it always did
        logger.debug("Could not register the fix stage's mode", exc_info=True)


def end(config: Any, stage_name: str) -> None:
    """Forget the stage's mode: its writes are over."""
    tests_only_writes.release(_run_id(config), stage_name)


def briefing(state: Any, config: Any, defect_index: int) -> str:
    """The section of the fixer's request that says what it may write; "" when nothing is held."""
    return tests_only_writes.briefing(_run_id(config), f"defect_fix_{state.get('test_round', 0)}_{defect_index}")


def may_write(state: Any, config: Any, defect: Any, root: str | Path, path: str) -> bool:
    """Whether the fix of `defect` may rewrite `path` under the stage's mode (the rewrite path's own filter)."""
    try:
        cycle = state["remediation"]
        index = next(i for i, d in enumerate(cycle.defects) if d is defect)
    except (KeyError, StopIteration):
        return True
    return tests_only_writes.may_write(_run_id(config), f"defect_fix_{state.get('test_round', 0)}_{index}", root, path)


__all__ = ["begin", "briefing", "end", "may_write"]
