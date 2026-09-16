"""Shared, safe tool wrappers for role agents.

Role agents should never receive raw filesystem or shell access, and they
should never choose their own repository root. This module wraps the narrow
functions in `app.tools.repository` as LangChain tools with the repository
root bound by closure, so a model cannot pass an arbitrary path and explore
directories outside the intended project. Every future role agent should
build its tools from here instead of redefining its own wrappers.
"""

from __future__ import annotations

import json

from typing import Any

from langchain_core.tools import BaseTool, tool

from app.tools.repository import (
    RepositoryToolError,
    delete_approved_artifact,
    move_approved_artifact,
    list_repository_files,
    read_dependency_metadata,
    read_text_file,
    run_approved_validation,
    search_text,
    edit_approved_artifact,
    read_text_lines,
    write_approved_artifact,
)


def build_repository_read_tools(repo_root: str, allow_subdirectories: bool = True) -> list[BaseTool]:
    """Return read-only repository tools bound to a fixed repository root.

    Binding `repo_root` in a closure (instead of accepting it as a tool
    argument) keeps every role agent scoped to one repository even if the
    model tries to request a different root.
    """

    @tool
    def inspect_repository() -> dict[str, Any]:
        """Return repository files, dependency metadata, and workflow-relevant matches.

        Use this to understand project structure and dependencies before
        drafting product or architecture conclusions.
        """
        return {
            "files": list_repository_files(repo_root, allow_subdirectories=allow_subdirectories),
            "dependency_metadata": read_dependency_metadata(repo_root),
            "relevant_matches": search_text(
                repo_root,
                "Product Manager|LangGraph|Deep Agents|workflow|product",
                max_matches=10,
            ),
        }

    @tool
    def read_repository_file(
        relative_path: str, start_line: int = 1, line_count: int | None = None
    ) -> str | dict[str, object]:
        """Read one text file from the repository, whole or in part.

        Args:
            relative_path: path relative to the repository root.
            start_line: 1-based line to start at. Defaults to the first line.
            line_count: how many lines to return. Omit to read to the end.

        Reading part of a file matters for long documents: a specification can
        run to tens of thousands of tokens, and pulling all of it in to change
        one paragraph crowds out everything else. The result says which lines
        came back and whether more follow, so the next slice needs no guessing.

        Returns `{"error": "..."}` instead of raising when the path escapes the
        repository or does not exist, so a wrong guess from the model becomes a
        recoverable tool result instead of crashing the whole agent run.
        """
        try:
            if start_line == 1 and line_count is None:
                return read_text_file(repo_root, relative_path)
            return read_text_lines(
                repo_root, relative_path, start_line=start_line, line_count=line_count
            )
        except RepositoryToolError as exc:
            return {"error": str(exc)}

    return [inspect_repository, read_repository_file]


def build_sprint_history_tool(repo_root: str) -> BaseTool:
    """Return a read-only tool answering "what did the last sprint change?".

    Every stage currently works that out by re-reading the workspace: 257
    `read_file` calls over 22 distinct files on run-61c5a5b6, most of them
    files an earlier sprint had not touched. The accepted-milestone commits
    (see `app.tools.version_control`) already hold the answer.

    Not in `HUMAN_APPROVAL_TOOLS`: it reads history this run wrote itself and
    changes nothing.
    """

    @tool
    def changed_since_sprint(sprint: int) -> dict[str, Any]:
        """List the files changed since the end of a numbered sprint.

        Use this instead of reading the whole project to find out what moved.
        Sprint 1 means "since sprint 1 was accepted", so from sprint 2 you
        would ask for 1.

        Args:
            sprint: the sprint number to compare against, 1 for the first.

        Returns `{"changed": [...]}`, or `{"error": "..."}` when that sprint
        has no recorded state - which is normal in the first sprint of a run.
        """
        from app.tools.version_control import changed_since, is_repository

        if not is_repository(repo_root):
            return {"error": "This workspace has no sprint history to compare against."}
        if sprint < 1:
            return {"error": "Sprint numbers start at 1."}

        changed = changed_since(repo_root, f"sprint-{sprint}")
        if not changed:
            return {
                "changed": [],
                "note": (
                    f"Nothing has changed since sprint {sprint} was accepted, or "
                    f"sprint {sprint} has not been accepted yet."
                ),
            }
        return {"changed": changed, "since": f"sprint-{sprint}"}

    return changed_since_sprint


