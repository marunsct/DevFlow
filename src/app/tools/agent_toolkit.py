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
import logging
import os
import re

from pathlib import Path
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
    replace_approved_lines,
    write_approved_artifact,
)

logger = logging.getLogger(__name__)


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
    `read_file` calls over 22 distinct files on one run, most of them
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
        from app.tools.version_control import accepted_sprints, changed_since, is_repository

        if not is_repository(repo_root):
            return {"error": "This workspace has no sprint history to compare against."}
        if sprint < 1:
            return {"error": "Sprint numbers start at 1."}
        # Said outright. "Nothing has changed since sprint N, or sprint N has
        # not been accepted yet" let a planning stage that no sprint had been
        # accepted for ask about sprints 1, 2, 3, 4 and 5 in turn, and again.
        accepted = accepted_sprints(repo_root)
        if sprint not in accepted:
            return {
                "changed": [],
                "note": (
                    f"Sprint {sprint} has not been accepted in this run. Accepted so far: "
                    f"{', '.join(map(str, accepted)) or 'none'}. There is nothing to compare against "
                    "for any other sprint number; asking again about another one returns this same answer."
                ),
            }

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
    most is the one that does not parse. One run wrote a 3,344-byte answer
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

    Measured on one run: `defect_fix_2_1` wrote `final_output.json`
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


#: How many of the schema's objections a refusal lists.
MOST_OBJECTIONS_LISTED = 5


def what_the_schema_would_refuse(content: str, schema: Any) -> str:
    """What `schema` would reject in `content`, as one line, or "".

    A stage that saves its answer as a file is told to return it instead - and
    one run's `defect_fix_1_0` wrote `structured_response.json` twice more,
    because the answer it was saving had `exitcode` where the schema has
    `exit_code`. Returned as it was, it would have been refused too; the
    refusal said nothing about that, so the model had no reason to change it.
    A missing field with a near-identical key beside it is named as the likely
    misspelling.
    """
    if schema is None or not hasattr(schema, "model_validate"):
        return ""
    try:
        payload = json.loads(content)
    except ValueError:
        return ""
    try:
        schema.model_validate(payload)
        return ""
    except Exception as error:  # noqa: BLE001 - pydantic's ValidationError, or anything else
        errors = getattr(error, "errors", None)
        if not callable(errors):
            return ""
        import difflib

        lines = []
        for item in errors()[:MOST_OBJECTIONS_LISTED]:
            where = ".".join(str(part) for part in item.get("loc", ()))
            line = f"{where}: {item.get('msg', 'invalid')}"
            given = item.get("input")
            name = str(item.get("loc", ("",))[-1])
            if item.get("type") == "missing" and isinstance(given, dict):
                close = difflib.get_close_matches(name, [str(key) for key in given], n=1, cutoff=0.75)
                if close:
                    line += f" (you wrote `{close[0]}`)"
            lines.append(line)
        return "; ".join(lines)


