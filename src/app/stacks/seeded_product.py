"""A product seeded at the workspace root moves into the directory intake pins for it.

An archive is flattened when it is unpacked, so a conventional one-folder upload
lands at the workspace root, and so does any product whose folders are all parts
of a project (`src`, `tests`). Intake then pinned a new, empty directory beside
it. Measured on one brownfield run: the agents rebuilt the product in the new
directory without its launcher, the hidden suite scored 0 of 15 at the start,
and the setup stage ran for 23 minutes because the empty directory held no
manifest.

Every rule of the harness, the scorer and a product's launcher work from the
pinned directory, so the product goes there: by `git mv` where the workspace is
a repository, keeping its history, and by a plain rename otherwise. Only what
seeding recorded is moved, nothing is overwritten, and the harness's own records
stay where they are. A record of the move makes a second visit (a resume, a
rewind to intake) do nothing, whatever has been written at the root since.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: What the move did: written once, read by a second visit and by the decision.
MOVE_RECORD = ".harness/seed-moved.json"
#: Never moved. `docs` is where the harness writes each run's documents.
STAYS_AT_THE_ROOT = frozenset({
    ".git", ".harness", ".agent-home", "docs", "large_tool_results", ".project-directory", ".project-stack",
    ".project-memory.json", ".work-order-files.json",
})
#: The decision's question, which also tells a decision already recorded.
QUESTION = "Where does the seeded product live?"


def _seed_entries(root: Path) -> list[str]:
    """The top-level names seeding recorded; [] for a run that was not seeded."""
    from app.acceptance.regression_contract import SEEDED_FILE

    try:
        record = json.loads((root / SEEDED_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    entries = record.get("entries") if isinstance(record, dict) else None
    if not isinstance(entries, list):
        return []
    return [name for name in entries if isinstance(name, str) and name == Path(name).name and name not in {"", ".", ".."}]


def _harness_ignore_file(path: Path) -> bool:
    """Whether a root `.gitignore` is the one `initialise_repository` wrote: it keeps the harness's records out of history."""
    from app.tools.version_control import _IGNORED

    try:
        return path.read_text(encoding="utf-8") == _IGNORED
    except (OSError, UnicodeDecodeError):
        return False


def move_the_seeded_product_in(root: str | Path) -> dict[str, Any] | None:
    """Move a product seeded at the root into the pinned directory; what was done, or None. Never raises."""
    try:
        return _move(Path(root))
    except OSError:
        logger.warning("Could not move the seeded product at %s", root, exc_info=True)
        return None


def _move(base: Path) -> dict[str, Any] | None:
    from app.tools.repository import _is_project_directory, pinned_project_directory
    from app.tools.version_control import commit_all, move_keeping_history

    if (base / MOVE_RECORD).exists():
        return None
    entries = _seed_entries(base)
    project = pinned_project_directory(base)
    if not entries or not project or project != Path(project).name or not _is_project_directory(project):
        return None
    # A project directory in the seed, or a pin that names the seed's own entry:
    # the code already says where it lives.
    if project in entries or any(
        (base / name).is_dir() and _is_project_directory(name) for name in entries if name not in STAYS_AT_THE_ROOT
    ):
        return None
    target = base / project
    if os.path.lexists(target) and not target.is_dir():
        logger.warning("%s/ is pinned but something else stands there; the seeded product stays at the root", project)
        return None
    target.mkdir(parents=True, exist_ok=True)
    moved: list[str] = []
    left: list[str] = []
    for name in entries:
        source = base / name
        if not os.path.lexists(source):
            continue
        if name in STAYS_AT_THE_ROOT or (name == ".gitignore" and _harness_ignore_file(source)):
            left.append(name)
        elif os.path.lexists(target / name):
            logger.warning("%s/%s already exists; the seeded %s stays at the root", project, name, name)
            left.append(name)
        else:
            move_keeping_history(base, name, project)
            moved.append(name)
    if not moved and not left:
        return None
    record = {"project": project, "moved": moved, "left": left}
    (base / MOVE_RECORD).parent.mkdir(parents=True, exist_ok=True)
    (base / MOVE_RECORD).write_text(json.dumps(record), encoding="utf-8")
    if moved:
        commit_all(base, f"Moved the seeded product into {project}/")
    logger.info("Moved the seeded product into %s/: %s; left at the root: %s", project, moved, left)
    return record


def record_the_move(state: Any, update: dict[str, Any]) -> None:
    """Add the move to the run's decisions, once. Never raises: a record is evidence, not control flow."""
    try:
        from app.decisions import record_decision

        root = Path(state["repository"].root_path)
        record = json.loads((root / MOVE_RECORD).read_text(encoding="utf-8"))
        known = update.get("decisions") or state.get("decisions") or []
        if any(isinstance(d, dict) and d.get("question") == QUESTION for d in known):
            return
        project, moved, left = record["project"], record["moved"], record["left"]
        rationale = (
            f"The product was seeded at the workspace root and the run works in `{project}/`, so its files were "
            f"moved there and the product is delivered there: {', '.join(moved) or 'nothing'}."
        )
        if left:
            rationale += f" Left at the workspace root: {', '.join(left)}."
        record_decision(
            state, update, point="product_intake", question=QUESTION,
            options=[f"in {project}/", "at the workspace root"], decision=f"in {project}/", rationale=rationale,
        )
    except FileNotFoundError:
        return
    except Exception:  # noqa: BLE001 - see docstring
        logger.debug("Could not record the move of the seeded product", exc_info=True)


__all__ = ["MOVE_RECORD", "QUESTION", "STAYS_AT_THE_ROOT", "move_the_seeded_product_in", "record_the_move"]
