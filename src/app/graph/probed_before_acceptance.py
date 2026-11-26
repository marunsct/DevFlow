"""No sprint is accepted before the harness's contract probes have run on the product as that sprint left it (LF.1523).

Measured on one run of a service in parallel mode: every criterion due by sprint 2 already passed when the sprint
opened, because sprint 1 had built its routes, so the lead's node closed it with nothing to build and sent it to its
reviews without a test round (`workflow._close_a_sprint_with_nothing_to_build`; both execution modes plan a sprint in
the same node). The contract probes run only inside a round (`triage`), so none of them saw that sprint's routes. At
release the edge probe found `DELETE /items/{id}` answering 500 at a huge id, a gap no fixer was ever given. The same
close skips the round, and with it the probes, on its other branch too: the one that accepts with no review at all.

So a sprint closed with nothing to build is first asked the probes a green test round asks. What they find sends the
sprint to a test round, which raises it as a defect for a fixer the way every round does; the sprint is reviewed and
accepted after that, as any sprint is. Nothing found: the sprint is closed as before. Each probe keeps its own switch.
"""
from __future__ import annotations

from typing import Any

#: Where the suite's state keeps what the contract's checks at the lock found (`interface_contract.probe_at_the_lock`).
_AT_THE_LOCK = "interface_contract_errors_at_lock"

#: The question a sprint closed with nothing to build answers, and the answer that sends it to a round.
FIRST_A_ROUND = "measure it in a test round first"

#: What the plan of such a sprint says: it builds nothing, and its round is for the probes' findings.
NO_NEW_WORK = (
    "No new work: every criterion due already passes. The harness's probes of the product as it stands found "
    "problems no locked test checks; a test round raises them for a fixer before the sprint is accepted."
)


def what_the_probes_find(state: Any, milestone: Any) -> list[Any]:
    """The defects the probes of a green test round raise on the product as it stands; [] when none. Never raises.

    The same probes, under the same conditions on the suite's last run, as `triage` asks them at a round: the contract's
    (server errors, concurrent writes, edges, round trips, emptied and kept-empty fields) on a green or near-green
    suite, the page checks on a green one, and what the checks at the lock found on any.
    """
    try:
        from app.acceptance import suite
        from app.agents.specialists import SpecialistOutput
        from app.graph.near_green_once import near_green
        from app.graph.workflow import (
            _with_a_page_check_defect, _with_the_contract_s_server_errors, _with_the_lock_s_server_errors,
        )

        root = state["repository"].root_path
        saved = suite.last_result(root) or {}
        passed, failed = int(saved.get("passed") or 0), int(saved.get("failed") or 0)
        found = SpecialistOutput(changed_files=[], defects=[], decisions=[])
        if failed == 0 or (passed > 0 and near_green(passed, failed)):
            found = _with_the_contract_s_server_errors(state, found, milestone)
        if failed == 0:
            found = _with_a_page_check_defect(state, found, milestone)
        # What the checks at the lock found is taken by the round that raises it: kept for that round, not spent here.
        kept = suite._state(root).get(_AT_THE_LOCK)  # noqa: SLF001 - one state file for the suite and its contract
        found = _with_the_lock_s_server_errors(state, found, milestone)
        if kept is not None:
            again = suite._state(root)  # noqa: SLF001
            again[_AT_THE_LOCK] = kept
            suite._save_state(root, again)  # noqa: SLF001
        return list(found.defects or [])
    except Exception as error:  # noqa: BLE001 - a probe that cannot run says nothing, as at a round
        from app.observability.degraded import degraded

        degraded("probed_before_acceptance", error)
        return []


def to_a_test_round(state: Any, why: str, found: list[Any], milestone: Any) -> dict[str, Any]:
    """The update that sends a sprint closed with nothing to build to a test round, for what `found` holds."""
    from app.decisions import record_decision
    from app.graph.workflow import _handing_on

    index = int(state.get("current_sprint_index") or 0)
    update: dict[str, Any] = {}
    record_decision(
        state, update, point="sprint",
        question=f"Is sprint {index + 1} done?",
        options=["accept without new work", FIRST_A_ROUND],
        decision=FIRST_A_ROUND,
        rationale=(
            "Every criterion due already passes, but the harness's probes of the product find what no locked test "
            "checks; a test round raises it for a fixer before the sprint is accepted.\n"
            + "".join(f"- {(str(getattr(d, 'description', '') or '').splitlines() or [''])[0][:300]}\n" for d in found)
            + why
        ),
    )
    plan = milestone.model_copy(update={"integration_notes": [NO_NEW_WORK]})
    return _handing_on(
        **update,
        stage="test_and_triage",
        milestone_plan=plan,
        specialist_outputs={},
        nothing_left_but_carried=None,
        test_round=int(state.get("test_round") or 0),
        defect_cursor=0,
    )


__all__ = ["FIRST_A_ROUND", "NO_NEW_WORK", "to_a_test_round", "what_the_probes_find"]
