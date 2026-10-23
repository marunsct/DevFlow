"""A run's handover pack: what the team that maintains the product needs, in one archive.

The workspace holds the product, and beside it everything that explains it -
the specification, the plan, each sprint's record and summary, the reviews,
every decision with its reason, and the acceptance suite the product was held
to. They were readable one file at a time on the run's page; a team taking the
product over wants them together.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

#: What goes in besides `docs/`: the decision record and the locked suite.
_RECORDS = (".harness/decisions.json",)
#: The most one pack may hold, uncompressed.
MOST_BYTES = 50 * 1024 * 1024


def _acceptance_directory(root: Path) -> str | None:
    try:
        from app.stacks import contract
        from app.tools.repository import pinned_project_directory

        found = contract.the_pack(root)
        project = pinned_project_directory(root)
        directory = getattr(found[0], "acceptance_dir", "") if found else ""
        return f"{project}/{directory}" if project and directory else None
    except Exception:  # noqa: BLE001 - the pack without the suite
        return None


def files_of(repo_root: str | Path) -> list[str]:
    """The workspace-relative files a handover pack holds, in order."""
    root = Path(repo_root)
    found: list[str] = []
    for top in ("docs", _acceptance_directory(root)):
        if not top or not (root / top).is_dir():
            continue
        from app.analysis.walk import files_under

        found += sorted(
            path.relative_to(root).as_posix() for path in files_under(root / top, ("node_modules",))
            if "node_modules" not in path.parts
        )
    found += [name for name in _RECORDS if (root / name).is_file()]
    return found


def build(repo_root: str | Path, run_id: str) -> bytes:
    """The pack as a zip archive, every file under a folder named for the run."""
    root = Path(repo_root)
    buffer = io.BytesIO()
    used = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for relative in files_of(root):
            size = (root / relative).stat().st_size
            if used + size > MOST_BYTES:
                break
            archive.write(root / relative, f"{run_id}-handover/{relative}")
            used += size
    return buffer.getvalue()
