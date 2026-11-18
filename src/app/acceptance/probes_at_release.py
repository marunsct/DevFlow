"""Each harness probe a test round asks is asked again at release; what it still finds is a gap that blocks.

Deep review 2026-11-18, item B2: a product was delivered with the concurrent-write defect the harness's own probe had
raised still open, and its gaps said nothing of it. The release re-ran only the contract's bare checks; of the other
probes it named only what they had not asked. A probe's finding at a round is a defect a fixer is given, and a defect
no fixer closed is still the product's at release, so each probe that applies is asked once more and what it still
finds is carried into `completion_gaps` in the very words the round's defect gave a fixer.

The probes are the round's own (`interface_contract`, `wrong_shape_body_probe`, `concurrent_write_probe`), each on
its own switch as at a round; a probe that cannot run says nothing.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: How each gap opens; the defect's own description follows it unchanged.
STILL_FINDS = "At release a harness probe still finds: "


def what_the_probes_still_find(repo_root: str | Path, *, runner: Any = None) -> list[str]:
    """A blocking completion gap for each probe that still finds a defect in the product; [] when none. Never raises."""
    from app.acceptance import concurrent_write_probe, interface_contract, wrong_shape_body_probe

    gaps: list[str] = []
    try:
        errors = interface_contract.server_errors(repo_root, runner=runner) or []
        bad_body = interface_contract.bad_body_errors(repo_root, runner=runner) or []
        wrong_shape = wrong_shape_body_probe.wrong_shape_errors(repo_root, runner=runner) or []
        if errors or bad_body or wrong_shape:
            gaps.append(STILL_FINDS + interface_contract.server_error_description(errors, bad_body, wrong_shape))
    except Exception:  # noqa: BLE001 - a probe that cannot run says nothing
        logger.debug("Could not ask the server-error probes again at release", exc_info=True)
    try:
        emptied = interface_contract.emptied_field_errors(repo_root, runner=runner) or []
        if emptied:
            gaps.append(STILL_FINDS + interface_contract.emptied_field_description(emptied))
    except Exception:  # noqa: BLE001
        logger.debug("Could not ask the emptied-field probe again at release", exc_info=True)
    try:
        lost = concurrent_write_probe.concurrent_write_errors(repo_root, runner=runner) or []
        if lost:
            gaps.append(STILL_FINDS + concurrent_write_probe.concurrent_write_description(lost))
    except Exception:  # noqa: BLE001
        logger.debug("Could not ask the concurrent-write probe again at release", exc_info=True)
    if gaps:
        logger.warning("At release %d harness probe(s) still find a defect", len(gaps))
    return gaps


__all__ = ["STILL_FINDS", "what_the_probes_still_find"]
