"""The product files a server's logged traceback names, for the failing criterion's defect to name (LF.1401, the rest).

Measured over the last 45 runs: seven rewrites after a surrender found no file, all for criteria the acceptance suite
judges - their defect said "Affected files: (none identified)", and their failure named only the acceptance test,
which such a rewrite never takes. On the latest medium run, every sign-up answered 500 while the server logged the
cause with its frames: `sqlite3.OperationalError: no such column: users.username`, raised in
`task_management_dashboard/routes.py` line 276, `register_user`. The defect carried that log in its account and named
no file.

So the files a logged trace names - each frame's path, under the workspace or the sandbox's mount, that is one of the
product's own files (not a test, a dependency or a build's output) - are the defect's affected files, the frame that
raised first: a trace that lists its frames outermost first (`File "<path>", line N`) is read from its end. Only the
errors the server logged are read (`suite.what_the_server_logged` keeps no access line), so a 500 answered without a
trace names nothing here. Nothing here names a language: the two ways a trace writes a frame are read whatever wrote
it. Never raises.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

#: Files a defect is given from one log at most.
MOST_FILES = 4
#: A frame written `File "<path>", line N` - outermost first.
_OUTERMOST_FIRST = re.compile(r'File "(?P<path>[^"\n]+)", line \d+')
#: A frame written `<path>:N` or `<path>:N:M`, as most runtimes print one - innermost first.
_INNERMOST_FIRST = re.compile(r"(?:file://)?(?P<path>(?:/|\.{0,2}/)?(?:[\w@.-]+/)*[\w@.-]+\.[A-Za-z]{1,6}):\d+")
#: Folders whose files are no product code of its own.
_NOT_THE_PRODUCT_S = ("node_modules/", ".venv/", "site-packages/", "dist-packages/", "/.next/", ".next/", "vendor/")


def _relative(path: str, root: Path) -> str:
    from app.agents.workspace_paths import THE_SANDBOX_S_MOUNT

    path = path.strip()
    for base in (str(root).rstrip("/") + "/", THE_SANDBOX_S_MOUNT.rstrip("/") + "/"):
        if path.startswith(base):
            return path[len(base):]
    return path.lstrip("./") if not path.startswith("/") else ""


def files_the_log_names(root: Any, logged: str, most: int = MOST_FILES) -> list[str]:
    """The product's own files the frames in `logged` name, the frame that raised first; [] for none."""
    try:
        from app.analysis.file_kinds import classify_file

        base = Path(str(root))
        frames: list[str] = []
        for line in str(logged or "").splitlines():
            outer = [m.group("path") for m in _OUTERMOST_FIRST.finditer(line)]
            if outer:
                frames[:0] = list(reversed(outer))
                continue
            frames.extend(m.group("path") for m in _INNERMOST_FIRST.finditer(line))
        found: list[str] = []
        for frame in frames:
            relative = _relative(frame, base)
            if not relative or relative in found or any(part in f"/{relative}" for part in _NOT_THE_PRODUCT_S):
                continue
            if (base / relative).is_file() and classify_file(relative) == "application":
                found.append(relative)
            if len(found) >= most:
                break
        return found
    except Exception:  # noqa: BLE001 - a defect that names no file is the defect as it was
        return []


__all__ = ["MOST_FILES", "files_the_log_names"]
