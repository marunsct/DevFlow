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

#: Retained for the tests that pin the old behaviour's boundary. The digest is
#: now injected on every call: `override` does not persist it, so "repeating
#: it" costs one copy per request and accumulates nothing, while injecting it
#: once left the agent with no map from the second call onwards.
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


#: Names that are workspace plumbing rather than anything a stage can learn
#: from. A run's workspace is created with these already in it.
_NOT_EVIDENCE = {".gitignore", ".project-directory", ".gitkeep", ".gitattributes"}


def _nothing_here_is_evidence(names: list[str]) -> bool:
    """Whether the workspace holds only the plumbing it was created with.

    The measured case, and the one the empty-workspace branch does not reach.
    `product_manager` runs before anything is built, and its prompt tells it to
    ground every conclusion in repository evidence. It is handed a listing of
    one `.gitignore`, which is a listing and not an answer, and the opening
    move is a guess at a file a repository would usually have: measured across
    the transcripts, four runs and four `read_repository_file` calls, all of
    them `README.md`, all answered "File does not exist within the repository".

    Run d6297b2f is the proof this needs saying rather than listing. Its first
    model call carried the digest

        The workspace as it stands. This is what is there ...
          .gitignore (9 lines)

    and its first tool call was `read_repository_file('README.md')`.
    """
    return bool(names) and all(
        Path(name).name in _NOT_EVIDENCE or Path(name).name.startswith(".")
        for name in names
    )


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
        # An empty workspace is a fact, and saying nothing is not the same as
        # saying it.
        #
        # This branch is the rarer one: a run's workspace is seeded with a
        # `.gitignore`, so `names` is almost never empty and the listing below
        # is what `product_manager` actually sees. `_nothing_here_is_evidence`
        # carries the same sentence into that case, which is the one measured.
        #
        # The unreadable case above still produces nothing, because that one
        # genuinely is unknown - `list_repository_files` raises for a root that
        # is not there and returns `[]` only when it looked and found nothing.
        return (
            "The workspace is empty. Nothing has been built yet, so there is "
            "nothing to read and nothing to list - no README, no manifest, no "
            "existing implementation. The brief you were given is the whole of "
            "the evidence available to you. Do not spend a call confirming this."
        )

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
    if _nothing_here_is_evidence(names):
        return (
            "The workspace holds nothing but the files it was created with:\n"
            + "\n".join(lines)
            + "\nNothing has been built yet - there is no README, no manifest "
            "and no existing implementation to consult. The brief you were "
            "given is the whole of the evidence available to you. Do not spend "
            "a call looking for a file a repository would usually have."
        )
    return (
        "The workspace as it stands. This is what is there - you do not need to "
        "list the directories to find out:\n" + "\n".join(lines) + more + "\n"
        "Read the files you actually need; the names after a filename are its "
        "top-level definitions."
    )


def build_workspace_digest_middleware(repo_root: str) -> Any:
    """Middleware that hands a stage the workspace listing on every call.

    Built as middleware rather than added to each request builder because there
    are thirteen of those, and reaching twelve of thirteen is the specific
    mistake this codebase has made four times.

    On EVERY call, not just the first. Injected once, the listing is in the
    opening request and nowhere afterwards - `override` does not write it to
    stored history - so from the second call the agent has no map and goes
    looking again. Measured on run-2eb3aa24's `principal_architect`: six
    identical `ls {'path': '/'}` and four `ls` of a project directory that did
    not exist yet, in one stage, against a digest that had already said what
    was there. It is also why the listing count fell only 43% (46 to 26) when
    this middleware shipped rather than to nearly nothing.

    Re-injecting costs one copy per request and accumulates nothing, because
    `override` applies to that call alone. It is also always current, so an
    agent sees the files it has just written - which the first-call-only
    version could never show.

    This does not address a re-READ of a file's contents; a listing is not
    content. Those were measured separately and are not eviction: compaction
    triggers at 70,200 tokens and the largest stage of run-1d1b6c9c carried
    about 22,600, with no compaction in the logs at all.
    """
    from langchain.agents.middleware import AgentMiddleware

    class WorkspaceDigestMiddleware(AgentMiddleware):
        """Append the digest to the opening request, not to stored history."""

        name = "WorkspaceDigestMiddleware"

        def wrap_model_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
            messages = getattr(request, "messages", None)
            if not isinstance(messages, list):
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
