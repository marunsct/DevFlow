"""Let an agent name a file the way the workflow told it to.

The agent filesystem (`ls`, `read_file`, `glob`, `grep`) is a
`FilesystemBackend` rooted at the run's workspace in virtual mode, so the
workspace root is `/` and the project is `/todo-app`. But several prompts hand
the agent `repository.root_path` - the real host path, such as
`/app/data/workspaces/low2-run-95ca3f72-.../` - and tool errors quote it back.
An agent that believes that is where it is asks for
`/app/data/workspaces/low2-run-.../todo-app/package.json`, which resolves under
the root a second time and is never found.

Measured on run-95ca3f72: seven `read_file` calls and one `ls` failed this way,
every one of them for a file that existed. The agent cannot tell a real
"missing file" from this, so it retried the same path three times in a row.

The workflow could stop telling agents the host path, and should. This is the
other half: whichever spelling arrives, it means the same file.
"""

from __future__ import annotations

import posixpath
from collections.abc import Callable
from pathlib import Path
from typing import Any

#: Filesystem tools whose path argument is rooted at the workspace.
_PATH_ARGUMENTS: dict[str, str] = {
    "ls": "path",
    "read_file": "file_path",
    "glob": "path",
    "grep": "path",
}


def workspace_relative(path: str, repo_root: str) -> str:
    """The same file, named from the workspace root.

    Leaves anything that is already virtual-root-relative alone; only a path
    that starts with the host workspace is rewritten.
    """
    if not path or not repo_root:
        return path

    root = repo_root.rstrip("/")
    if not root:
        return path

    normalised = posixpath.normpath(path)
    if normalised == root:
        return "/"
    if normalised.startswith(root + "/"):
        return "/" + normalised[len(root) + 1 :]
    return path



def without_an_invented_root(path: str, repo_root: str) -> str:
    """The same file with a made-up top directory removed, if that is what it is.

    `workspace_relative` handles the host path the workflow itself hands out.
    This handles the other direction: a root the model invents. The brief says
    "The workspace is rooted at '/'" and the model writes `/workspace/docs/...`
    anyway.

    Measured on run-44653bd2: 16 `read_file` calls for
    `/workspace/docs/technical_specification.md` and two `ls` of `/workspace`,
    18 of that run's 33 tool failures, every one for a file that existed one
    level down. The "there is a file of that name at ..." hint fired on every
    one of them and the model asked again regardless - which is the case for
    rewriting rather than explaining.

    Deliberately evidence-led rather than a list of known prefixes. It rewrites
    only when the path as given does not exist *and* the path without its first
    segment does, so a workspace that really does contain a `workspace/`
    directory is untouched, and a genuinely missing file still fails as a
    missing file.
    """
    if not path or not repo_root:
        return path
    normalised = posixpath.normpath(path)
    if not normalised.startswith("/"):
        return path
    segments = [part for part in normalised.split("/") if part]
    if len(segments) < 2:
        return path

    root = Path(repo_root)
    try:
        if (root / "/".join(segments)).exists():
            return path
        without_first = "/" + "/".join(segments[1:])
        if (root / "/".join(segments[1:])).exists():
            return without_first
    except OSError:  # noqa: PERF203 - an unreadable workspace rewrites nothing
        return path
    return path

#: What `read_file` returns when the model does not say. The tool's own default
#: is 100 lines, which is less than half of what the tool-result budget can
#: already afford and turns reading one source file into several model turns.
#:
#: Measured on run-61c5a5b6: 148 of 257 `read_file` calls carried an explicit
#: offset - they were paging, not sampling. `tests.test.js` alone was paged 57
#: times. Reading the project's six files from end to end costs 25 calls at 100
#: lines and 8 at 400, and every saved call is a whole model turn carrying the
#: entire conversation.
#:
#: Raising it is not the same as reading more: an agent that paged to the end
#: put exactly the same content into the context either way, in more envelopes
#: and more turns. Only an agent that would have stopped after the first page
#: reads more, and `read_file` still reports that lines remain, so the choice to
#: continue stays with the model.
DEFAULT_READ_LINES = 400


def rewrite_tool_arguments(
    name: str, arguments: dict[str, Any], repo_root: str
) -> dict[str, Any]:
    """A copy of `arguments` with workspace paths and read windows normalised."""
    changed = dict(arguments)

    key = _PATH_ARGUMENTS.get(name)
    if key is not None:
        value = arguments.get(key)
        if isinstance(value, str):
            # Host path first - that is the spelling the workflow itself hands
            # out - then a root the model invented, which only resolves against
            # what is actually on disk.
            resolved = workspace_relative(value, repo_root)
            changed[key] = without_an_invented_root(resolved, repo_root)

    # Only when the model did not ask for a window. The raw arguments still
    # distinguish that from an explicit `limit`, because the schema default is
    # filled in later, at validation - so a model that asked for 30 lines gets
    # 30.
    if name == "read_file" and "limit" not in arguments:
        changed["limit"] = DEFAULT_READ_LINES

    return arguments if changed == arguments else changed


def build_workspace_path_middleware(repo_root: str) -> Any:
    """Middleware that accepts the host workspace path as a name for `/`."""
    from langchain.agents.middleware import AgentMiddleware

    class WorkspacePathMiddleware(AgentMiddleware):
        """Normalise filesystem paths before the built-in tools see them."""

        name = "WorkspacePathMiddleware"

        def wrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
            call = getattr(request, "tool_call", None)
            if isinstance(call, dict):
                arguments = call.get("args")
                if isinstance(arguments, dict):
                    rewritten = rewrite_tool_arguments(
                        call.get("name", ""), arguments, repo_root
                    )
                    if rewritten is not arguments:
                        request = request.override(
                            tool_call={**call, "args": rewritten}
                        )
            return handler(request)

    return WorkspacePathMiddleware()


__all__ = [
    "DEFAULT_READ_LINES",
    "build_workspace_path_middleware",
    "rewrite_tool_arguments",
    "workspace_relative",
]
