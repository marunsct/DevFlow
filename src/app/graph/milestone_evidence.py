"""`MILESTONE_EVIDENCE_GATE` (harness review G3, docs/measuring.md M7): a milestone finding sends the sprint back only
when a failing test, check or underline shows it - the code review's rule (`engineering.what_shows_it`).

Measured: no review lifts the hidden score, and a milestone send-back costs about 19 minutes on a third of runs. One
run sent its sprint back on a reviewer's reading of the code (a `KeyError` on a malformed stored record) that no test
showed; the product scored the same either way. Off until measured: two runs per family on and off.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

from app.switches import is_on

logger = logging.getLogger(__name__)

ON_BY_DEFAULT = False
#: What the admin page says this switch does.
explanation = ("A milestone review's blocking finding sends the sprint back only when a failing test, a failing "
               "criterion or an underline in its file shows it; a finding nothing shows is kept as advice for the "
               "release. The code review's rule, applied to the milestone review (harness review G3).")


def enabled() -> bool:
    return is_on("MILESTONE_EVIDENCE_GATE", ON_BY_DEFAULT)


def shown_and_not(state: Any, findings: list[Any]) -> tuple[list[Any], list[Any]]:
    """`findings` split into those a test, check or underline shows and those nothing shows. Never raises."""
    from app.graph.engineering import what_shows_it

    shown, unshown = [], []
    for finding in findings:
        as_a_review_finding = SimpleNamespace(
            problem=str(getattr(finding, "description", "") or getattr(finding, "problem", "") or ""),
            fix=str(getattr(finding, "recommendation", "") or getattr(finding, "fix", "") or ""),
            file=str(getattr(finding, "file", "") or getattr(finding, "location", "") or ""),
        )
        try:
            why = what_shows_it(state, as_a_review_finding)
        except Exception:  # noqa: BLE001 - unknown blocks as before
            why = "unknown"
        (shown if why else unshown).append(finding)
    return shown, unshown


__all__ = ["ON_BY_DEFAULT", "enabled", "explanation", "shown_and_not"]
