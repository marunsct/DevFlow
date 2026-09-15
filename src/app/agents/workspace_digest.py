"""Tell a stage what is in the workspace before it starts looking.

Every stage begins the same way: `ls /`, `ls /project`, then a read of each
file it might care about. It has to, because an agent is built per stage and
none of them can see what an earlier one learned.

Measured on run-61c5a5b6: 257 `read_file` calls over 22 distinct files, and the
opening moves of `technical_lead`, `test_round_0`, `milestone_review`,
`security_review` and every specialist are near-identical - list the root, list
the project, read `app.js`, read `index.html`, read the tests. Each of those is
a model turn carrying the whole conversation, and the answer was the same every
time.

A digest does not replace reading a file. It replaces *finding out what there
is to read*, which is the part that was rediscovered twenty-five times. An
agent that knows `app.js` is 229 lines and exports `createTask`, `toggleTask`
and `renderTasks` can go straight to the one it needs.

Injected into the first model call of a stage and never written to state, on
the same reasoning as `app.agents.response_reminder`: it is context the model
needs once, not a message that should accumulate.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Beyond this the digest costs more context than the calls it saves.
MAX_FILES = 40

#: Only the first model call of a stage. By the second the agent has the
#: digest, and repeating it would be the accumulation this avoids.
FIRST_CALL_MESSAGES = 2

_SYMBOL_PATTERNS = (
    re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", re.M),
    re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(", re.M),
    re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)", re.M),
    re.compile(r"^\s*def\s+([A-Za-z_][\w]*)", re.M),
    re.compile(r"^\s*class\s+([A-Za-z_][\w]*)", re.M),
)

_CODE_SUFFIXES = {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".py"}


def _symbols(text: str, limit: int = 8) -> list[str]:
    """Top-level names a reader would look for, in source order."""
    found: list[str] = []
    for pattern in _SYMBOL_PATTERNS:
        for match in pattern.finditer(text):
            name = match.group(1)
            if name not in found:
                found.append(name)
            if len(found) >= limit:
                return found
    return found


def _in_reading_order(root: Path, names: list[str]) -> list[str]:
    """The project first, then documents, then everything else.

    Alphabetical order put dotfiles at the top, so the cut at `max_files` fell
    on the application: on run-61c5a5b6's workspace the listing reached
    `simple-to-do-list-app/README.md` and stopped, hiding `app.js` behind
    "... and 13 more". The files a stage came here for must survive the cut.
    """
    try:
        from app.tools.repository import pinned_project_directory

        project = pinned_project_directory(root)
    except Exception:  # noqa: BLE001 - ordering must never fail the digest
        project = None

    def rank(name: str) -> tuple[int, str]:
        if project and name.startswith(f"{project}/"):
            return (0, name)
        if name.startswith("docs/"):
            return (1, name)
        return (2, name)

    return sorted(names, key=rank)


def render_workspace_digest(repo_root: str | Path, max_files: int = MAX_FILES) -> str:
    """One compact listing of what is in the workspace, or "" if nothing is.

    Never raises. A digest that fails a stage would cost far more than the
    calls it saves, so an unreadable workspace simply produces no digest and
    the agent explores the way it always did.
    """
    try:
        from app.tools.repository import list_repository_files

        root = Path(repo_root)
        names = list_repository_files(root)
    except Exception:  # noqa: BLE001 - see docstring
        logger.debug("Could not build a workspace digest for %s", repo_root, exc_info=True)
        return ""

    if not names:
        return ""

    lines: list[str] = []
    for name in _in_reading_order(root, names)[:max_files]:
        path = root / name
        try:
            if path.stat().st_size > 512 * 1024:
                lines.append(f"  {name} (large)")
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        count = text.count("\n") + 1
        entry = f"  {name} ({count} lines)"
        if path.suffix.lower() in _CODE_SUFFIXES:
            names_found = _symbols(text)
            if names_found:
                entry += ": " + ", ".join(names_found)
        lines.append(entry)

    if not lines:
        return ""

    more = f"\n  ... and {len(names) - max_files} more" if len(names) > max_files else ""
    return (
        "The workspace as it stands. This is what is there - you do not need to "
        "list the directories to find out:\n" + "\n".join(lines) + more + "\n"
        "Read the files you actually need; the names after a filename are its "
        "top-level definitions."
    )


def build_workspace_digest_middleware(repo_root: str) -> Any:
    """Middleware that hands a stage the workspace listing on its first call.

    Built as middleware rather than added to each request builder because there
    are thirteen of those, and reaching twelve of thirteen is the specific
    mistake this codebase has made four times.
    """
    from langchain.agents.middleware import AgentMiddleware

    class WorkspaceDigestMiddleware(AgentMiddleware):
        """Append the digest to the opening request, not to stored history."""

        name = "WorkspaceDigestMiddleware"

        def wrap_model_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
            messages = getattr(request, "messages", None)
            if not isinstance(messages, list) or len(messages) > FIRST_CALL_MESSAGES:
                return handler(request)
            if os.environ.get("WORKSPACE_DIGEST", "1").lower() in ("0", "false", "off"):
                return handler(request)
            digest = render_workspace_digest(repo_root)
            if not digest:
                return handler(request)
            try:
                request = request.override(
                    messages=[*messages, {"role": "user", "content": digest}]
                )
            except Exception:  # noqa: BLE001 - never fail a call over a hint
                return handler(request)
            return handler(request)

    return WorkspaceDigestMiddleware()


__all__ = [
    "FIRST_CALL_MESSAGES",
    "MAX_FILES",
    "build_workspace_digest_middleware",
    "render_workspace_digest",
]
