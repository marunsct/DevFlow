"""Where a fix stage that gave up was aiming, for the rewrite that follows it, and why that rewrite found no file.

Measured over the last 45 runs' transcripts: 25 rewrites after a surrender were declined. Six were mutation findings,
which say so. The other 19 all said "the rewrite found no file it may write, or wrote none" - two different things
in one line, and neither said which file or which rule:

- 11 found no file. Seven were criteria the acceptance suite judges: their defect named no file ("Affected files:
  (none identified)"), and the failure named only the acceptance test, which a rewrite for such a criterion never
  takes. In one the fixer had found the fault and tried to edit the module that sets up the database, and the
  language service refused that edit; the others wrote only scratch scripts or nothing. One fixer named the product
  file in its blockers while its attempt was held to tests only; one edited only the locked acceptance test; two
  defects named only a build's output files, rightly left alone.
- 8 rewrote the file the failure named and got every file back unchanged.

So the rewrite after a surrender also takes the files the fixer wrote, tried to write or named in its answer
(`aimed_at`), after the defect's own evidence and under the same rules (`rewritten_fixes.files_to_fix`). When no file
is left, `why_none` says which rule left out which file, and a rewrite that wrote nothing says what each file's
rewrite came to (`rewritten_fixes.fix_by_rewriting`).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: The tools that change a file, and the arguments naming it.
WRITING_TOOLS = frozenset({
    "write_artifact", "edit_artifact", "replace_lines", "replace_approved_lines", "move_artifact",
})
PATH_ARGUMENTS = ("relative_path", "path", "file_path")
#: Fields of a fixer's answer that say where it found the fault.
_ANSWER_FIELDS = ("changed_files", "blockers", "decisions", "risks")
#: Files the decline names at most, so a ledger line stays a line.
MOST_NAMED = 6


def _written_or_tried(run_id: str | None, stage: str, since: str) -> list[str]:
    """The paths a stage's writing calls named since `since` - refused ones too - in the order it sent them."""
    if not run_id or not stage:
        return []
    from app.observability.transcript import read_live

    found: list[str] = []
    for entry in read_live(run_id, {"tool_call"}):
        if entry.get("stage") != stage or str(entry.get("at") or "") < str(since or ""):
            continue
        if str(entry.get("tool") or entry.get("name") or "") not in WRITING_TOOLS:
            continue
        args = entry.get("args") or {}
        for key in PATH_ARGUMENTS:
            path = str(args.get(key) or "").strip() if isinstance(args, dict) else ""
            if path and path not in found:
                found.append(path)
    return found


def answer_text(output: Any) -> str:
    """What a fixer's answer says, in the fields that name where the fault is."""
    parts: list[str] = []
    for name in _ANSWER_FIELDS:
        value = getattr(output, name, None) or []
        parts.extend(str(item) for item in (value if isinstance(value, (list, tuple)) else [value]))
    return "\n".join(parts)


def aimed_at(run_id: str | None, stage: str, since: str, output: Any) -> list[str]:
    """The files a fix stage wrote or tried to write, then those its answer names; once each. Never raises."""
    from app.graph.rewritten_fixes import files_mentioned_in

    found: list[str] = []
    try:
        found = _written_or_tried(run_id, stage, since)
    except Exception:  # noqa: BLE001 - its answer still names files
        logger.debug("Could not read what the fix stage wrote", exc_info=True)
    try:
        for name in files_mentioned_in(answer_text(output)):
            if name not in found:
                found.append(name)
    except Exception:  # noqa: BLE001 - what it wrote stands
        logger.debug("Could not read the files the fix stage's answer names", exc_info=True)
    return found


def why_none(refused: dict[str, str]) -> str:
    """Why a rewrite found no file it may write: each file left out with the rule that left it out."""
    if not refused:
        return ("the rewrite found no file it may write: neither the defect, its failure nor the fixer's work "
                "names a file in the workspace")
    named = [f"`{path}`: {reason}" for path, reason in list(refused.items())[:MOST_NAMED]]
    more = len(refused) - len(named)
    return ("the rewrite found no file it may write: " + "; ".join(named)
            + (f"; and {more} more" if more > 0 else ""))


__all__ = ["MOST_NAMED", "PATH_ARGUMENTS", "WRITING_TOOLS", "aimed_at", "answer_text", "why_none"]