def _top_level_keys(text: str) -> list[str]:
    """Keys at the outermost level of a JSON object, parsed or not.

    Written as a scan rather than `json.loads` because the case that matters
    most is the one that does not parse. run-9f617c73 wrote a 3,344-byte answer
    that ended `...}] }` - truncated, almost certainly against the output
    ceiling - so `json.loads` raised, the check returned "not the answer", and
    the write went through. A model that ran out of room mid-answer is exactly
    the one about to write it again.

    Depth-aware, so `verification: [{"command": ...}]` does not contribute
    `command`. String-aware, so a brace inside a value does not shift the
    depth.
    """
    keys: list[str] = []
    depth = 0
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char == '"':
            start = index + 1
            index += 1
            while index < length:
                if text[index] == "\\":
                    index += 2
                    continue
                if text[index] == '"':
                    break
                index += 1
            word = text[start:index]
            index += 1
            if depth == 1:
                probe = index
                while probe < length and text[probe] in " \t\r\n":
                    probe += 1
                if probe < length and text[probe] == ":":
                    keys.append(word)
            continue
        if char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
        index += 1
    return keys


def _is_the_stages_own_answer(content: str, answer_fields: frozenset[str]) -> bool:
    """Whether this content is the structured response, saved as a file.

    An agent asked for a structured response and given a write tool sometimes
    does both: it writes the answer to disk and then returns it. The file is
    not a product artifact, nothing reads it, and the stage has usually
    finished its real work by then - so the write is followed by nothing, and
    the repeat guard ends the run.

    Measured on run-2bcdc19b: `defect_fix_2_1` wrote `final_output.json`
    containing `{"changed_files": [], "decisions": [...]}` - its own schema -
    five times in twenty seconds. The second and later writes were answered
    "This file already contained exactly this content ... Do not write it
    again; continue with your response", and it wrote it three more times. The
    prompts say the same thing in words; both lost.

    Matched on the schema's own field names, which is the one signal that
    separates an answer from a data file. Two keys must match and every key
    must be a field, so a `package.json` or a fixture cannot trip it.
    """
    if not answer_fields:
        return False
    text = (content or "").strip()
    if not text.startswith("{"):
        return False
    keys = _top_level_keys(text)
    if len(keys) < 2:
        return False
    return set(keys) <= answer_fields


def build_artifact_write_tool(
    repo_root: str, answer_fields: frozenset[str] = frozenset()
) -> BaseTool:
    """Return the single controlled artifact-write tool bound to a repository root.

    This is the only mutation path role agents get: writes are restricted to
    the repository root and its subfolders by `write_approved_artifact`
    itself, regardless of what path the model requests.

    `answer_fields` are the field names of this stage's response schema, used
    to recognise the stage's own answer being saved as a file - see
    `_is_the_stages_own_answer`.
    """

    @tool
    def write_artifact(relative_path: str, content: str) -> dict[str, str]:
        """Write a generated artifact inside the repository root or its subfolders.

        Returns `{"error": "..."}` instead of raising when the target path
        escapes the repository root, so the model can retry with a valid
        path instead of crashing the whole agent run.
        """
        if _is_the_stages_own_answer(content, answer_fields):
            return {
                "error": (
                    f"Refusing to write '{relative_path}': this content is your "
                    "structured response, not an artifact. It reaches the workflow "
                    "through the response schema, which is the only way it is read - "
                    "a copy on disk is read by nothing and changes nothing. Nothing "
                    "was written. Return your structured response now instead."
                )
            }
        try:
            return write_approved_artifact(repo_root, relative_path, content)
        except RepositoryToolError as exc:
            return {"error": str(exc)}

    return write_artifact


def build_artifact_edit_tool(repo_root: str) -> BaseTool:
    """Return the targeted-edit counterpart to the artifact write tool.

    Without this an agent can only replace whole files, so revising one sentence
    of a long document means regenerating the entire thing in a single tool call.
    On a real run the specification reached 71KB; asked to correct a contradiction
    inside it, the agent produced a shorter second file called
    `technical_specification_v2.md` rather than reproduce the original, and the
    reviewer then read both and reported the differences between them as
    contradictions in the design.

    Gated exactly like `write_artifact`: it changes a file, so it stops at the
    same approval interrupt.
    """

    @tool
    def edit_artifact(relative_path: str, find: str, replace: str) -> dict[str, str]:
        """Replace one exact passage inside a file that already exists.

        Prefer this over `write_artifact` whenever the file is already there:
        it changes only the passage you name and leaves the rest untouched, so
        nothing is lost to a partial rewrite.

        Args:
            relative_path: the file to change, relative to the repository root.
            find: the exact text to replace, including its whitespace. It must
                appear exactly once - include surrounding lines to make it unique.
            replace: the text to put in its place. Pass an empty string to delete
                the passage.

        Returns `{"error": "..."}` instead of raising when the file is missing or
        the passage is absent or ambiguous, so the model can read the section and
        try again rather than crashing the run.
        """
        try:
            return edit_approved_artifact(repo_root, relative_path, find, replace)
        except RepositoryToolError as exc:
            return {"error": str(exc)}

    return edit_artifact


