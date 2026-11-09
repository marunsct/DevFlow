"""A file rewritten for one defect is shown the failures of the other open defects that point at it (behind `CO_DEFECT_FAILURES_IN_REWRITES`).

Measured over the runs with rewrites: files were rewritten twice in one round, once for each open defect that
pointed at them. Each rewrite saw only its own defect's failure, so the second could undo what the first had
needed, and the round measured both. A file that two failures name is one file with two things to get right.

With the switch on, the prompt of a file's rewrite also carries the other open defects whose failure points at that
file (`failures_by_file`): what each says failed, in at most `MOST_CO_DEFECTS` entries of `MOST_CHARACTERS`
characters. The rewrite is asked for one version of the file that answers all of them, and a defect the
write settled is closed by the fix cycle's own check (`_closed_if_an_earlier_fix_resolved_it`) before it is
dispatched, so the file is not rewritten a second time in the round.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Sequence

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `CO_DEFECT_FAILURES_IN_REWRITES` set to on or off overrides this.
ON_BY_DEFAULT = False

#: Other defects shown in one file's rewrite, and the characters of each one's failure.
MOST_CO_DEFECTS = 3
MOST_CHARACTERS = 1_200


def enabled() -> bool:
    return is_on("CO_DEFECT_FAILURES_IN_REWRITES", ON_BY_DEFAULT)


def open_besides(cycle: Any, defect: Any) -> list[Any]:
    """The defects of `cycle` still open other than `defect`; [] when the switch is off or there is no cycle."""
    if not enabled():
        return []
    mine = str(getattr(defect, "description", "") or "")
    return [other for other in getattr(cycle, "defects", None) or []
            if other is not defect and str(getattr(other, "status", "")) == "open"
            and str(getattr(other, "description", "") or "") != mine]


def failures_by_file(
    co_defects: Sequence[Any], root: str | Path, may_write: Callable[[str], bool],
) -> dict[str, str]:
    """{file: the section of other defects' failures that point at it}; {} when off, none open or none points anywhere.

    A defect's files are the ones its own failure names (`rewritten_fixes.files_to_fix`), the same rule that
    chooses what its own rewrite changes. Never raises: a rewrite without this section is the rewrite as before.
    """
    if not enabled() or not co_defects:
        return {}
    try:
        from app.graph.rewritten_fixes import files_to_fix, what_failed

        entries: dict[str, list[str]] = {}
        for other in co_defects:
            failure = what_failed(other, root)
            said = " ".join(str(getattr(other, "description", "") or "").split())[:300]
            body = f"- {said}\n  Expected: {' '.join(str(getattr(other, 'expected_behavior', '') or '').split())[:300]}"
            if failure.strip():
                body += "\n  What failed:\n" + "\n".join("    " + line for line in failure[:MOST_CHARACTERS].splitlines())
            for path in files_to_fix(other, failure, root, may_write):
                if len(entries.setdefault(path, [])) < MOST_CO_DEFECTS:
                    entries[path].append(body)
        return {path: _section(found) for path, found in entries.items() if found}
    except Exception:  # noqa: BLE001 - the rewrite is asked without it
        logger.debug("Could not gather the other defects' failures for a rewrite", exc_info=True)
        return {}


def _section(entries: list[str]) -> str:
    return ("--- Other open defects whose failure points at this file ---\n" + "\n".join(entries)
            + "\nWrite one version of the file that answers this defect and these too; do not undo what they need.")


__all__ = ["ON_BY_DEFAULT", "enabled", "failures_by_file", "open_besides"]
