"""Each harness probe a test round asks is asked again at release; what it still finds is a gap that blocks.

Deep review 2026-11-18, item B2: a product was delivered with the concurrent-write defect the harness's own probe had
raised still open, and its gaps said nothing of it. The release re-ran only the contract's bare checks; of the other
probes it named only what they had not asked. A probe's finding at a round is a defect a fixer is given, and a defect
no fixer closed is still the product's at release, so each probe that applies is asked once more and what it still
finds is carried into `completion_gaps` in the very words the round's defect gave a fixer.

The probes are the round's own (`interface_contract`'s server-error, emptied-field and kept-when-empty probes,
`wrong_shape_body_probe`, `concurrent_write_probe`, `edge_probe`, `round_trip_probe`, `page_probe`), each on its own
switch as at a round (the round-trip and kept-when-empty probes have none); a probe that cannot run says nothing.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: How each gap opens; the defect's own description follows it unchanged.
STILL_FINDS = "At release a harness probe still finds: "


def _the_openings() -> tuple[str, ...]:
    """How the defect of each probe asked here opens, as the round raises it."""
    from app.acceptance import concurrent_write_probe, edge_probe, interface_contract, page_probe, round_trip_probe

    return (interface_contract.SERVER_FAILED, interface_contract.EMPTIED_FIELD_ACCEPTED, interface_contract.KEPT_EMPTY_REFUSED,
            concurrent_write_probe.CONCURRENT_WRITES_LOST, edge_probe.EDGE_CASES_FAILED, page_probe.PAGE_CHECK_FAILED,
            round_trip_probe.ROUND_TRIPS_FAILED)


def carries_a_finding(defect: Any) -> bool:
    """Whether `defect` carries what one of these probes found - as its own finding, or merged into another. Never raises.

    What a probe finds still at release blocks it, so such a defect is the product's to fix: never a failing unit test
    alone, whose first fix may write tests only and which a green sprint settles with. Measured on one run: the
    server-error and edge probes' findings at a green round were merged under "the unit tests fail" (one cause: a store
    read before any write answered 500); the fixer was told the product was right and allowed to write tests only, the
    sprint settled as "only the unit tests fail", and the release was not deliverable on those very findings.
    """
    try:
        description = str(getattr(defect, "description", "") or "")
        if any(opening in description for opening in _the_openings()):
            return True
        return any(isinstance(record, dict) and record.get("probe") for record in getattr(defect, "evidence", None) or ())
    except Exception:  # noqa: BLE001 - a defect that cannot be read is taken as it was
        logger.debug("Could not read whether a defect carries a probe's finding", exc_info=True)
        return False


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
        refused = interface_contract.kept_empty_errors(repo_root, runner=runner) or []
        if refused:
            gaps.append(STILL_FINDS + interface_contract.kept_empty_description(
                refused, interface_contract.what_the_brief_refuses_empty(repo_root)))
    except Exception:  # noqa: BLE001
        logger.debug("Could not ask the kept-when-empty probe again at release", exc_info=True)
    try:
        lost = concurrent_write_probe.concurrent_write_errors(repo_root, runner=runner) or []
        if lost:
            gaps.append(STILL_FINDS + concurrent_write_probe.concurrent_write_description(lost))
    except Exception:  # noqa: BLE001
        logger.debug("Could not ask the concurrent-write probe again at release", exc_info=True)
    try:
        from app.acceptance import edge_probe

        edges = edge_probe.edge_errors(repo_root, runner=runner) or []
        if edges:
            gaps.append(STILL_FINDS + edge_probe.edge_description(edges))
    except Exception:  # noqa: BLE001
        logger.debug("Could not ask the edge probe again at release", exc_info=True)
    try:
        from app.acceptance import round_trip_probe

        trips = round_trip_probe.round_trip_errors(repo_root, runner=runner) or []
        if trips:
            gaps.append(STILL_FINDS + round_trip_probe.round_trip_description(trips))
    except Exception:  # noqa: BLE001
        logger.debug("Could not ask the round-trip probe again at release", exc_info=True)
    try:
        from app.acceptance import page_probe

        # The brief's word on persistence as the round's asking kept it.
        pages = page_probe.page_errors(repo_root, runner=runner) or []
        if pages:
            gaps.append(STILL_FINDS + page_probe.page_description(pages))
    except Exception:  # noqa: BLE001
        logger.debug("Could not ask the page checks again at release", exc_info=True)
    if gaps:
        logger.warning("At release %d harness probe(s) still find a defect", len(gaps))
    return gaps


__all__ = ["STILL_FINDS", "carries_a_finding", "what_the_probes_still_find"]
