"""A product that does not build or start gets one fix aimed at that, before any fixer of a single criterion.

Deep review 2026-11-18, item 1.5. Measured on two runs: fix rounds sent many per-defect fixers - up to 13 in one round
- at a product that did not start, each shown its own criterion or compiler line, each failing the same way; the
reverts piled up ("the product no longer builds or starts" three and five times). The test round already raised one
defect for a product that does not start (`acceptance_nodes.THE_PRODUCT_DOES_NOT_START`), but beside it went every
compiler and language-service finding, a failed install and a unit run that did not compile, each to a fixer of its
own and in parallel, and every open defect of the rounds before.

Now, at a test round, what says why it does not build or start is folded into the one start defect (`folded`), so its
one fixer has all of the evidence; and while a start defect is open, the fix round dispatches only it (`held_back`).
The others stay open, and are fixed - or measured again - once the product starts. A product that starts is not
affected.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from app.sprint import cause

logger = logging.getLogger(__name__)

#: The opening of the install failure's defect (`acceptance_nodes._the_install_that_failed`).
DEPENDENCIES_DO_NOT_INSTALL = "The project's dependencies do not install"
#: What opens the list of folded findings on the start defect.
ALSO_WHILE_IT_DOES_NOT_START = (
    "Also found while the product does not build or start. Each may be why it does not; this one change makes it "
    "build and start, and every other failure is measured again once it does:"
)
_MOST_FOLDED = 12


def is_a_start_defect(defect: Any) -> bool:
    """Whether `defect` is a product that does not build or start for the acceptance suite."""
    kind = str(getattr(defect, "kind", "") or "")
    if kind:
        return kind == cause.START_FAILURE
    # A defect from before kinds: the start defect's own sentence.
    from app.graph.acceptance_nodes import THE_PRODUCT_DOES_NOT_START

    return str(getattr(defect, "description", "") or "") == THE_PRODUCT_DOES_NOT_START


def _part_of_the_start(defect: Any) -> bool:
    """A finding that says why a product does not build or start: a compiler's, a build's, an install's."""
    # The setup's contract on its entry file (a declaration or an export its build and start rely on) too: measured
    # on one Rust run, `app()` declared `-> Router<AppState>` waited three rounds behind the start defect it caused.
    return (str(getattr(defect, "kind", "") or "") == cause.COMPILE_ERROR
            or str(getattr(defect, "source", "") or "") in ("language service", "pack contract")
            or str(getattr(defect, "description", "") or "").startswith(DEPENDENCIES_DO_NOT_INSTALL))


def folded(reported: Sequence[Any]) -> list[Any]:
    """`reported` with each finding that says why the product does not build or start folded into its start defect.

    As it was when no start defect is among them. The start defect keeps its place and owner and carries each folded
    finding's text, files and evidence; the folded ones are not raised on their own.
    """
    reported = list(reported)
    lead_at = next((at for at, item in enumerate(reported) if is_a_start_defect(item)), None)
    if lead_at is None:
        return reported
    parts = [item for at, item in enumerate(reported) if at != lead_at and _part_of_the_start(item)]
    if not parts:
        return reported
    lead = reported[lead_at]
    lines = [
        f"- [{getattr(item, 'source', '') or 'reported'}] {' '.join(str(item.description).split())[:400]}"
        + (f"\n  {' '.join(str(item.actual_behavior).split())[:600]}" if str(getattr(item, "actual_behavior", "") or "").strip()
           else "")
        for item in parts[:_MOST_FOLDED]
    ]
    if len(parts) > _MOST_FOLDED:
        lines.append(f"- ... and {len(parts) - _MOST_FOLDED} more")
    files = list(dict.fromkeys(str(f) for member in (lead, *parts) for f in getattr(member, "affected_files", None) or []))
    merged = lead.model_copy(update={
        "actual_behavior": f"{lead.actual_behavior}\n\n{ALSO_WHILE_IT_DOES_NOT_START}\n" + "\n".join(lines),
        "affected_files": files,
        "severity": "blocking",
        "kind": cause.START_FAILURE,
        "evidence": cause.merged_evidence((lead, *parts)),
    })
    logger.warning("The product does not build or start: %d finding(s) folded into its one defect", len(parts))
    kept = [merged if at == lead_at else item for at, item in enumerate(reported)]
    return [item for item in kept if not any(item is part for part in parts)]


def held_back(defects: Sequence[Any]) -> set[int]:
    """The indices of open defects no fixer is sent to yet: every one but the start defects, while one is open."""
    open_ = [(at, d) for at, d in enumerate(defects) if str(getattr(d, "status", "")) == "open"]
    if not any(is_a_start_defect(d) for _, d in open_):
        return set()
    return {at for at, d in open_ if not is_a_start_defect(d)}


__all__ = ["ALSO_WHILE_IT_DOES_NOT_START", "DEPENDENCIES_DO_NOT_INSTALL", "folded", "held_back", "is_a_start_defect"]
