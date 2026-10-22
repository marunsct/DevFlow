"""Say when a listing or a search comes back exactly as it did before.

`read_file` has had this since finding 59, and after finding 80 keyed it on the
bytes returned it catches almost everything: on one run only 1 of 50 reads
returned content the stage had already been given. The tools beside it never
had it, and the same waste simply moved there - 4 of 10 `ls` calls and 4 of 12
`grep` calls in that run returned byte-identical results, with
`ls {'path': 'task-manager'}` run five times in one stage.

Those results have nowhere to put a note: `LsResult` carries `entries` and an
`error` and nothing else, and writing into `error` would report a working call
as a failure. The tool boundary does have somewhere - a `ToolMessage` is text -
so the notice lives here rather than in the backend.

Why no write-invalidation, unlike every other repeat notice in this codebase:
these results are self-describing. A listing carries each entry's size and
modification time, and a search carries the matching lines, so anything that
changed what the call reports also changes the bytes it returns. A
byte-identical result therefore *is* the evidence that nothing the agent asked
about has moved, and no separate tracking of writes can tell it better.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from app.agents.workspace_paths import the_same_place

#: One repeat is ordinary; the second is the one worth mentioning. Matches
#: `app.agents.workspace_backend.REPEATS_BEFORE_SAYING_SO`, deliberately: the
#: two notices should not disagree about what counts as circling.
REPEATS_BEFORE_SAYING_SO = 2

#: The words that mark a repeated query's identical, successful answer. Matched
#: by `app.agents.settled_answer`, which withholds a tool asked the same thing
#: past `IDENTICAL_ANSWERS_BEFORE_WITHHOLDING_THE_TOOL` times.
SAME_ANSWER_MARKER = "returned exactly what it returned"

#: Read-only queries with no note of their own. `read_file` is excluded because
#: the backend already gives it a better one, keyed on the file's identity as
#: well as the bytes, and two notices on one result would just be noise.
#:
#: `read_repository_file` is a second, parallel way to read a file and had none
#: of that machinery - no repeat notice, no span tracking, nothing. So a model
#: that used it paid for every re-read in silence, and a model that alternated
#: between the two escaped even `read_file`'s counter. Measured on
#: one run: `specialist_testing_6` read
#: `simple-to-do-list-app/app.test.js` through this tool five times with
#: identical arguments, and `specialist_backend_1` read
#: `docs/architecture_review.md` through it four times while reading the same
#: file through `read_file` eleven more.
#:
#: `inspect_repository` takes no arguments at all and returns a listing, so a
#: repeat of it is always a repeat. One run called it seven times in one
#: stage.
#:
#: `read_command_output` and `changed_since_sprint` were the two read-only
#: tools left out, and a test now fails for the next one. One run's fix stage
#: sent one identical `read_command_output` eight times, answered identically
#: each time with no note, so nothing counted it.
QUERY_TOOLS = frozenset({
    "ls", "grep", "glob", "read_repository_file", "inspect_repository",
    "read_command_output", "changed_since_sprint", "look_up_package", "look_at_page", "read_docs",
    "search_the_web", "read_web_page",
})

#: Mutating tools, watched only for repeated *failures*. A repeated successful
#: write is already answered by `write_artifact`'s "unchanged" status and by the
#: no-op edit refusal; a repeated failing edit had nothing at all.
#:
#: One run died on it: `specialist_backend_2` sent the same failing
#: `edit_artifact` over and over against a five-line file and was stopped as a
#: loop at 1,137 events. The command notices cover `run_terminal_command` and
#: the query notice covers listings and searches; mutations were the member of
#: the set nobody had added, which is the mistake this codebase has made five
#: times now.
MUTATING_TOOLS = frozenset({
    "edit_artifact", "write_artifact", "delete_artifact", "move_artifact",
    "replace_lines",
})


#: How many identical no-op writes to tolerate before refusing one. The write
#: tool already answers the second with "This file already contained exactly
#: this content ... Do not write it again; continue with your response".
#:
#: One run shows what that is worth on its own: `specialist_backend_1`
#: wrote docs/technical_specification.md, was told "unchanged" with that
#: sentence, and wrote it three more times until the run-level guard ended the
#: run at 728 events. One run did the same with final_output.json.
#:
#: A note the model has ignored twice is not a note that needs rewording. The
#: escalation this codebase keeps arriving at is hint, note, rewrite, refuse -
#: and refusing a write that would change nothing costs nothing, because by
#: definition the file already holds exactly that content.
#:
#: This was defined and never read: the refusal borrowed
#: `REPEATS_BEFORE_SAYING_SO` instead, so the two policies could not be tuned
#: apart and the constant documented something that was not happening. Same
#: number today; the point is that changing it now changes the behaviour it
#: describes.
NO_OP_WRITES_BEFORE_REFUSING = 2


#: Argument names that hold a location in the workspace. A tool may spell it
#: any of these ways; the location is the same thing.
_PATH_ARGUMENTS = frozenset({
    "path", "file_path", "relative_path", "filename", "file", "dir",
    "directory", "working_directory", "cwd", "root", "target", "destination",
    "source", "src",
})


def _comparable(args: dict) -> dict:
    """The arguments of a call, with every path spelled one way.

    Applied to both sides of every comparison, so a value it normalises
    differently from some other component cannot cause a false match - only
    two calls that named the same place can collide.
    """
    if not isinstance(args, dict):
        return {}
    return {
        key: (the_same_place(value) if key in _PATH_ARGUMENTS and isinstance(value, str)
              else value)
        for key, value in args.items()
    }


#: `"status": "unchanged"` however the serialiser spaced it. Matching the
#: literal string with one space passed a local test and failed in the
#: container, where the same dict came back without it - the kind of brittleness
#: this codebase has been bitten by before in an "Error"-anywhere match and a
#: ">"-anywhere match.
_UNCHANGED = re.compile(r'"status"\s*:\s*"unchanged"')


def _changed_nothing(content: str) -> bool:
    """Whether a write reported that the file already held this content."""
    return bool(_UNCHANGED.search(content[:400]))


def _looks_like_a_failure(content: str) -> bool:
    """Whether a tool result is reporting an error.

    Two shapes reach here: the filesystem tools return `Error: ...` as text,
    the repository tools return a JSON object with an `error` key.
    """
    head = content.lstrip()[:400]
    return head.startswith("Error:") or '"error"' in head


#: The opening of a refusal, with any quoted path removed so the same refusal
#: about the same file reads the same however the message names it.
_WHY_REFUSED = re.compile(r"""(?:Refusing to \w+|Cannot \w+)[^:]*:\s*([^.]{0,60})""")

#: The repository edit tool's failure, which has no colon in it. Its text is
#: `Could not find that text in '<path>'` followed by the reason, so the whole
#: opening - path included - is the stable shape. A stage that keeps guessing
#: at the passage varies `find` on every retry, and keying the repeat guard on
#: the arguments let all ten of those retries count as ten first attempts.
#: Measured on one run: `specialist_testing_2` sent a different failing
#: `find` for the same file seven times, and `test_round_1` ten times.
_EDIT_NOT_FOUND = re.compile(r"(Could not find that text in '[^']*')")


def _the_same_refusal(content: str) -> str:
    """A stable shape for a refusal, or "" when this is not one.

    The no-op branch below collapses content variation for a write that
    changed nothing, because the event is the same whatever bytes were sent. A
    refusal is the same kind of event and had no such treatment: the guard
    keyed on the arguments, so a stage that rewrote the body each time was
    never counted as repeating itself.

    Measured across every stored transcript, 26 combinations of stage, refusal
    and path were refused three or more times, costing 72 model calls past the
    second. One run's `test_round_0` wrote `docs/technical_specification.md`
    ten times with different content on each attempt - a document the workflow
    renders and no agent may write - and was refused ten times without the
    guard ever seeing a repeat.
    """
    if not _looks_like_a_failure(content):
        return ""
    head = content[:400]
    found = _EDIT_NOT_FOUND.search(head)
    if found:
        return found.group(1)
    found = _WHY_REFUSED.search(head)
    return found.group(1).strip() if found else ""


#: Refusals that are about what a file *is*, not about what was sent to it.
#:
#: The counter keys a refusal on `(tool, path, reason)`, which is right for a
#: refusal about content - "could not find that text" in one file says nothing
#: about another. It is wrong for a refusal about a class of file, because the
#: lesson does not belong to the path.
#:
#: Measured on one run's `test_round_0`: it was refused a write to
#: `docs/technical_specification.md`, then to `docs/milestone_review.md`, then
#: to `docs/technical_specification.md` again - the same refusal, in the same
#: words, three times in one stage - and no notice ever fired, because two of
#: the three were spread across two paths and the third was only the second
#: for its own.
#:
#: Matched on the reason `_the_same_refusal` already extracts, so a wording
#: change shows up here as a refusal that stops grouping rather than as a
#: silent regression - and `test_every_policy_refusal_is_recognised` pins the
#: messages these come from.
_POLICY_REFUSALS = (
    "the workflow writes this file",
    "is a test, and tests are part of what",
    "is not permitted for role",
    "the brief rules that out",
    "it can execute arbitrary code",
    "is your structured response, not an artifact",
    "would create or rewrite a project manifest",
)


def _is_about_the_kind_of_file(reason: str) -> bool:
    """Whether this refusal would read the same about any other path."""
    return any(marker in reason for marker in _POLICY_REFUSALS)


def build_repeated_query_middleware() -> Any:
    """Middleware that tells a stage when a query answered exactly as before."""
    from langchain.agents.middleware import AgentMiddleware

    class RepeatedQueryMiddleware(AgentMiddleware):
        """State lives on the instance, which is built per stage."""

        def __init__(self) -> None:
            super().__init__()
            # Only the fallback for a call outside a graph run. The counting
            # that matters happens in `stage_memory`, because this instance is
            # rebuilt on every approval resume and this dict goes with it.
            # See `app.agents.stage_memory`.
            self._seen: dict[tuple[str, str], dict[str, int]] = {}

        @property
        def _counts(self) -> dict:
            from app.agents.stage_memory import store

            return store("repeated_queries", self._seen)

        def wrap_tool_call(self, request: Any, handler: Any) -> Any:
            result = handler(request)
            try:
                note = self._note_for(request, result)
            except Exception:  # noqa: BLE001 - never fail a tool over a hint
                return result
            if not note:
                return result
            try:
                if _refuses_instead(request, result):
                    return result.model_copy(
                        update={
                            "content": (
                                "{\"error\": \"Refusing this write: the file already "
                                "contains exactly this content, and you have already "
                                "been told that twice. Nothing was written and nothing "
                                "would change if it were. The artifact is saved. Move on to "
                                "the rest of your task, or return your structured "
                                "response.\"}"
                            ),
                            "status": "error",
                        }
                    )
                # Ahead of the result, for the reason in
                # `workspace_backend.read`: a notice after the payload is read
                # last or not at all, and it exists to change the next call.
                return result.model_copy(
                    update={"content": note.strip() + "\n\n" + result.content}
                )
            except Exception:  # noqa: BLE001 - a Command, or some other shape
                return result

        def _note_for(self, request: Any, result: Any) -> str:
            call = getattr(request, "tool_call", None) or {}
            name = call.get("name", "")
            content = getattr(result, "content", None)
            if not isinstance(content, str) or not content:
                return ""
            if name in MUTATING_TOOLS:
                # A repeated failure, or a repeated write that changed nothing.
                # A write that actually changed the file is left alone.
                if not _looks_like_a_failure(content) and not _changed_nothing(content):
                    return ""
            elif name not in QUERY_TOOLS and not name.startswith("mcp_"):
                # Every MCP tool a stage holds is one the owner allowed as a query
                # (`app.tools.mcp_tools`).
                return ""

            args = call.get("args") or {}
            if name in MUTATING_TOOLS and _changed_nothing(content):
                # A write that changed nothing is the same event whatever bytes
                # were sent, so it counts per file - not per (file, content).
                #
                # Keying on the arguments let a single byte reset the counter.
                # Measured on one run, `specialist_backend_0` writing
                # `docs/README.md` ten times: two writes, two "unchanged", two
                # refusals, then one trailing newline removed - and two more
                # "unchanged" before it was refused again. The guard fired
                # twice and the stage still spent ten calls on one file.
                #
                # `_with_one_trailing_newline` is why those 278 and 277 byte
                # bodies are the same file: the tool normalises the ending, so
                # the second really did change nothing.
                # Falling back to the full arguments when there is no path
                # keeps a tool spelled some other way counting as it did
                # before, rather than collapsing every such call into one
                # bucket and refusing an unrelated file's first no-op.
                path = the_same_place(args.get("relative_path") or "")
                key = (
                    (name, path, "changed nothing")
                    if path
                    else (name, repr(sorted(_comparable(args).items())))
                )
                digest = "changed nothing" if path else hashlib.sha1(
                    content.encode("utf-8", "replace")
                ).hexdigest()
            elif (refusal := _the_same_refusal(content)):
                # Same treatment as the no-op write above, for the same
                # reason: the refusal is the event, and the body sent with it
                # is not part of what happened.
                path = the_same_place(args.get("relative_path") or args.get("file_path") or "")
                if _is_about_the_kind_of_file(refusal):
                    # The path is not part of this event: the refusal says
                    # what kind of file it is, and the model has made the same
                    # mistake whichever one it aimed at.
                    path = ""
                key = (name, path, refusal) if path else (name, refusal)
                digest = refusal
            else:
                key = (name, repr(sorted(_comparable(args).items())))
                digest = hashlib.sha1(content.encode("utf-8", "replace")).hexdigest()
            counts = self._counts.setdefault(key, {})
            count = counts.get(digest, 0)
            counts[digest] = count + 1
            threshold = (
                NO_OP_WRITES_BEFORE_REFUSING
                if name in MUTATING_TOOLS and _changed_nothing(content)
                else REPEATS_BEFORE_SAYING_SO
            )
            if count < threshold:
                return ""
            if _looks_like_a_failure(content):
                # The repeated case is usually this one. Measured on
                # one run's `specialist_ui_ux_0`: three identical
                # `ls {'path': 'task-manager'}` in four seconds, every one
                # `path_not_found`. Calling that "returned exactly what it
                # returned" is true and reads as though something came back;
                # what the agent needs to hear is that it failed identically
                # and that repeating it cannot help.
                return (
                    f"\n\n[This `{name}` failed the same way the {count} previous "
                    "times you ran it in this stage, and nothing has changed it "
                    "since. It will fail this way again. Change the arguments, "
                    "create what is missing, or carry on without it.]"
                )
            return (
                f"\n\n[This `{name}` {SAME_ANSWER_MARKER} the {count} "
                "previous times you ran it in this stage. A listing reports each "
                "entry's size and modification time, a search reports the lines it "
                "matched, and a read returns the file's bytes - so an identical "
                "result means nothing you asked about has changed. Running it again "
                "will return this again.]"
            )

    return RepeatedQueryMiddleware()


def _refuses_instead(request: Any, result: Any) -> bool:
    """Whether this repeat has earned a refusal rather than another note."""
    name = (getattr(request, "tool_call", None) or {}).get("name", "")
    content = getattr(result, "content", "") or ""
    return name in MUTATING_TOOLS and _changed_nothing(content)


__all__ = ["QUERY_TOOLS", "REPEATS_BEFORE_SAYING_SO", "SAME_ANSWER_MARKER", "build_repeated_query_middleware"]
