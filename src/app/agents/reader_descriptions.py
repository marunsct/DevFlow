"""What the four built-in readers say about themselves to the model (TR.4, LF.1520).

`ls`, `read_file`, `glob` and `grep` come from deepagents, and their descriptions were the library's own, sent in
about 5,600 requests each. Measured against this harness (tool review 2026-11-26), they said things that are not so
here: `read_file` "reads up to 100 lines" (it reads `DEFAULT_READ_LINES`), `grep` "use the execute tool with `rg`"
(no stage has `execute`), `ls` "almost ALWAYS use this tool before using the read_file or edit_file tools" (no stage
has `edit_file`, and every request lists the workspace), and `read_file` "speculatively batch" reads and images
"return multimodal content blocks" (the served model reads none). Their argument schemas said the same: a `limit` of
100 and a `grep` that is literal only and answers with file names by default.

So each says what it does here, in the harness's words, naming no tool a stage is not offered.
"""

from __future__ import annotations

from typing import Any, Literal

from deepagents.middleware.filesystem import GrepSchema, ReadFileSchema
from pydantic import Field

from app.agents.workspace_paths import DEFAULT_GREP_OUTPUT, DEFAULT_READ_LINES

#: The descriptions, by tool name: `FilesystemMiddleware(custom_tool_descriptions=...)`.
DESCRIPTIONS: dict[str, str] = {
    "ls": (
        "Lists what one folder of the workspace holds now: its files and the folders in it. Package caches, build "
        "output and the harness's own short-lived files are left out. Use it for a folder whose contents you need "
        "and your request does not already show."
    ),
    "read_file": (
        "Reads one file of the workspace and returns its lines, each numbered from `offset` + 1.\n\n"
        f"- Without a `limit` it reads the first {DEFAULT_READ_LINES} lines; the result says when lines remain, and "
        "`offset` with `limit` reads on from there.\n"
        "- The numbers are not part of the file: leave them out of any text you write back.\n"
        "- Lines over 5,000 characters are split with continuation markers (5.1, 5.2); `limit` counts the file's "
        "own lines.\n"
        "- An empty file is answered with a warning in place of its text.\n"
        "- When the work needs several files, ask for them in one reply, one call each."
    ),
    "glob": (
        "Finds the workspace's files whose paths match a pattern and returns their paths. `*` matches within one "
        "name, `**` across folders, `?` one character, `[abc]` one of a set and `{a,b}` either. A pattern without "
        "`/` matches a file's name at any depth (`*.md` finds `docs/notes.md`); one with `/` matches the path from "
        "the folder searched. A name starting with a dot matches only a part of the pattern that starts with a dot. "
        "Package caches and build output are left out."
    ),
    "grep": (
        "Searches the workspace's files for a pattern and returns each matching line, numbered, under the file it "
        f"is in (`output_mode` '{DEFAULT_GREP_OUTPUT}' unless you say: 'files_with_matches' gives the file names "
        "alone, 'count' the number of matches per file).\n\n"
        "- The pattern is matched as plain text first. When no line holds it as plain text, a pattern written as a "
        "regular expression (`^## `, `get.*Name`) is matched as one, and the result says which way it matched.\n"
        "- `a|b` finds the lines that hold either.\n"
        "- `path` narrows the search to one folder or file, `glob` to the files whose names match it (`*.md`).\n"
        "- Package caches and build output are not searched."
    ),
}


class ReadArguments(ReadFileSchema):
    """`read_file`'s arguments, with the default the path middleware applies."""

    limit: int = Field(
        default=DEFAULT_READ_LINES,
        description=f"How many lines to read, {DEFAULT_READ_LINES} unless you say; with `offset`, the next window.",
    )


class SearchArguments(GrepSchema):
    """`grep`'s arguments, as the harness's backend and path middleware treat them."""

    pattern: str = Field(
        description="What to search for: plain text, or a regular expression when no line holds it as plain text.",
    )
    output_mode: Literal["files_with_matches", "content", "count"] = Field(
        default=DEFAULT_GREP_OUTPUT,
        description=(
            f"'{DEFAULT_GREP_OUTPUT}' (unless you say): each matching line, numbered, under its file's path. "
            "'files_with_matches': the matching files' paths alone. 'count': the number of matches per file."
        ),
    )


#: The argument schemas replaced, by tool name.
ARGUMENTS: dict[str, type] = {"read_file": ReadArguments, "grep": SearchArguments}


def with_the_harness_s_arguments(tools: list[Any]) -> list[Any]:
    """`tools`, each reader's argument schema replaced by the harness's (`ARGUMENTS`). Never raises."""
    for tool in tools:
        schema = ARGUMENTS.get(getattr(tool, "name", ""))
        if schema is None:
            continue
        try:
            tool.args_schema = schema
        except Exception:  # noqa: BLE001 - the library's schema still works
            pass
    return tools


__all__ = ["ARGUMENTS", "DESCRIPTIONS", "ReadArguments", "SearchArguments", "with_the_harness_s_arguments"]
