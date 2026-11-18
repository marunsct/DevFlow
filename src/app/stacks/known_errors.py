"""A defect whose text carries an error the stack pack knows is given that error's cause.

Measured on one run: a delete answered with `c.body('', 204)` threw "Invalid response status code 204" on a Hono
service; the fixers were shown the message, rewrote the handler twice without changing that call, and the sprint was
planned again over a one-line fix. The pack names such errors once (`StackPack.known_errors`); nothing here names a
stack.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: How the cause is introduced in a defect's actual behaviour; never added twice.
KNOWN_CAUSE = "Known cause on this stack:"


def _runs_node_test(pack: Any) -> bool:
    """Whether the pack's unit tests run on `node --test`, by its kept test script or its manifest."""
    script = str((getattr(pack, "kept_scripts", None) or {}).get("test") or "")
    manifest = str((getattr(pack, "files", None) or {}).get("package.json") or "")
    return "node --test" in script or "node --test" in manifest


def _known(repo_root: str | Path) -> dict[str, str]:
    """The project's pack's known errors, by phrase; raises when the contract cannot be read."""
    from app.stacks import contract

    found = contract.the_pack(Path(repo_root))
    known = dict(getattr(found[0], "known_errors", None) or {}) if found else {}
    if found and _runs_node_test(found[0]):
        from app.stacks.packs._javascript import NODE_TEST_KNOWN_ERRORS

        known = {**NODE_TEST_KNOWN_ERRORS, **known}
    return known


def with_known_causes_in_lines(repo_root: str | Path, lines: list[str]) -> list[str]:
    """`lines` - what the compiler or language service reports on a stage's own writes - each carrying an error the
    project's pack knows followed by its cause. Never raises.

    Deep review 2026-11-18, item E4: the causes were added only at triage, after a test round had failed on the error;
    the stage that wrote it was told the compiler's message alone, at the moment it could still fix it in one change.
    """
    try:
        known = _known(repo_root)
    except Exception:  # noqa: BLE001 - the lines as reported stand
        return lines
    if not known:
        return lines
    out = []
    for line in lines:
        text = str(line)
        causes = [cause for phrase, cause in known.items() if phrase.lower() in text.lower() and cause not in text]
        out.append(text + "".join(f"\n  {KNOWN_CAUSE} {cause}" for cause in causes))
    return out


def with_known_causes(repo_root: str | Path, defects: list[Any]) -> list[Any]:
    """`defects`, each whose text carries an error the project's pack knows given its cause. Never raises."""
    try:
        known = _known(repo_root)
    except Exception:  # noqa: BLE001 - the defects as raised stand
        return defects
    if not known:
        return defects
    out = []
    for defect in defects:
        text = f"{getattr(defect, 'description', '')} {getattr(defect, 'actual_behavior', '')}".lower()
        actual = str(getattr(defect, "actual_behavior", "") or "")
        causes = [cause for phrase, cause in known.items() if phrase.lower() in text and cause not in actual]
        if causes:
            try:
                defect = defect.model_copy(update={
                    "actual_behavior": (actual + "\n" + "\n".join(f"{KNOWN_CAUSE} {c}" for c in causes)).strip()})
                logger.info("A defect carries an error its stack pack knows; its cause was added")
            except Exception:  # noqa: BLE001 - the defect as raised stands
                pass
        out.append(defect)
    return out


__all__ = ["KNOWN_CAUSE", "with_known_causes", "with_known_causes_in_lines"]
