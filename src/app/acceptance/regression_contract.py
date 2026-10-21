"""A seeded codebase's own green tests are a contract the change must keep (plan BW.1, behind `REGRESSION_CONTRACT`).

A run seeded with an existing product started its CI baseline empty, as a
greenfield run does - nothing passes before the first feature - so a change
that broke what the product already did was found by no regression check; and
the platform's second scenario, changing a product that exists, was measured by
nothing until the brownfield bench (BW.3). With the switch on, the baseline
taken when the acceptance suite is locked is a measurement of the seeded
product as it stands: its unit tests and the locked suite's tests that already
pass. Every one is then held by the CI gate, which raises a test that passed
then and fails later as a regression defect - sent back like a failed criterion.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `REGRESSION_CONTRACT` set to on or off overrides this.
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
        path.write_text(json.dumps({"provenance": provenance}), encoding="utf-8")
    except OSError:
        logger.debug("Could not record the seed", exc_info=True)


def seeded(root: str | Path) -> bool:
    return (Path(root) / SEEDED_FILE).is_file()


def applies(root: str | Path) -> bool:
    """Whether the baseline at the suite's lock is the seeded product's own measurement."""
    return enabled() and seeded(root)


__all__ = ["ON_BY_DEFAULT", "SEEDED_FILE", "applies", "enabled", "mark_seeded", "seeded"]
