"""How a run delivers: `fast` or `thorough` (`DELIVERY_MODE`, a setting).

Measured on one run of a five-route notes service: 13 hours, 1,081 model
calls one after another, 2.8 million output tokens (half of them reasoning)
for 549 lines of product and 5,058 lines of tests. Most of the time went to
ceremony - four sprints each re-planned, reviewed and test-rounded - and to
an agent loop of about forty tool calls per work order.

Fast delivery keeps every stage and record and changes how much each does:

- a product with few criteria is one sprint (`scrum_master.max_sprints_for_criteria_count`);
- each work order's files are drafted straight from the specification, one
  call per file, several at once (`graph.drafting`), with the agent loop as
  the fallback for what a draft cannot do;
- a test round is the harness's own: the locked suite and the unit tests
  run, and what fails becomes a defect without a model reading it;
- tests are the ones the specification plans;
- the stages that build and fix run with reasoning off: the specification
  has decided what they write.

Thorough is the pipeline as it was. The code's default is thorough; a
deployment chooses fast with `DELIVERY_MODE=fast`, and the settings page
changes it.
"""

from __future__ import annotations

import os
from typing import Mapping

FAST = "fast"
THOROUGH = "thorough"
MODES = (FAST, THOROUGH)


def mode(environment: Mapping[str, str] | None = None) -> str:
    """The delivery mode in force: `fast` or `thorough`."""
    if environment is None:
        try:
            from app.server.runtime_settings import effective_environment

            environment = effective_environment()
        except Exception:  # noqa: BLE001 - the deployed environment still stands
            environment = os.environ
    chosen = str(environment.get("DELIVERY_MODE") or "").strip().lower()
    return chosen if chosen in MODES else THOROUGH


def fast(environment: Mapping[str, str] | None = None) -> bool:
    """Whether this deployment delivers fast. See the module docstring."""
    return mode(environment) == FAST
