"""Let an agent name a file the way the workflow told it to.

The agent filesystem (`ls`, `read_file`, `glob`, `grep`) is a
`FilesystemBackend` rooted at the run's workspace in virtual mode, so the
workspace root is `/` and the project is `/todo-app`. But several prompts hand
the agent `repository.root_path` - the real host path, such as
`/app/data/workspaces/low2-one run-.../` - and tool errors quote it back.
An agent that believes that is where it is asks for
`/app/data/workspaces/low2-run-.../todo-app/package.json`, which resolves under
the root a second time and is never found.

Measured on one run: seven `read_file` calls and one `ls` failed this way,
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


def the_same_place(value: str) -> str:
    """One spelling for one location in the workspace.

    The workspace is rooted at `/`, so `/task-manager/app.js`,
    `task-manager/app.js` and `./task-manager/app.js` are the same file and
    every tool here reads all three. The repeat guard keyed on the raw
    arguments, so they were three different files to it and each got its own
    allowance before anything was said.

    Measured on one run's `specialist_ui_ux_1`: `style.css` read six
    times as `/task-manager/style.css` and four more as
    `task-manager/style.css`, and `app.js` six and four the same way. Ten
    reads of one unchanged file in one stage, counted as two runs of four and
    six, so the notice arrived late twice instead of once early.

    Deliberately textual and deliberately not `Path.resolve`: this normalises
    a string the model wrote, which may name a file that does not exist, and
    touching the filesystem to compare two arguments would be both slower and
    wrong.
    """
    text = str(value or "").strip().replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")
    parts: list[str] = []
    for part in text.split("/"):
        if part in {"", "."}:
            continue
        if part == ".." and parts and parts[-1] != "..":
            parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


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

    Measured on one run: 16 `read_file` calls for
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
#: Measured on one run: 148 of 257 `read_file` calls carried an explicit
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

#: What `grep` answers with when the model does not say. The tool's own default
#: is `files_with_matches`: the names of the files that matched, and nothing
#: of what matched in them.
#:
#: Measured over twelve runs: 35 of 36 `grep` calls left the mode unset, and
#: 28 of the answers were file names alone. 20 of those calls searched a single
#: named file, so the answer was that file's own name back - a yes or no, with
#: no line and no text. One architecture review searched its specification for
#: eight different words that way, and for "required" twice, then read the
#: whole file anyway.
#:
#: `content` answers the same question and the one behind it: each matching
#: line, numbered, under the file it is in. The file names are still there. It
#: is held to the same result budget as every other tool answer, so a search
#: that matches everywhere is cut short with a note, not dumped whole. A model
#: that asks for file names or counts still gets them.
DEFAULT_GREP_OUTPUT = "content"

#: Characters that make a `glob` pattern a pattern rather than a name.
_GLOB_WILDCARDS = frozenset("*?[")


def a_name_fragment(pattern: Any) -> str:
    """The text a `glob` pattern with no wildcard in it is looking for, or ''.

    `glob` matches a pattern against whole file names, so `taskStore` finds a
    file named exactly `taskStore` and never `taskStore.js`, and `.js` finds
    nothing at all. The model writes it as a search for names that contain it.

    Measured over twenty runs: 36 of 71 `glob` calls were a bare fragment like
    that - `.js`, `playwright`, `addTask`, `.config` - and 34 came back "No
    files found", including `.js` three times in a project full of `.js`
    files. 62 of the 71 found nothing.

    Only a fragment without a directory in it: `docs/spec.md` names a place,
    and is left to mean what it says.
    """
    if not isinstance(pattern, str):
        return ""
    text = pattern.strip()
    if not text or "/" in text or _GLOB_WILDCARDS & set(text):
        return ""
    return text


def nothing_is_named(fragment: str, path: Any) -> str:
    """What an empty search for names containing `fragment` means, and what to use instead.

    The rest of those empty answers were a directory name (`tests`, `modules`)
    or words from inside a file (`addTask`, `export`) - neither of which a
    file name ever contains, however the pattern is written.
    """
    where = f"'{path}'" if isinstance(path, str) and path.strip("/ ") else "the workspace"
    return (
        f"No file in {where} has a name containing '{fragment}'. `glob` matches "
        "file names only - not directory names, and not the text inside files. "
        "To see what a directory holds, use `ls`; to find where something is "
        "written, use `grep`."
    )


def rewrite_tool_arguments(
    name: str, arguments: dict[str, Any], repo_root: str
) -> dict[str, Any]:
    """A copy of `arguments` with workspace paths, read windows and search output normalised."""
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

    if name == "grep" and "output_mode" not in arguments:
        changed["output_mode"] = DEFAULT_GREP_OUTPUT

    if name == "glob":
        fragment = a_name_fragment(arguments.get("pattern"))
        if fragment:
            changed["pattern"] = f"**/*{fragment}*"

    return arguments if changed == arguments else changed


def _explained_if_empty(result: Any, fragment: str, path: Any) -> Any:
    """`result`, with "No files found" replaced by what that means for a name search."""
    content = getattr(result, "content", None)
    if not isinstance(content, str) or not content.strip().startswith("No files found"):
        return result
    try:
        return result.model_copy(update={"content": nothing_is_named(fragment, path)})
    except Exception:  # noqa: BLE001 - a Command, or some other shape
        return result


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
                    if call.get("name") == "glob":
                        fragment = a_name_fragment(arguments.get("pattern"))
                        if fragment:
                            return _explained_if_empty(
                                handler(request), fragment, arguments.get("path")
                            )
            return handler(request)

    return WorkspacePathMiddleware()


__all__ = [
    "DEFAULT_GREP_OUTPUT",
    "DEFAULT_READ_LINES",
    "a_name_fragment",
    "build_workspace_path_middleware",
    "nothing_is_named",
    "rewrite_tool_arguments",
    "workspace_relative",
]