def build_artifact_write_tool(
    repo_root: str, answer_fields: frozenset[str] = frozenset(), schema: Any = None
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
            objections = what_the_schema_would_refuse(content, schema)
            return {
                "error": (
                    f"Refusing to write '{relative_path}': this content is your "
                    "structured response, not an artifact. It reaches the workflow "
                    "through the response schema, which is the only way it is read - "
                    "a copy on disk is read by nothing and changes nothing. Nothing "
                    "was written. Return your structured response now instead."
                    + (
                        f" As written, the schema would not accept it either - fix "
                        f"these in the response you return: {objections}."
                        if objections
                        else ""
                    )
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


NETWORK_OFF_SENTENCE = "Everything\n                except 'install' runs with networking disabled."
_THE_NETWORK_SENTENCE = re.compile(r"Everything\s+except 'install' runs with networking disabled\.")


def with_the_network_as_it_is(description: str) -> str:
    """The command tool's text with its network sentence true for the sandbox mode in use (Initiative X.3).

    It said every category but 'install' runs with networking disabled. That
    is the per-command container's `--network none`; in container mode the
    command runs in the worker itself and nothing cuts the network, so the
    sentence was false on the deployment that uses that mode.
    """
    try:
        from app.tools.sandbox import IN_CONTAINER_MODE, execution_mode

        here = execution_mode() == IN_CONTAINER_MODE
    except Exception:  # noqa: BLE001 - the text stands as written
        return description
    if not here:
        return description
    # Matched on its words, not on the whitespace between them: Python 3.13
    # strips a docstring's indentation at compile time, so the sentence that
    # matched on 3.12 silently did not (Initiative AO.4).
    return _THE_NETWORK_SENTENCE.sub(
        "Commands run in the harness's own container, which is not cut off from the network; "
        "fetch nothing but dependencies, and those with category 'install'.",
        description,
    )


def line_edits_offered() -> bool:
    """Whether stages are offered `replace_lines`. Off unless `LINE_EDITS=on`.

    Measured across four runs: 51 of 81 `replace_lines` calls failed (62%),
    against 6 of 82 `edit_artifact` (7%) and 7 of 90 `write_artifact` (7%) -
    line numbers go stale after every earlier edit, and a weak model sends
    them anyway. `edit_artifact` and a whole-file write do every job it does.
    """
    import os

    return str(os.environ.get("LINE_EDITS") or "").strip().lower() in ("1", "on", "true", "yes")


def build_line_replace_tool(repo_root: str) -> BaseTool:
    """Return the line-range counterpart to `edit_artifact`.

    `edit_artifact` asks the model to reproduce a passage byte for byte. Swept
    across 45 stored transcripts on 2026-09-19, that requirement produced 247
    of 371 costly tool failures - 67%, eight times the next cause - and 294 of
    the 330 failures were against a file the same stage had already read. The
    model is not editing blind; reproducing bytes from context is simply the
    hard part, and it is a requirement the tool invented rather than one the
    task has.

    A line range removes it. `read_file` numbers every line it returns, so the
    model can read the range off output it already has, and there is nothing
    to quote, escape or indent. It also works identically in every language,
    which no text-matching repair can claim.
    """

    @tool
    def replace_lines(
        relative_path: str,
        start_line: int,
        end_line: int,
        content: str,
        expect_start: str = "",
        expect_end: str = "",
    ) -> dict[str, str]:
        """Replace a numbered range of lines in a file that already exists.

        Prefer this over `edit_artifact` whenever you have just read the file:
        the read shows you line numbers, and naming them needs no quoting. Use
        `edit_artifact` when you know the exact text but not where it is.

        Args:
            relative_path: the file to change, relative to the workspace root.
            start_line: first line to replace, counting from 1, inclusive.
            end_line: last line to replace, inclusive. Pass the same number as
                `start_line` to replace a single line.
            content: the replacement text. Pass an empty string to delete the
                range. Do not include line numbers.
            expect_start: optional. The first line as you read it. Given, the
                edit is refused if that line has moved, so a stale line number
                cannot silently change the wrong place. Whitespace is ignored.
            expect_end: optional, and worth sending every time you send
                `expect_start`. The LAST line of the range as you read it. With
                both ends given, an edit whose numbering has drifted is applied
                at the range's new position instead of being refused - the two
                lines identify the range without depending on where it sits.
                With only `expect_start`, a drifted edit is still refused,
                because one line cannot say where the range now ends.

        Returns `{"error": "..."}` instead of raising when the range is outside
        the file or the file is missing, so a wrong guess is a recoverable tool
        result rather than a crashed run.
        """
        try:
            return replace_approved_lines(
                repo_root, relative_path, start_line, end_line, content,
                expect_start, expect_end,
            )
        except RepositoryToolError as exc:
            return {"error": str(exc)}

    return replace_lines


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
        """Run one allowlisted validation command, e.g. ["npm", "test"].

        Examples that work in this image: `["npm", "test"]`,
        `["node", "--test"]`, `["npx", "vitest", "run"]`. A Python project
        needs `["pip", "install", "pytest"]` with category "install" first -
        `pytest` is allowed but is not installed.

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

        Code passed on the command line (`python -c`, `node -e`, `node -p`)
        is saved as a `tmp-inline-` file in the project and run from there, so
        what ran is readable afterwards; the harness removes the file before
        the next test round.

        A command that runs until something stops it - a dev server, a
        watcher, `serve` - has nothing here to stop it and will sit until the
        timeout. To serve a page for a browser test, let Playwright start it:
        `webServer: { command: "...", url: "..." }` in `playwright.config.ts`.

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

        command, working_directory, moved = _a_cd_taken_as_the_working_directory(command, working_directory)
        command, saved = _code_on_the_command_line_as_a_file(command, repo_root, working_directory, role_name)
        moved = " ".join(part for part in (moved, saved) if part)
        held_back = _a_look_with_the_looking_tools_withheld(command, repo_root, working_directory)
        if held_back:
            return {"error": held_back}
        result = SandboxExecutor.execute(
            command=command,
            repo_root=repo_root,
            role_name=role_name,
            category=category,
            working_directory=working_directory,
        )
        if moved and isinstance(result, dict):
            result = {**result, "note": moved}
        return result

    run_terminal_command.description = with_the_network_as_it_is(run_terminal_command.description)
    return run_terminal_command


#: Interpreters whose code on the command line is saved to a file and run from it,
#: by the flags that take the code: (extension, whether it prints the value).
_CODE_FLAGS: dict[str, dict[str, tuple[str, bool]]] = {
    "python": {"-c": (".py", False)},
    "node": {"-e": (".cjs", False), "--eval": (".cjs", False), "-p": (".cjs", True), "--print": (".cjs", True)},
}


def _the_interpreter(program: str) -> str:
    name = os.path.basename(program)
    if re.fullmatch(r"python(?:3(?:\.\d+)?)?", name):
        return "python"
    return name


def _code_on_the_command_line_as_a_file(
    command: Any, repo_root: str, working_directory: str | None, author: str = ""
) -> tuple[Any, str]:
    """`python -c CODE` / `node -e CODE` as the same interpreter run on a `tmp-` file holding CODE; else unchanged and "".

    The owner's decision, 2026-10-20: code on the command line was refused ("Put
    the code in a file ... named `tmp-<what it checks>`") - 10 refusals on one
    run, 35 on another, each a model call, and the advice was rarely followed.
    The file is saved where the advice said, in the project, so what ran can
    be read afterwards; a `tmp-` name is swept before the next test round and
    at release (`file_kinds.is_scratch`). The sweep removes only a file the
    project memory says a stage of this run wrote, so the file is recorded as
    the calling stage's: measured on one gate run, seven of them, never
    recorded, sat in the product.
    """
    import hashlib

    if not isinstance(command, list) or len(command) < 3:
        return command, ""
    flags = _CODE_FLAGS.get(_the_interpreter(str(command[0])))
    if not flags:
        return command, ""
    at = next((i for i, part in enumerate(command[1:], 1) if str(part) in flags), None)
    if at is None or at + 1 >= len(command):
        return command, ""
    extension, prints = flags[str(command[at])]
    code = str(command[at + 1])
    if prints:
        code = f"console.log(eval({json.dumps(code)}));"
    try:
        from app.tools.repository import pinned_project_directory

        root = Path(repo_root)
        here = root / str(working_directory or "").strip().strip("/")
        project = pinned_project_directory(root) if not working_directory else None
        folder = (root / project) if project and (root / project).is_dir() else here
        name = f"tmp-inline-{hashlib.sha1(code.encode()).hexdigest()[:8]}{extension}"
        target = folder / name
        target.write_text(code.rstrip("\n") + "\n", encoding="utf-8")
        shown = os.path.relpath(target, here).replace(os.sep, "/")
    except Exception:  # noqa: BLE001 - the command goes on as it was, and is refused as before
        logger.debug("Could not save code from the command line", exc_info=True)
        return command, ""
    rewritten = [str(part) for part in command[:at]] + [shown] + [str(part) for part in command[at + 2:]]
    recorded = os.path.relpath(target, root).replace(os.sep, "/")
    try:
        from app.analysis import project_memory
        from app.observability.transcript import _stage_from_config

        project_memory.record(root, recorded, _stage_from_config(author or "run_terminal_command"))
    except Exception:  # noqa: BLE001 - bookkeeping must never fail the command
        pass
    return rewritten, (
        f"Ran the code you passed on the command line from `{recorded}`, saved there so what ran can be "
        "read afterwards; a `tmp-` file is removed before the next test round and at release."
    )


#: Shell operators a `cd` may be followed by before its command.
_AFTER_A_CD = frozenset({"&&", ";"})


def _a_cd_taken_as_the_working_directory(command: Any, working_directory: str | None) -> tuple[Any, str | None, str]:
    """`["cd", folder, *command]` as `command` run in `folder`; else the call unchanged and "".

    Measured live: `["cd", "task-management-dashboard", ".venv/bin/python", "-m",
    "pip", "list"]` was refused three times in one run and five in another
    ("`cd` is not a program. Pass `working_directory`") - each a model call to
    say what the argv already said. The folder is resolved, and confined, by
    the sandbox exactly as a `working_directory` is.
    """
    if not isinstance(command, list) or len(command) < 3 or os.path.basename(str(command[0])) != "cd":
        return command, working_directory, ""
    folder, rest = str(command[1]), [str(part) for part in command[2:]]
    if rest and rest[0] in _AFTER_A_CD:
        rest = rest[1:]
    if not rest or not folder.strip() or folder.startswith("-"):
        return command, working_directory, ""
    base = str(working_directory or "").strip().strip("/")
    joined = os.path.normpath(os.path.join(base, folder)) if base else os.path.normpath(folder)
    moved = (
        f"Ran `{' '.join(rest)}` in `{joined}`: `cd` is not a program here, so the folder was taken as "
        f"`working_directory`, which is how to run a command elsewhere."
    )
    return rest, joined, moved


#: Programs that only show what is in the workspace: what `read_file` and
#: `ls` do, by another door.
_PROGRAMS_THAT_ONLY_LOOK = frozenset({"cat", "head", "tail", "less", "more", "nl", "ls", "tree", "find", "stat"})

#: Of those, the ones that show a file's lines rather than its name.
_PROGRAMS_THAT_SHOW_LINES = frozenset({"cat", "head", "tail", "less", "more", "nl"})

#: Entries under one folder looked at before it is taken as more than the memory shows.
_MOST_ENTRIES_CHECKED = 2_000


def _what_it_looks_at(argv: list[str], repo_root: str, working_directory: str | None) -> list[Path] | None:
    """The workspace paths `argv` names that are there; None when one lies outside the workspace."""
    root = Path(repo_root).resolve()
    here = (root / str(working_directory or "").strip().lstrip("/")).resolve()
    found: list[Path] = []
    for word in argv[1:]:
        word = str(word)
        if not word or word.startswith("-"):
            continue
        path = (here / word).resolve()
        if not path.exists():
            # A flag's value (`-n 20`, `-type f`) or a path that is not there:
            # the command says which itself.
            continue
        if path != root and root not in path.parents:
            return None
        found.append(path)
    if not found and not any(str(w) and not str(w).startswith("-") for w in argv[1:]):
        found.append(here)
    return found


def _the_memory_shows(path: Path, root: Path, held: dict[str, str], shows_lines: bool) -> bool:
    """Whether the stage already has what a look at `path` gives back.

    A file's lines: this stage has seen the file as it is now - the memory held
    it whole, or the stage read or wrote it. A name, or a folder's listing:
    every file under it is a text file the memory names, held or listed as left
    out. An installed or built folder, a database or anything else the memory
    never names is new to the stage, and the look runs.
    """
    from app.tools.seen_content import has_seen_this_version

    relative = path.relative_to(root).as_posix()
    if path.is_file():
        if relative not in held:
            return False
        return has_seen_this_version(relative, held[relative]) if shows_lines else True
    if shows_lines or not path.is_dir():
        return False
    from app.agents.project_memory import _ignored

    looked_at = 0
    files_seen = 0
    for folder, directories, files in os.walk(path):
        folder_path = Path(folder)
        if folder_path != root and _ignored(folder_path.relative_to(root).parts):
            return False
        for name in files:
            looked_at += 1
            files_seen += 1
            if looked_at > _MOST_ENTRIES_CHECKED or (folder_path / name).relative_to(root).as_posix() not in held:
                return False
        looked_at += len(directories)
        if looked_at > _MOST_ENTRIES_CHECKED:
            return False
    # An empty folder's listing costs nothing and settles the question: measured
    # live, refusing `ls -la tests/` on one sent the same command four times.
    return files_seen > 0


def _a_look_with_the_looking_tools_withheld(command: Any, repo_root: str = "", working_directory: str | None = None) -> str:
    """The refusal for a command that only looks, once this stage's reading is withheld; else "".

    Measured live: a fixer had its read tools withheld for re-reading files it
    held, then read the same files with `cat` and listed the same folders with
    `ls` through this tool - about ten calls in two minutes - until its budget
    ran out with nothing written.

    Refused only when everything it looks at is already the stage's: measured
    on a later run, 49 of 70 refusals were of looks at what the memory never
    shows - an installed `.venv`, a built `dist`, a folder holding a database -
    and each was told the look only showed what it already had.
    """
    argv = command if isinstance(command, list) else str(command or "").split()
    if not argv:
        return ""
    program = os.path.basename(str(argv[0]))
    if program not in _PROGRAMS_THAT_ONLY_LOOK:
        return ""
    from app.agents.settled_answer import the_read_tool_is_withheld

    if not the_read_tool_is_withheld():
        return ""
    if repo_root:
        try:
            from app.agents import project_memory

            looked_at = _what_it_looks_at([str(word) for word in argv], repo_root, working_directory)
            if not looked_at:
                return ""
            root = Path(repo_root).resolve()
            held = project_memory.current(root)
            shows_lines = program in _PROGRAMS_THAT_SHOW_LINES
            if not all(_the_memory_shows(path, root, held, shows_lines) for path in looked_at):
                return ""
        except Exception:  # noqa: BLE001 - the look runs, as it would have
            logger.debug("Could not tell what a look shows", exc_info=True)
            return ""
    return (
        f"Not running `{program}`: reading is done for this stage, and this command only shows "
        "what the project memory and your earlier reads already gave you. Make the change with "
        "the tools that write, then return your structured response saying what you changed."
    )


JOURNAL_TOOL_MAX_CHARS = 20_000
"""Ceiling on one `read_command_output` result.

The journal exists because 50 KB of output did not fit in the context window.
Handing the whole file back on request would undo that, so a read returns a
bounded window: matching lines when a search term is given, otherwise the tail,
because a build's real error is almost always in the last lines.
"""

JOURNAL_TOOL_MAX_MATCHES = 200


#: A reference the journal could have produced: a name ending in the eight
#: random characters `journal` appends. Anything else was constructed or is a
#: path, and neither can ever be found.
_A_JOURNAL_REFERENCE = re.compile(r"-[0-9a-f]{8}\.[A-Za-z0-9]{1,6}$")


#: A filename inside a longer string: a stem, a dot, a short extension. The
#: reference is not always just a path - it is often a path the harness printed
#: with something after it.
_A_FILENAME_IN_IT = re.compile(r"[\w./-]*[\w-]\.[A-Za-z0-9]{1,6}\b")


def _the_files_a_reference_names(candidate: str) -> list[str]:
    """Every filename the reference mentions, longest first.

    A bare `os.path.basename` was not enough. The commonest failing reference is
    the harness's own workspace listing copied verbatim - `task-manager/app.js
    (188 lines)`, whose basename is `(188` - and the next commonest is a
    description like `app.spec.js lines 315-340`, whose basename is `315-340`.
    Across the stored runs those two shapes are 21 of the 56 references that did
    not resolve.
    """
    found = _A_FILENAME_IN_IT.findall(candidate or "")
    return sorted({os.path.basename(name) for name in found if name}, key=len, reverse=True)


def _somewhere_in_the_workspace(repo_root: str | None, candidate: str) -> str:
    """Where a named file is in the workspace, or "". Never raises.

    A reference that is really a path is usually missing its directory, which is
    why naming the whole path is worth more than naming the tool.
    """
    if not repo_root:
        return ""
    for wanted in _the_files_a_reference_names(candidate) or [
        os.path.basename(candidate.strip("/"))
    ]:
        found = _the_first_file_named(repo_root, wanted)
        if found:
            return found
    return ""


def _the_first_file_named(repo_root: str, wanted: str) -> str:
    """The first path in the workspace whose basename is `wanted`, or ""."""
    if not wanted:
        return ""
    try:
        root = os.path.abspath(str(repo_root))
        for directory, subdirectories, files in os.walk(root):
            subdirectories[:] = [
                name for name in subdirectories
                if not name.startswith(".") and name != "node_modules"
            ]
            if wanted in files:
                return os.path.relpath(os.path.join(directory, wanted), root)
    except Exception:  # noqa: BLE001 - a hint must not decide a tool result
        return ""
    return ""



def _and_a_path_is_read_with_read_file(
    reference: str, repo_root: str | None = None, search: str = ""
) -> str:
    """The sentence for a reference that is really a workspace path, or "".

    6 of the 28 failed calls across the current generation of runs passed a path
    - `todo-app/app.js`, `todo-app/index.html` - which is this tool being
    mistaken for `read_file`. The refusal explained the journal at a stage that
    was not asking about the journal.

    Says whether the file is there, and where, rather than only naming the tool.
    Measured live on one run, whose `test_round_0` asked 16 times for

        todo-toggling-checkbox-app-da256-kethrough-and-checked-state/error-context.md

    a Playwright per-case artefact. It was told to use `read_file` every time,
    and `read_file` would have failed too: Playwright had already cleared the
    directory, and no `error-context.md` exists anywhere in that workspace.
    Suggesting a tool that cannot work is one more round trip, which is what this
    message was added to stop.
    """
    candidate = str(reference or "")
    if not candidate or _A_JOURNAL_REFERENCE.search(candidate):
        return ""
    if "/" not in candidate and "." not in candidate:
        return ""
    if not repo_root:
        # Nothing to look in, so neither of the sentences below can be said
        # honestly - "there is no file of that name anywhere in the workspace"
        # would be a claim about a workspace this never saw. Caught by the deploy
        # check, which calls this with no root.
        return (
            f" '{candidate}' looks like a path rather than a journal reference: a "
            "reference ends in eight random characters. To read a file in the "
            "workspace, use `read_file`."
        )
    where = _somewhere_in_the_workspace(repo_root, candidate)
    if where and str(search or "").strip():
        # The stage was searching, not reading. Told to `read_file`, one run's
        # `specialist_backend_0` sent the identical call again - a file path as
        # the reference and `search: "toggle-btn"` - because reading the whole
        # file was not what it wanted. The call that does what it wanted is
        # `grep`, with both of the values it already gave.
        return (
            f" '{candidate}' looks like a path rather than a journal reference: a "
            f"reference ends in eight random characters. That file is in the "
            f"workspace at '{where}'. To search it, call `grep` with pattern "
            f"{json.dumps(str(search).strip())} and path '{where}'."
        )
    if where:
        # One run's `defect_fix_2_2` had its read tool withheld for re-reading
        # files it already held, then asked this tool for `app.js (425 lines)`
        # and `index.html (276 lines)` - copied from the workspace listing -
        # and was told to read them with the tool it no longer had.
        from app.agents.settled_answer import the_read_tool_is_withheld

        if the_read_tool_is_withheld():
            return (
                f" '{candidate}' looks like a path rather than a journal reference: "
                f"a reference ends in eight random characters. That file is in the "
                f"workspace at '{where}', and its content is already in this "
                "conversation from your earlier reads - that is why `read_file` was "
                "withdrawn. Work from what you have; after you change the file, the "
                "tool's result shows what it now holds."
            )
        return (
            f" '{candidate}' looks like a path rather than a journal reference: a "
            f"reference ends in eight random characters. That file is in the "
            f"workspace at '{where}' - read it with `read_file`."
        )
    return (
        f" '{candidate}' looks like a path rather than a journal reference: a "
        "reference ends in eight random characters - and there is no file of that "
        "name anywhere in the workspace either, so no tool can read it. If a "
        "command wrote it and then removed it, it is gone; run the command again "
        "if you need it."
    )


#: Failed lookups of one reference before the note says so, and before the
#: refusal. The same two rungs `run_terminal_command` and `read_file` use: one
#: miss is ordinary, the second is worth mentioning, the third is not worth
#: paying for.
_MISSES_BEFORE_SAYING_SO = 2
_MISSES_BEFORE_REFUSING = 3

#: Per-instance fallback, for a lookup outside a graph run.
_MISSES_OUTSIDE_A_RUN: dict[str, int] = {}


def _missed_before(reference: str) -> bool:
    """Whether this stage has already asked for this reference and missed."""
    try:
        from app.agents.stage_memory import store

        return bool(store("missing_journal_references", _MISSES_OUTSIDE_A_RUN).get(reference))
    except Exception:  # noqa: BLE001 - treat as a first ask
        return False


def _count_a_missing_reference(reference: str) -> int:
    """How many times this exact reference has now failed for this stage.

    Kept in `stage_memory`, like the repeated-read tally: the toolkit is rebuilt
    with the agent on every approval resume, and a counter on the closure would
    start again from zero each time.

    Every other tool that can fail the same way twice says so - measured across
    the current generation of runs, results that mention a repeat number 132 for
    `read_file`, 93 for `edit_artifact`, 90 for `run_terminal_command`, 36 for
    `write_artifact`, and 0 for this one. It was the only tool with no rung at
    all, and the second-biggest waster: 19 repeated identical failures, with
    single stages sending one invented reference 8, 6 and 5 times.
    """
    from app.agents.stage_memory import store

    seen = store("missing_journal_references", _MISSES_OUTSIDE_A_RUN)
    seen[reference] = seen.get(reference, 0) + 1
    return seen[reference]


def _and_you_have_asked_for_this_before(reference: str, misses: int) -> str:
    """The repeat note for a reference that has already failed, or "".

    A reference that did not resolve cannot start resolving: entries are created
    under fresh random names, so no later command can produce the name that was
    guessed. That is what makes refusing safe here rather than merely cheaper.
    """
    if misses < _MISSES_BEFORE_SAYING_SO:
        return ""
    return (
        f" You have asked for '{reference}' {misses} times now and it has not "
        "existed any of them. A reference that does not resolve never will: "
        "entries are created under fresh random names, so nothing you run later "
        "can produce this one."
    )


def _refuse_a_reference_already_missed(reference: str, misses: int) -> str:
    """The refusal once the note has been ignored, or "".

    Says what to do instead rather than only that it will not look again, which
    is what every other refusal in this harness does.
    """
    if misses < _MISSES_BEFORE_REFUSING:
        return ""
    return (
        f"Not looking for '{reference}' again: it has failed {misses} times in "
        "this stage and a reference that does not resolve never will, because "
        "entries are created under fresh random names. If you want a file in the "
        "workspace, use `read_file`. If you want a command's full output, run the "
        "command and use the reference from the truncation pointer it gives you. "
        "If you have what you need, return your structured response."
    )


def _this_run_s_entries(repo_root: str | None) -> list[str]:
    """This run's journal entries, newest first, or [] on any failure."""
    try:
        from app.tools.journal import list_entries, scope_of

        return list(list_entries(scope=scope_of(repo_root)))
    except Exception:  # noqa: BLE001 - the plain miss message still applies
        return []


def _the_one_entry_it_meant(reference: str, entries: list[str]) -> str:
    """The one entry of this run whose name ends with `reference`, or "".

    An entry is named `<timestamp>-<run>-<role>-<program>-<stream>-<random>.log`,
    and a model copying one back drops the leading timestamp. One run's
    `specialist_testing_3` asked for
    `run-<id>-ui_ux_specialist-node-stderr-<random>.log` six times; the
    reply listed the one entry, `<timestamp>-run-<id>-...-<random>.log`, and
    from the third ask said "a reference that does not resolve never will" -
    about a name one prefix away from the answer.

    Only a suffix long enough to carry the random tail, and only when exactly one
    of this run's entries has it, so this never picks between two logs.

    The `.log` ending may be dropped too: one run's QA asked twice for
    `<timestamp>-run-<id>-...-<random>` - the whole name but its extension - and
    was refused both times.
    """
    wanted = str(reference or "").strip()
    if len(wanted) < 12:
        return ""
    found = [
        name
        for name in entries or ()
        if name != wanted and (name.endswith(wanted) or name.removesuffix(".log").endswith(wanted))
    ]
    return found[0] if len(found) == 1 else ""


def build_journal_read_tool(repo_root: str | None = None) -> BaseTool:
    """Return the read-back tool for output an earlier command had truncated.

    `repo_root` is used for one thing: naming which run's entries to suggest when
    a reference is not found. Reads still resolve exactly as before -
    `app.tools.journal.read_entry` sanitises the reference to a single path
    segment under `DATA_DIR`, so there is nothing for a caller to escape, and
    passing a root does not widen that.

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

        This is not a way to read a file. A path in the workspace is read with
        `read_file`; this reads only output a command produced and this
        conversation had to cut.

        Args:
            reference: the name copied from a truncation pointer you were
                actually shown. It ends in eight random characters, so there is
                no way to write one from the command that produced it - if you
                have no pointer, there is nothing here to read. Do not construct
                a reference, and do not pass a file path.
            search: optional substring. When given, returns only the matching
                lines, each prefixed with its line number - use this to find an
                error in a long build log. When omitted, returns the tail.

        Returns `{"error": "..."}` when the reference is unknown, so a wrong
        guess is a recoverable tool result rather than a crashed agent run.
        """
        from app.tools.journal import read_entry

        content = read_entry(reference)
        listed_once: list[str] | None = None
        if content is None and not _missed_before(str(reference)):
            # Only on the first miss: a unique suffix match either resolves now
            # or never will, and a refused reference must stop costing lookups.
            # The list is kept for the "these are this run's outputs" answer
            # below, so a first miss still costs one lookup, not two.
            listed_once = _this_run_s_entries(repo_root)
            resolved = _the_one_entry_it_meant(str(reference), listed_once)
            if resolved:
                reference, content = resolved, read_entry(resolved)
        if content is None:
            # Counted before the message is built, so the note and the refusal
            # both read from one tally.
            misses = _count_a_missing_reference(str(reference))
            refusal = _refuse_a_reference_already_missed(str(reference), misses)
            if refusal:
                return {"error": refusal}
            repeated = _and_you_have_asked_for_this_before(str(reference), misses)
            # What the refusal used to be: "use the exact reference from the
            # truncation pointer". A reference ends in eight random hex
            # characters, so an agent that no longer has the pointer cannot
            # construct one however well it remembers the command - and it tries.
            # Measured on one run: eight failed calls on invented names like
            # `5-backend-specialist-pytest-stdout-a1b2c3d4.log`, with seven of
            # them identical repeats. Naming what exists turns a dead end into one
            # more call.
            #
            # That fix left the cause in place. The `Args:` description above
            # carried a complete, copyable example reference, and across the
            # current generation of runs that exact string was the single
            # most-passed value: 9 of 28 failures, from stages that had never
            # been shown a pointer. A worked example of an identifier that cannot
            # be constructed is an invitation to construct one, so the
            # description now gives the shape and says not to. Another 6 of the
            # 28 passed a workspace path, which both refusals now redirect.
            #
            # Scoped to this run. The journal is one shared directory kept for
            # three days and the worker runs two runs at once, so an unscoped list
            # would offer another run's build log - and reading another run's
            # passing tests as your own is worse than the error it replaced.
            from app.tools.journal import list_entries, scope_of

            redirect = _and_a_path_is_read_with_read_file(reference, repo_root, search)
            if redirect and repo_root and _somewhere_in_the_workspace(repo_root, str(reference)):
                # A file of the workspace: the stage meant the file, and the list
                # of saved outputs in front of the one sentence that helps was
                # noise. Measured live: a fixer searching a source file was given
                # thirty log names first and the `grep` it needed last, and did
                # not use it.
                return {"error": f"No journalled output named '{reference}'.{redirect}{repeated}"}
            available = (
                listed_once if listed_once is not None else list_entries(scope=scope_of(repo_root))
            )
            if available:
                listed = "\n".join(f"  {name}" for name in available)
                return {
                    "error": (
                        f"No journalled output named '{reference}'. These are this "
                        f"run's journalled outputs, newest first:\n{listed}\n\n"
                        "Pass one of those names exactly. The reference ends in "
                        "eight random characters and cannot be guessed from the "
                        "command that produced it."
                        + _and_a_path_is_read_with_read_file(reference, repo_root, search)
                        + repeated
                    )
                }
            return {
                "error": (
                    f"No journalled output named '{reference}', and this run has "
                    "nothing journalled: output is only saved when it was too "
                    "large for the conversation, and a command whose output fitted "
                    "has nothing more to read. Entries are also deleted after the "
                    "configured retention window."
                    + _and_a_path_is_read_with_read_file(reference, repo_root, search)
                    + repeated
                )
            }

        if search:
            lines = content.splitlines()
            matches = [
                f"{number}: {line}" for number, line in enumerate(lines) if search in line
            ]
            alternatives = _the_alternatives_meant(search) if not matches else []
            if alternatives:
                matches = [
                    f"{number}: {line}"
                    for number, line in enumerate(lines)
                    if any(each in line for each in alternatives)
                ]
            if not matches:
                return _nothing_matched(search, reference, len(lines), alternatives)
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


def _the_alternatives_meant(search: str) -> list[str]:
    """`a|b|c` as the alternatives a regex would mean, or [] when it is not one.

    `search` is a literal substring. A model checking a passing test log sent
    `not ok|Error|FAIL|AssertionError|...` and found nothing, which here only
    ever meant the literal string was absent. Asked after the literal search
    missed, so text that really contains `|` still matches itself first; and
    never for `||`, which is code, not alternation. The same reading `grep`
    gets in `app.agents.workspace_backend`.
    """
    if "|" not in search or "||" in search:
        return []
    parts = [part.strip() for part in search.split("|") if part.strip()]
    return parts if len(parts) >= 2 else []


def _nothing_matched(search: str, reference: str, searched: int, alternatives: list[str]) -> str:
    """A search that found nothing, reported as the answer it is.

    It was `{"error": ...}`. A test round searched a passing log for its
    failure markers, got an error back, and spent another call searching for
    `not ok` alone to be sure: the absence it was looking for had been
    reported as the tool failing.
    """
    what = (
        f"none of {', '.join(repr(a) for a in alternatives)}"
        if alternatives
        else f"'{search}'"
    )
    return (
        f"No line of '{reference}' contains {what}. All {searched:,} lines were "
        "searched, so that is the answer: the output does not contain it."
    )


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
    "replace_lines",
    "delete_artifact",
    "move_artifact",
    "run_terminal_command",
    "run_validation",
)


__all__ = [
    "HUMAN_APPROVAL_TOOLS",
    "line_edits_offered",
    "build_artifact_delete_tool",
    "build_artifact_move_tool",
    "build_artifact_edit_tool",
    "build_line_replace_tool",
    "JOURNAL_TOOL_MAX_CHARS",
    "build_artifact_write_tool",
    "build_journal_read_tool",
    "build_repository_read_tools",
    "build_sprint_history_tool",
    "build_terminal_command_tool",
    "build_validation_tool",
]
