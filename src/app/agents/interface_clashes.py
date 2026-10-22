"""Two work orders of one batch that disagree on an interface become a defect at the join (plan CM.3's parallel half, behind `INTERFACE_CLASH_CHECK`).

Work orders built side by side never share a file, and still meet at their
interfaces: one removes or renames a definition while another, at the same
moment, writes code that calls it by its old name. Neither sees the other's
change, and the break surfaced rounds later as a failing test. With the
switch on, the CI gate reads the batch before committing it: each definition
a work order removed (PH.3's `definitions_changed`) that another work order's
changed file still names is a defect at once, owned by the work order that
still names it. Never model-written.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `INTERFACE_CLASH_CHECK` set to on or off overrides this.
ON_BY_DEFAULT = False
#: Clashes reported, at most.
MOST = 8


def enabled() -> bool:
    return is_on("INTERFACE_CLASH_CHECK", ON_BY_DEFAULT)


def clashes(root: str | Path, outputs: dict[str, Any]) -> list[dict[str, str]]:
    """{name, removed_in, removed_by, used_in, used_by} per clash; [] when off or none. Never raises."""
    if not enabled():
        return []
    try:
        from app.agents.interface_changes import definitions_changed

        root = Path(root)
        files = {stage: [str(f).strip().removeprefix("./").lstrip("/") for f in (getattr(o, "changed_files", None) or [])]
                 for stage, o in (outputs or {}).items()}
        found: list[dict[str, str]] = []
        changes = {stage: definitions_changed(root, changed) for stage, changed in files.items()}
        # A name any work order of the batch defines anew was moved, not removed.
        added_anywhere = {name for changed in changes.values() for added, _ in changed.values() for name in added}
        for stage, changed in changes.items():
            for relative, (added, removed) in changed.items():
                module = re.compile(rf"(?<![\w$]){re.escape(Path(relative).stem)}(?![\w$])")
                for name in removed:
                    if name in added:
                        continue
                    moved = name in added_anywhere
                    word = re.compile(rf"(?<![\w$]){re.escape(name)}(?![\w$])")
                    # The use that breaks: an import line naming the removed
                    # file and the name. A moved name is a clash only there.
                    imported_from = re.compile(
                        rf"^[^\n#/]*\b(?:from|import|require)\b[^\n]*(?<![\w$]){re.escape(Path(relative).stem)}(?![\w$])"
                        rf"[^\n]*(?<![\w$]){re.escape(name)}(?![\w$])", re.M)
                    for other, theirs in files.items():
                        if other == stage:
                            continue
                        for used in theirs:
                            path = root / used
                            if used == relative or not path.is_file():
                                continue
                            text = path.read_text(encoding="utf-8", errors="replace")
                            # A use of the removed definition names the file it came from, as an import
                            # does; a file that defines the name itself, or never names that file, uses
                            # another `get` or `update` of its own.
                            if name in _defined_in(used, text):
                                continue
                            if imported_from.search(text) or (not moved and module.search(text) and word.search(_code_only(text))):
                                found.append({"name": name, "removed_in": relative, "removed_by": stage,
                                              "used_in": used, "used_by": other})
        return found[:MOST]
    except Exception:  # noqa: BLE001 - no clash found is no defect
        logger.debug("Could not check the batch for interface clashes", exc_info=True)
        return []


_COMMENTS_AND_STRINGS = re.compile(r"#[^\n]*|//[^\n]*|/\*.*?\*/|\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'|`(?:\\.|[^`\\])*`", re.S)


def _code_only(text: str) -> str:
    """`text` with its comments and string literals blanked: a name there is no use of it."""
    return _COMMENTS_AND_STRINGS.sub(" ", text)


def _defined_in(relative: str, text: str) -> set[str]:
    """The names `text` defines, in its language's family; empty when the family is unknown."""
    from app.analysis.reachability import FAMILIES, _defined, family_of

    family = FAMILIES.get(family_of(relative))
    return set(_defined(text, family)) if family is not None else set()


_A_CLASH_DESCRIPTION = re.compile(r"`(?P<name>[^`]+)` was removed from `(?P<removed_in>[^`]+)` by \S+, and `(?P<used_in>[^`]+)`")


def still_clashing(root: str | Path, description: str) -> bool | None:
    """Whether the clash a defect describes is still there; None when the description is not a clash's.

    Asked at settlement, as the language service is asked again: a clash is
    settled when the using file no longer imports the name from the file that
    dropped it, or that file defines it again - whatever the fixer named.
    """
    found = _A_CLASH_DESCRIPTION.search(description or "")
    if not found:
        return None
    try:
        root = Path(root)
        name, removed_in, used_in = found["name"], found["removed_in"], found["used_in"]
        removed = root / removed_in
        if removed.is_file() and name in _defined_in(removed_in, removed.read_text(encoding="utf-8", errors="replace")):
            return False
        using = root / used_in
        if not using.is_file():
            return False
        text = using.read_text(encoding="utf-8", errors="replace")
        if name in _defined_in(used_in, text):
            return False
        imported_from = re.compile(
            rf"^[^\n#/]*\b(?:from|import|require)\b[^\n]*(?<![\w$]){re.escape(Path(removed_in).stem)}(?![\w$])"
            rf"[^\n]*(?<![\w$]){re.escape(name)}(?![\w$])", re.M)
        module = re.compile(rf"(?<![\w$]){re.escape(Path(removed_in).stem)}(?![\w$])")
        word = re.compile(rf"(?<![\w$]){re.escape(name)}(?![\w$])")
        return bool(imported_from.search(text) or (module.search(text) and word.search(_code_only(text))))
    except Exception:  # noqa: BLE001 - unmeasured is not settled
        logger.debug("Could not re-check an interface clash", exc_info=True)
        return None


def role_of(stage: str) -> str:
    """The role of a builder's stage, `specialist_<role>_<n>`; "" for any other stage."""
    if not stage.startswith("specialist_"):
        return ""
    role, _, index = stage[len("specialist_"):].rpartition("_")
    return role if role and index.isdigit() else ""


def defects(root: str | Path, outputs: dict[str, Any], owner_of: Any) -> list[Any]:
    """The clashes as defects for the CI gate's review. Never raises."""
    from app.agents.specialists import ReportedDefect
    from app.graph.engineering import FAILS_WHEN_IT_RUNS

    made = []
    for clash in clashes(root, outputs):
        made.append(ReportedDefect(
            description=(f"`{clash['name']}` was removed from `{clash['removed_in']}` by {clash['removed_by']}, and "
                         f"`{clash['used_in']}`, written by {clash['used_by']} in the same batch, still uses it"
                         f"{FAILS_WHEN_IT_RUNS}"),
            severity="major",
            reproduction_steps=f"Read `{clash['used_in']}`: it names `{clash['name']}`, which `{clash['removed_in']}` no longer defines.",
            expected_behavior=f"Every use of `{clash['name']}` follows the interface `{clash['removed_in']}` defines now.",
            actual_behavior=f"{clash['used_by']} still uses the old name; {clash['removed_by']} removed it.",
            affected_files=[clash["used_in"], clash["removed_in"]],
            owner=owner_of(clash["used_by"]),
        ))
    return made


__all__ = ["MOST", "ON_BY_DEFAULT", "clashes", "defects", "enabled", "role_of", "still_clashing"]
