"""A test round reports from the harness's measurement; it does not diagnose it (LF.1394, LF.1395).

The split: the harness measures (the locked suite, the unit tests, the probes); the test round reports what failed
with its evidence and what the measurement does not show; the defect's fixer finds the cause and fixes it, given the
measurement again when it starts (`graph.fresh_evidence`).

Measured on one medium run's first test round (thorough delivery, the suite 8 passed and 13 failed): 46 replies in 36
minutes and counting, 59 file reads - the sign-in routes and their unit tests 10 times each, each acceptance file 6
times, the schemas 6 - a diagnostic script of its own, a reinstall, and the whole suite run again, all to explain 13
failures the harness had measured and raises itself after the round (`acceptance_nodes.failing_due_defects`, with each
test's message and the server's log). On two earlier medium runs a red round took 38-81 active minutes and 165-204
reads, one file read 27-30 times. Its explanation, when it gave one, took the place of the harness's defect for that
criterion, and the fixer read it first: the measured run's said the service crashed at start, while the health route
answered 200 throughout.

- `the_split` (always on, LF.1394: a role confused, not a trade): a round whose due criteria fail is told the harness
  raises them, with their evidence, after it; that diagnosing them is the fixer's work; and that its report is what the
  measurement does not show - the unit tests, an error printed while tests pass, a rule held on one path only, a fault
  in a test of its own.
- `MEASURED_ROUND_WHEN_RED` (LF.1395, group "Efficiency", off until measured): in thorough delivery, a round whose
  locked suite ran and fails due criteria is the harness's own, as every fast delivery round is - the unit tests run
  and what fails is raised without a model. The trade: what only the model's round finds (a rule held on one path, an
  error printed while tests pass) waits for a round whose suite is green.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

from app.switches import is_on

logger = logging.getLogger(__name__)

#: The heading of the section a test round with failing due criteria is given; the audit can find it in requests.
SPLIT_HEADING = "--- Already reported: the failing criteria above ---"

#: Off in code like every switch; the compose file and each run's own setting decide.
ON_BY_DEFAULT = False

#: What the admin page says this switch does.
explanation = ("In thorough delivery, a test round whose locked acceptance suite fails criteria that are due is run by "
               "the harness alone, as in fast delivery: the unit tests run and every failure is raised as a defect "
               "from the measurement, with no model reading the product. A round with a green suite is unchanged.")

#: What the harness records each time the switch makes a round its own; the switch-firing check reads it.
SAID = "A red round measured by the harness alone in thorough delivery"
#: The transcript record of such a round.
RECORD_KIND = "measured_round"


def enabled() -> bool:
    return is_on("MEASURED_ROUND_WHEN_RED", ON_BY_DEFAULT)


def _ids(failing: Iterable[Any]) -> list[str]:
    ids: list[str] = []
    for entry in failing or ():
        found = str(entry.get("id") or "") if isinstance(entry, dict) else str(entry or "")
        if found and found not in ids:
            ids.append(found)
    return ids


def the_split(failing: Iterable[Any]) -> str:
    """What a test round's request adds after the suite's result when due criteria fail (`acceptance_nodes._failing_due`
    entries, or their ids); "" when none fails."""
    ids = _ids(failing)
    if not ids:
        return ""
    return (
        f"{SPLIT_HEADING}\n"
        f"After your round the harness raises a defect itself for each failing criterion that is due ({', '.join(ids)}), "
        "with the messages its tests failed with and what the product's server logged, and sends a fixer with each "
        "to find the cause. Do not report those criteria again, and do not work out why they fail: reading the "
        "product's code again and again to explain a failure measured here, running the acceptance suite again, or "
        "writing a script to reproduce one is the fixer's work, done twice.\n"
        "Your report is what this measurement does not show: the unit tests' failures (run them), an error the product "
        "printed while tests passed, a rule held on one path and not on another, a fault in a test of yours. With "
        "nothing beyond the measurement, return an empty `defects` list.\n\n"
    )


def the_harness_s_own(failing: Iterable[Any]) -> bool:
    """Whether a thorough round is the harness's own: the switch on and due criteria failing (the caller has checked
    that the locked suite ran)."""
    return bool(_ids(failing)) and enabled()


def note(stage: str, failing: Iterable[Any]) -> None:
    """Record that the switch made `stage` the harness's own. Never raises."""
    try:
        from app.observability.transcript import _run_id_from_config, record

        record(_run_id_from_config(), stage, RECORD_KIND, message=SAID, criteria=_ids(failing))
    except Exception:  # noqa: BLE001 - the round goes on unrecorded
        logger.debug("Could not record a round measured by the harness", exc_info=True)


__all__ = ["ON_BY_DEFAULT", "RECORD_KIND", "SAID", "SPLIT_HEADING", "enabled", "explanation", "note",
           "the_harness_s_own", "the_split"]
