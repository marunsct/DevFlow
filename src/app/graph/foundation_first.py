"""At each test round, the product's foundation is smoked before any fixer of a single criterion is sent (LF.1268).

Measured on a medium run: sign-up answered 500 for hours, then every route 404 under a doubled prefix, and 24 of 24
per-criterion fixers of a sprint worked on a product where no account could be made. The round now asks the smoke
(`acceptance.foundation_smoke`) once the product starts: a smoke that fails raises one blocking defect for its first
failing step, and while that is open the fix round sends a fixer to it alone (`start_first.held_back`). A smoke that
holds closes it; one that could not be asked or settled this round releases it, so a hold never outlives the
measurement that made it. A product with no HTTP contract, or one the smoke cannot read, is not affected.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: The check a smoke's defect is raised by.
SOURCE = "foundation smoke"


def at_the_round(state: Any, reported: list[Any], test_round: int) -> tuple[list[Any], Any]:
    """(`reported` with the smoke's defect first when the smoke failed, the smoke's result or None). Never raises."""
    try:
        from app.acceptance import foundation_smoke, suite
        from app.agents.specialists import raised_by
        from app.graph import acceptance_nodes, start_first

        root = state["repository"].root_path
        if not suite.is_locked(root):
            return reported, None
        stage = f"test_round_{test_round}"
        saved = suite.last_result(root) or {}
        if saved.get("ran") and int(saved.get("failed") or 0) == 0 and int(saved.get("passed") or 0) > 0:
            # The suite reached the product and every test it ran passed: the foundation holds, and the round is as
            # it always was (no smoke to wait for).
            held = foundation_smoke.Result(held=True, why="the acceptance suite passes every test it ran")
            foundation_smoke.record(root, stage, held)
            return reported, held
        problem = str(saved.get("problem") or "")
        if problem.startswith(suite.PRODUCT_DID_NOT_START) or any(start_first.is_a_start_defect(d) for d in reported):
            # The tier before: one defect for a product that does not start, which the smoke would only repeat.
            foundation_smoke.record(root, stage, None)
            return reported, None
        due = acceptance_nodes.criteria_due(state)
        result = foundation_smoke.run(root, due)
        foundation_smoke.record(root, stage, result, due)
        if result is None or result.held is not False:
            return reported, result
        logger.warning("%s: the foundation smoke failed where %s (%s %s answered %s); every other defect waits",
                       stage, foundation_smoke.STEPS.get(result.step, result.step), result.method, result.path,
                       result.status or "nothing")
        owner = acceptance_nodes._owner_for(state, result.said)  # noqa: SLF001 - who fixes the product's service
        return [*raised_by(SOURCE, [foundation_smoke.a_defect(result, owner)]), *reported], result
    except Exception:  # noqa: BLE001 - the round as measured stands
        logger.debug("Could not smoke the product's foundation", exc_info=True)
        return reported, None


def settled_by_the_round(cycle: Any, result: Any, test_round: int, sprint: int = 0) -> Any:
    """`cycle` with each open smoke defect of an earlier round closed by this round's smoke: fixed when it held,
    superseded when it was not asked or could not settle; left open (to be refreshed) when it failed again."""
    try:
        from app.acceptance import foundation_smoke
        from app.observability import defect_ledger
        from app.sprint import mark_defect_fixed

        if result is not None and result.held is False:
            return cycle
        stage = f"test_round_{test_round}"
        for index, defect in enumerate(list(cycle.defects)):
            if defect.status != "open" or not foundation_smoke.is_a_smoke_defect(defect):
                continue
            if result is not None and result.held:
                why = "the foundation smoke holds at this round"
                cycle = mark_defect_fixed(cycle, index, regression_test="the harness's foundation smoke",
                                          verified_by=SOURCE, resolution=f"{why} (test round {test_round}).")
            else:
                why = "the foundation smoke was not asked or could not settle at this round"
                defects = list(cycle.defects)
                defects[index] = defect.model_copy(update={"status": "superseded"})
                cycle = cycle.model_copy(update={"defects": defects})
            defect_ledger.note("closed by the round's measurement", stage, defect=defect, round_=test_round,
                               index=index, detail=why, sprint=sprint)
        return cycle
    except Exception:  # noqa: BLE001 - a defect left open is counted as before
        logger.debug("Could not settle the foundation smoke's defects", exc_info=True)
        return cycle


__all__ = ["SOURCE", "at_the_round", "settled_by_the_round"]