def build_artifact_delete_tool(repo_root: str) -> BaseTool:
    """Return the delete counterpart to the artifact write tool.

    An agent told to leave no scratch files behind, holding only a write tool,
    cleans up the only way it can: by writing another file. See
    `delete_approved_artifact` for what that cost on a real run. Gated exactly
    like `write_artifact` - it changes the workspace, so it stops at the same
    approval interrupt.
    """

    @tool
    def delete_artifact(relative_path: str) -> dict[str, str]:
        """Delete one file inside the workspace.

        Use this to remove a temporary helper you created - a probe script, a
        one-off validator - once it has served its purpose. Never write a
        script whose job is to delete another script: call this instead.

        Args:
            relative_path: the file to delete, relative to the workspace root.

        Returns `{"error": "..."}` instead of raising when the file is missing
        or the path is not allowed, so the model can list the directory and try
        again rather than crashing the run.
        """
        try:
            return delete_approved_artifact(repo_root, relative_path)
        except RepositoryToolError as exc:
            return {"error": str(exc)}

    return delete_artifact


def build_artifact_move_tool(repo_root: str) -> BaseTool:
    """Return the move/rename member of the mutation set.

    Completes the matrix: create, read, change, remove, relocate. Gated exactly
    like `write_artifact` - it changes where a file is, so it stops at the same
    approval interrupt.
    """

    @tool
    def move_artifact(relative_path: str, destination: str) -> dict[str, str]:
        """Move or rename one file inside the workspace.

        Use this instead of rewriting a file at a new path and deleting the old
        one: it keeps the exact bytes, so a long document cannot come back
        subtly different from the version that was already approved.

        Args:
            relative_path: the file to move, relative to the workspace root.
            destination: where it should end up, relative to the workspace root.
                Parent directories are created. It must not already exist.

        Returns `{"error": "..."}` instead of raising when either path is not
        allowed, so the model can list the directory and try again.
        """
        try:
            return move_approved_artifact(repo_root, relative_path, destination)
        except RepositoryToolError as exc:
            return {"error": str(exc)}

    return move_artifact


def build_validation_tool(repo_root: str) -> BaseTool:
    """Return a tool that runs one allowlisted validation command bound to a repo root.

    This is deliberately narrow: `run_approved_validation` already restricts
    the executable to a small allowlist (python, pytest, compileall), so a
    specialist can prove their change works without a general-purpose shell.
    """

    @tool
    def run_validation(
        command: list[str], working_directory: str | None = None
    ) -> dict[str, object]:
        """Run one allowlisted validation command, e.g. ["pytest", "tests/", "-q"].

        Runs in this run's project directory by default, so `["npm", "test"]`
        finds the project's own manifest. Pass `working_directory` (relative to
        the workspace root) only to run somewhere else.

        Returns `{"error": "..."}` instead of raising when the command is not
        on the allowlist, so the specialist can pick an approved command
        instead of crashing the whole agent run.
        """
        try:
            return run_approved_validation(repo_root, command, working_directory)
        except RepositoryToolError as exc:
            return {"error": str(exc)}

    return run_validation


def build_terminal_command_tool(repo_root: str, role_name: str = "general") -> BaseTool:
    """Return a contained command-execution tool bound to one workspace.

    The command is taken as an argv *list*, never a string: there is no shell in
    the execution path, so shell metacharacters carry no meaning and the
    executable can be matched exactly rather than by prefix.
    """

    @tool
    def run_terminal_command(
        command: list[str],
        category: str = "default",
        working_directory: str | None = None,
    ) -> dict[str, Any]:
        """Run one command in the workspace, inside an isolated container.

        Pass the command as a list of arguments, not as a single string:
        `["npm", "install"]`, not `"npm install"`. There is no shell, so `;`,
        `&&`, `|` and `$(...)` will not work - run separate commands instead.

        To run inside a subdirectory, pass `working_directory` - do not try to
        `cd`, which is not a program and cannot be run. For example, to run the
        project's tests from a project directory named `myapp`:
        `command=["npx", "jest"], working_directory="myapp"`.

        Requires human approval before it runs.

        Args:
            command: argv list, e.g. ["npx", "vitest", "run"].
            category: affects the timeout and whether the network is available.
                'install' (300s, network on - use for dependency installs),
                'build' (180s), 'test' (300s), or 'default' (120s). Everything
                except 'install' runs with networking disabled.
            working_directory: path relative to the workspace root to run in.
                Defaults to the workspace root. Must be a directory inside it.
        """
        from app.tools.sandbox import SandboxExecutor

        return SandboxExecutor.execute(
            command=command,
            repo_root=repo_root,
            role_name=role_name,
            category=category,
            working_directory=working_directory,
        )

    return run_terminal_command


