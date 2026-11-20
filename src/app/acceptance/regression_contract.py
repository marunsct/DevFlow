"""A seeded codebase's own green tests are a contract the change must keep (plan BW.1; on for every seeded run, WS.7).

A run seeded with an existing product started its CI baseline empty, as a
greenfield run does - nothing passes before the first feature - so a change
that broke what the product already did was found by no regression check; and
the platform's second scenario, changing a product that exists, was measured by
nothing until the brownfield bench (BW.3). For a seeded run the baseline taken
when the acceptance suite is locked is a measurement of the seeded product as it
stands: its unit tests and the locked suite's tests that already pass. Every one
is then held by the CI gate, which raises a test that passed then and fails
later as a regression defect - sent back like a failed criterion.

It was behind a premium bundle, so a deployment without the bundle changed an
existing product with nothing holding what it already did (plan WS.7). It is
part of the base product now, on for every seeded run whatever a bundle says;
only `REGRESSION_CONTRACT=off` on the host (a test's hook) turns it off. Each
baseline taken is a `baseline` record in the run's transcript.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.switches import is_on

logger = logging.getLogger(__name__)

#: The code's own default, as every listed switch has it; built in (`switches.BUILT_IN`), it is on unless its variable
#: is set off on the host.
ON_BY_DEFAULT = False
#: Where seeding says what the workspace was seeded from (`server.seeding.seed_workspace`).
SEEDED_FILE = ".harness/seeded.json"


def enabled() -> bool:
    return is_on("REGRESSION_CONTRACT", ON_BY_DEFAULT)


def mark_seeded(workspace: str | Path, provenance: dict) -> None:
    """Record that the workspace was seeded, and from what. Never raises."""
    try:
        path = Path(workspace) / SEEDED_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        # The top-level names too, read before anything else writes there: what
        # is the seed's to move into the pinned directory (`stacks.seeded_product`).
        entries = sorted(entry.name for entry in Path(workspace).iterdir() if entry.name not in {".git", ".harness"})
        path.write_text(json.dumps({"provenance": provenance, "entries": entries}), encoding="utf-8")
    except OSError:
        logger.debug("Could not record the seed", exc_info=True)


def seeded(root: str | Path) -> bool:
    return (Path(root) / SEEDED_FILE).is_file()


def applies(root: str | Path) -> bool:
    """Whether the baseline at the suite's lock is the seeded product's own measurement: for every seeded run."""
    return seeded(root) and enabled()


def record_the_baseline(measured: object, run_id: str | None = None) -> None:
    """A `baseline` record in the run's transcript: how many of the seeded product's tests pass and are held. Never raises."""
    try:
        from app.observability.transcript import record

        if run_id is None:
            from app.models.model_pin import current_run_id

            run_id = current_run_id()
        passing = sorted(getattr(measured, "passing")())
        record(run_id, "acceptance", "baseline",
               label=str(getattr(measured, "label", "") or ""), commit=str(getattr(measured, "commit", "") or ""),
               held=len(passing), unit_ran=bool(getattr(measured, "unit_ran", False)),
               acceptance_ran=bool(getattr(measured, "acceptance_ran", False)), tests=passing[:200])
    except Exception:  # noqa: BLE001 - a record is evidence, not control flow
        logger.debug("Could not record the baseline", exc_info=True)


__all__ = ["ON_BY_DEFAULT", "SEEDED_FILE", "applies", "enabled", "mark_seeded", "record_the_baseline", "seeded"]
