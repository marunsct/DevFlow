"""A pack's entry file keeps exporting what the pack's own files import from it (behind `PACK_ENTRY_EXPORTS_KEPT`).

Measured on a small-model run: the Hono pack builds its app in `createApp()` in `src/app.ts`, which `src/main.ts` serves
and its unit smoke test calls. Drafting rewrote `src/app.ts` with a default export and no `createApp`, and seven test
files the same model wrote imported the missing name; one fix restored it, but only after a round of reverts.

A pack names the exports of its entry files that the rest of its scaffold depends on (`StackPack.required_exports`).
When a stage drops one, the round raises a defect that says which name, which files import it, and what the pack
wrote, before the importers' own errors arrive one by one.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.switches import is_on

#: Off in code like every switch; the compose file turns it on.
ON_BY_DEFAULT = False


def enabled() -> bool:
    return is_on("PACK_ENTRY_EXPORTS_KEPT", ON_BY_DEFAULT)


def _exports(text: str, name: str) -> bool:
    declared = re.search(rf"^\s*export\s+(?:declare\s+)?(?:async\s+)?(?:function\*?|const|let|var|class)\s+{re.escape(name)}\b", text, re.M)
    if declared:
        return True
    for listed in re.findall(r"^\s*export\s*(?:type\s*)?\{([^}]*)\}", text, re.M):
        for part in listed.split(","):
            if re.split(r"\s+as\s+", part.strip())[-1].strip() == name:
                return True
    return False


def what_the_entry_no_longer_exports(repo_root: str | Path) -> list[tuple[str, str]]:
    """(file relative to the workspace, name) for each export the pack's scaffold depends on that its file lost.

    Never raises: a project without a pack, or a file that cannot be read, has nothing to report.
    """
    if not enabled():
        return []
    try:
        from app.stacks import contract

        found = contract.the_pack(repo_root)
        if found is None or not contract.scaffolded(found[1]):
            return []
        pack, record = found
        wanted = getattr(pack, "required_exports", None) or {}
        project = str(record.get("project") or "")
        lost: list[tuple[str, str]] = []
        for relative, names in wanted.items():
            path = Path(repo_root) / project / relative
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                lost += [(f"{project}/{relative}" if project else relative, name) for name in names]
                continue
            lost += [(f"{project}/{relative}" if project else relative, name) for name in names if not _exports(text, name)]
        return lost
    except Exception:  # noqa: BLE001 - a check that cannot run finds nothing
        return []


def _a_required_parameter(text: str, name: str) -> str:
    """The first parameter `name`'s declaration requires (no default, not optional, not a rest); "" when none or unread."""
    found = re.search(rf"^\s*export\s+(?:default\s+)?(?:async\s+)?function\*?\s+{re.escape(name)}\s*(?:<[^>]*>)?\s*\(([^)]*)\)", text, re.M) \
        or re.search(rf"^\s*(?:export\s+)?(?:const|let|var)\s+{re.escape(name)}\s*(?::[^=]+)?=\s*(?:async\s+)?\(([^)]*)\)\s*(?::[^=]+)?=>", text, re.M)
    if not found:
        return ""
    for part in [p.strip() for p in found.group(1).split(",") if p.strip()]:
        head = re.split(r"[:=]", part, 1)[0].strip()
        if "=" in part or head.endswith("?") or head.startswith("..."):
            continue
        return head
    return ""


def what_the_start_file_cannot_call(repo_root: str | Path) -> list[tuple[str, str, str]]:
    """(file, name, parameter) for each required export the scaffold calls bare that now requires an argument.

    Measured on one run: `createApp(storage)` took the store as a parameter; the pack's start file calls `createApp()`
    with none, every handler read `undefined.storage` and answered 500, and two sprint attempts went on fixes to the
    routes. Never raises.
    """
    if not enabled():
        return []
    try:
        from app.stacks import contract

        found = contract.the_pack(repo_root)
        if found is None or not contract.scaffolded(found[1]):
            return []
        pack, record = found
        if not getattr(pack, "required_exports_called_bare", False):
            return []
        project = str(record.get("project") or "")
        wrong: list[tuple[str, str, str]] = []
        for relative, names in (getattr(pack, "required_exports", None) or {}).items():
            try:
                text = (Path(repo_root) / project / relative).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for name in names:
                needed = _a_required_parameter(text, name)
                if needed:
                    wrong.append((f"{project}/{relative}" if project else relative, name, needed))
        return wrong
    except Exception:  # noqa: BLE001 - a check that cannot run finds nothing
        return []


def still_raised(repo_root: str | Path, description: str) -> bool | None:
    """Whether a pack-contract defect with this description would be raised again now; None when it is not one.

    A defect about the scaffold's contract is settled by the check that raised it, not by unit tests: measured on one
    run, `createApp()` was made callable bare, and the defect was left open because unrelated unit tests failed; the
    attempt was spent and the sprint planned again over a green suite.
    """
    text = str(description or "")
    if " no longer exports `" not in text and " but the scaffold's start file" not in text:
        return None
    current = [f"{path} no longer exports `{name}`" for path, name in what_the_entry_no_longer_exports(repo_root)]
    current += [f"{path} declares `{name}(" for path, name, _ in what_the_start_file_cannot_call(repo_root)]
    return any(text.startswith(found) for found in current)