JOURNAL_TOOL_MAX_CHARS = 20_000
"""Ceiling on one `read_command_output` result.

The journal exists because 50 KB of output did not fit in the context window.
Handing the whole file back on request would undo that, so a read returns a
bounded window: matching lines when a search term is given, otherwise the tail,
because a build's real error is almost always in the last lines.
"""

JOURNAL_TOOL_MAX_MATCHES = 200


def build_journal_read_tool() -> BaseTool:
    """Return the read-back tool for output an earlier command had truncated.

    Takes no repository root: journalled output lives under `DATA_DIR`, not in
    the workspace, and `app.tools.journal.read_entry` sanitises the reference to
    a single path segment, so there is nothing for a caller to escape.

    Not in `HUMAN_APPROVAL_TOOLS`: this reads back bytes this same agent already
    produced, under a directory it cannot write to by any other means. Gating it
    would pause the run to approve re-reading a log it was just handed a pointer
    to.
    """

    @tool
    def read_command_output(reference: str, search: str = "") -> str | dict[str, str]:
        """Read back the full output of an earlier command that was truncated.

        When a command's output is too large for the conversation it is cut down
        to its head and tail, with a pointer of the form
        `...[N bytes omitted; full output saved as <reference>]...`. Pass that
        `<reference>` here to see what was cut.

        Args:
            reference: the name from the truncation pointer, e.g.
                `1717171717-backend-specialist-pytest-stdout-a1b2c3d4.log`.
            search: optional substring. When given, returns only the matching
                lines, each prefixed with its line number - use this to find an
                error in a long build log. When omitted, returns the tail.

        Returns `{"error": "..."}` when the reference is unknown, so a wrong
        guess is a recoverable tool result rather than a crashed agent run.
        """
        from app.tools.journal import read_entry

        content = read_entry(reference)
        if content is None:
            return {
                "error": (
                    f"No journalled output named '{reference}'. Use the exact reference "
                    "from the truncation pointer; entries are deleted after the "
                    "configured retention window."
                )
            }

        if search:
            matches = [
                f"{number}: {line}"
                for number, line in enumerate(content.splitlines())
                if search in line
            ]
            if not matches:
                return {"error": f"'{search}' does not appear in '{reference}'."}
            clipped = matches[:JOURNAL_TOOL_MAX_MATCHES]
            body = "\n".join(clipped)[:JOURNAL_TOOL_MAX_CHARS]
            if len(matches) > len(clipped):
                body += f"\n\n[{len(matches) - len(clipped)} further matches not shown.]"
            return body

        if len(content) <= JOURNAL_TOOL_MAX_CHARS:
            return content
        return (
            f"[Showing the last {JOURNAL_TOOL_MAX_CHARS:,} characters of "
            f"{len(content):,}. Pass `search` to find an earlier line.]\n\n"
            + content[-JOURNAL_TOOL_MAX_CHARS:]
        )

    return read_command_output


#: Tools that must never run without a human decision.
#:
#: Risk here is about what a call can *do*, not what it is named. Executing a
#: command, installing a dependency or reaching the network can all compromise
#: the host or exfiltrate data; writing a document cannot. The previous
#: configuration gated only ``write_artifact`` and left every execution tool
#: ungated, which is precisely backwards.
HUMAN_APPROVAL_TOOLS = (
    "write_artifact",
    "edit_artifact",
    "delete_artifact",
    "move_artifact",
    "run_terminal_command",
    "run_validation",
)


__all__ = [
    "HUMAN_APPROVAL_TOOLS",
    "build_artifact_delete_tool",
    "build_artifact_move_tool",
    "build_artifact_edit_tool",
    "JOURNAL_TOOL_MAX_CHARS",
    "build_artifact_write_tool",
    "build_journal_read_tool",
    "build_repository_read_tools",
    "build_sprint_history_tool",
    "build_terminal_command_tool",
    "build_validation_tool",
]
