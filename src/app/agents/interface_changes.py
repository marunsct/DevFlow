"""A builder's report names every interface it added or removed, written by the harness (plan PH.3, behind `INTERFACE_CHANGES_NAMED`).

The work orders after a builder learn what it changed from its `decisions`,
and those named a choice where they named anything: a function renamed in
one module and still called by its old name in another reached the next work
order as nothing. The harness can read it instead of asking for it: the
definitions each changed file gained or lost against the last commit, in the
language patterns `analysis.reachability` already has. Each change the
builder's own decisions do not mention is added to them, so the decision
ledger (CM.2) and the next work order receive it.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `INTERFACE_CHANGES_NAMED` set to on or off overrides this.
ON_BY_DEFAULT = False
#: Changed files read, at most.
MOST_FILES = 20


def enabled() -> bool:
    return is_on("INTERFACE_CHANGES_NAMED", ON_BY_DEFAULT)


def _before(root: Path, relative: str) -> str:
    try:
        done = subprocess.run(["git", "-C", str(root), "show", f"HEAD:{relative}"],
                              capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout if done.returncode == 0 else ""


def definitions_changed(root: str | Path, changed_files: list[str]) -> dict[str, tuple[list[str], list[str]]]:
    """Changed file -> (definitions added, definitions removed) against the last commit; files with neither left out. Never raises."""
    from app.analysis.reachability import FAMILIES, _defined, family_of

    root = Path(root)
    found: dict[str, tuple[list[str], list[str]]] = {}
    for relative in [str(f).strip().removeprefix("./").lstrip("/") for f in changed_files if str(f).strip()][:MOST_FILES]:
        try:
            family = FAMILIES.get(family_of(relative))
            path = root / relative
            if family is None:
                continue
            after = _defined(path.read_text(encoding="utf-8", errors="replace"), family) if path.is_file() else set()
            before = _defined(_before(root, relative), family)
            if after != before:
                found[relative] = (sorted(after - before), sorted(before - after))
        except Exception:  # noqa: BLE001 - one file unread is one file fewer
            logger.debug("Could not read the interface change of %s", relative, exc_info=True)
    return found


def changes(root: str | Path, changed_files: list[str]) -> list[str]:
    """One line per changed file whose definitions changed against the last commit. Never raises."""
    lines: list[str] = []
    for relative, (added, removed) in definitions_changed(root, changed_files).items():
        try:
            parts = []
            if added:
                parts.append("added " + ", ".join(f"`{n}`" for n in added[:10]))
            if removed:
                parts.append("removed " + ", ".join(f"`{n}`" for n in removed[:10]))
            lines.append(f"Interface of `{relative}`: " + "; ".join(parts) + ".")
        except Exception:  # noqa: BLE001 - one file unread is one line fewer
            logger.debug("Could not read the interface change of %s", relative, exc_info=True)
    return lines


def with_them(output: Any, root: str | Path) -> Any:
    """`output` with each interface change its decisions do not already name added to them; as it was when off."""
    if not enabled() or output is None:
        return output
    try:
        decisions = [str(d) for d in (getattr(output, "decisions", None) or [])]
        said = " ".join(decisions)
        missing = [line for line in changes(root, list(getattr(output, "changed_files", None) or []))
                   if not all(name in said for name in _names_in(line))]
        if not missing:
            return output
        return output.model_copy(update={"decisions": [*decisions, *missing]})
    except Exception:  # noqa: BLE001 - the report stands as it was
        logger.debug("Could not add the interface changes", exc_info=True)
        return output


def _names_in(line: str) -> list[str]:
    import re

    return re.findall(r"`([^`]+)`", line)[1:]


__all__ = ["ON_BY_DEFAULT", "changes", "definitions_changed", "enabled", "with_them"]
