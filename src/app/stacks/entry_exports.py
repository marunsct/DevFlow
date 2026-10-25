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
