"""The workspace an agent sees, without the machinery that runs it.

The sandbox points HOME at `.agent-home` inside the workspace, so npm, pip and
cargo caches land per-run instead of in a directory every run shares. In
container mode that placement is not a choice: only the workspace is mounted,
so anything a command writes has to be inside it.

The cost is that it is also inside everything an agent looks at. Measured on
run-61c5a5b6: 42 tool results across ten stages carried `.agent-home`, every
`ls /` opened with it, and one `npm install` had left 26 cache blobs with
sha512 filenames. `list_repository_files` was taught to skip it; `ls`, `glob`
and `grep` come from the deep-agent filesystem backend and were not.

This wraps that backend so all three agree. It is the agent's *view* that
changes - the directory is still there, still writable, and the sandbox still
uses it - which is the distinction that matters: hiding it from a listing must
not mean a command cannot write to it.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

from deepagents.backends.filesystem import FilesystemBackend

#: Directory names hidden from an agent's view of the workspace. Sourced from
#: the repository tools so the two listings cannot drift apart.
from app.tools.repository import IGNORED_DIRECTORIES



#: Beyond this, a suggestion is a list rather than an answer.
MAX_SUGGESTIONS = 3


def _basename(path: str) -> str:
    return os.path.basename(str(path).rstrip("/")) or str(path)


class _Suggesting:
    """Turn "not found" into "not found, and here is where it is".

    An agent that guesses a path prefix gets an error naming the path it
    invented and nothing else, so it guesses again. Measured across the stored
    runs, the guesses are `/home/user/...`, `/workspace/...`, the project
    directory at the root, and the host path; and the file it wants almost
    always exists. On run-3f8e387d - the run that died of gate exhaustion -
    72 reads failed and 56 of them (77%) named a file that was in the
    workspace under a different path.

    The lookup is by basename, which is the part an agent gets right. It costs
    one directory walk on a path that has already failed, and nothing at all
    on the normal path.
    """

    def _what_is_in_it(self, wanted: str) -> str:
        """The entries of `wanted`, when `wanted` is a directory that exists.

        A model that reads a directory is asking what is in it. Answering "that
        is a directory" is true and is not the answer - measured on
        run-130deeef, where `specialist_backend_3` read
        `/simple-to-do-list-app/tests` four times and was told four times that
        a directory of that name existed there. Listing it costs one `iterdir`
        on a call that has already failed.
        """
        root = getattr(self, "cwd", None)
        if not root:
            return ""
        try:
            target = Path(root) / str(wanted).lstrip("/")
            if not target.is_dir():
                return ""
            entries = sorted(
                (f"{child.name}/" if child.is_dir() else child.name)
                for child in target.iterdir()
                if child.name not in IGNORED_DIRECTORIES
            )
        except Exception:  # noqa: BLE001 - a hint must never fail the call
            return ""
        if not entries:
            return (
                f" '{wanted}' is a directory, and it is empty. Reading a "
                "directory is not possible; read one of the files in it."
            )
        shown = ", ".join(entries[:MAX_DIRECTORY_ENTRIES])
        more = (
            ""
            if len(entries) <= MAX_DIRECTORY_ENTRIES
            else f" and {len(entries) - MAX_DIRECTORY_ENTRIES} more"
        )
        return (
            f" '{wanted}' is a directory, not a file. It contains: {shown}{more}. "
            "Read one of those instead."
        )

    def _where_it_actually_is(self, wanted: str) -> str:
        root = getattr(self, "cwd", None)
        name = _basename(wanted)
        if not root or not name:
            return ""
        # A name with no extension is a directory name, which is what `ls`
        # misses: run-2eb3aa24 asked for `/simple-to-do-list-app` four times.
        want_file = "." in name
        try:
            found = [
                str(candidate.relative_to(root))
                for candidate in Path(root).rglob(name)
                if (candidate.is_file() if want_file else candidate.is_dir())
                and not any(part in IGNORED_DIRECTORIES for part in candidate.parts)
            ]
        except Exception:  # noqa: BLE001 - a hint must never fail the call
            return ""
        if not found:
            return ""
        kind = "a file" if want_file else "a directory"
        shown = ", ".join(f"/{path}" for path in sorted(found)[:MAX_SUGGESTIONS])
        more = "" if len(found) <= MAX_SUGGESTIONS else f" and {len(found) - MAX_SUGGESTIONS} more"
        return (
            f" There is {kind} of that name at {shown}{more}. "
            "Every path is relative to the workspace root, which is '/'."
        )


#: Entries to name when a read lands on a directory. Enough to answer "what is
#: in here", short of reprinting a `node_modules`.
MAX_DIRECTORY_ENTRIES = 30

#: After this many identical reads of unchanged bytes, say so. The second read
#: of a file is ordinary - a model checks its work. The sixth is a loop.
REPEATS_BEFORE_SAYING_SO = 2

#: After this many, stop returning the bytes and say where they already are.
#:
#: The note above is the right first response and it is not always the last
#: one. Measured on run-84e05d4b's `specialist_backend_1`: eleven reads of
#: `/docs/architecture_review.md`, byte-identical, in one stage, each answered
#: with a note saying so and each followed by another. run-44e9fc83 did
#: seventeen of `app.js`.
#:
#: This codebase's escalation everywhere else is hint, note, refuse, and the
#: refusal is safe here for a reason particular to reads: it applies only to a
#: request for *the same bytes* of an *unchanged* file. Any other range still
#: returns content, so a model that has genuinely lost the text has a way back
#: that a loop does not take.
READS_BEFORE_WITHHOLDING = 5


class _NoticingRepeats:
    """Say when a file comes back byte-identical to the last time it was read.

    Measured on run-44e9fc83's `specialist_backend_1`: 39 tool calls, 17 of
    them the same `read_file` of `app.js` at the same range, in runs of six,
    five and four, two to three seconds apart, with no write between them.
    That is 16 model turns spent re-reading 400 lines the model already had.

    Keyed on the CONTENT, not on whether a write happened. A specialist that
    edits a file and reads it back gets different bytes and no note, which is
    the case that makes write-tracking necessary everywhere else; here the
    bytes answer the question directly.

    The content is always returned. A note that withheld it would strand a
    model that had genuinely lost the text - and while compaction is not
    firing on these stages today (it triggers at 70,200 tokens and the largest
    stage of run-1d1b6c9c carried about 22,600), a fix whose failure mode is
    "the agent cannot get its file back" is not worth the tokens it saves.

    The note is delivered in the result the model just asked for, which is
    where correction has been shown to work on this pipeline: the "there is a
    file of that name at ..." hint changed behaviour on the very next call,
    while the same guidance in a brief changed nothing.
    """

    def _file_identity(self, file_path: str) -> str:
        """Size and mtime, which change when the file does.

        Cheap, and unlike a digest of the returned slice it is the same for
        every range of one unchanged file - which is the whole point.
        """
        try:
            stat = self._resolve_path(file_path).stat()
        except Exception:  # noqa: BLE001 - an unreadable stat is not a change
            return ""
        return f"{stat.st_size}:{stat.st_mtime_ns}"

    def _note_if_already_seen(self, path: str, digest: str, first: int, last: int) -> str:
        """Whether this stage has already been served these exact lines.

        Finding 59 caught a byte-identical call. This catches the same waste
        wearing different arguments. Measured on run-6412366b's
        `specialist_ui_ux_0`, reading a 984-line `index.html` that had not
        changed since it was written:

            offset=  0 limit=100   100 new lines
            offset=310 limit= 80    80 new
            offset=320 limit=100    30 new,  70 already read
            offset=320 limit= 50     0 new,  50 already read
            offset=320 limit=100     0 new, 100 already read   <- 20 min later

        Five reads, 220 line-reads of already-seen content against 210 distinct
        lines: more than half the reading was re-reading, and two reads returned
        nothing new at all. On this model a turn costs minutes.

        Keyed on the FILE's identity (size and mtime), never on the returned
        slice. Digesting the slice was the first version and it could never
        work: two different ranges of one unchanged file produce two different
        digests, so the file never looked unchanged and the check never fired -
        on exactly the overlapping reads it was written for. Caught by running
        it against the recorded sequence above.

        A write changes size or mtime, so a specialist that edits and reads
        back is never told anything.
        """
        seen = getattr(self, "_read_spans", None)
        if seen is None:
            seen = {}
            self._read_spans = seen  # noqa: SLF001 - own attribute
        previous_digest, covered = seen.get(path, (None, set()))
        if previous_digest != digest:
            seen[path] = (digest, set(range(first, last + 1)))
            return ""
        wanted = set(range(first, last + 1))
        fresh = wanted - covered
        covered |= wanted
        # Bounded: a file large enough for this to matter is already paged.
        seen[path] = (digest, covered if len(covered) < 100_000 else set())
        if fresh:
            return ""
        return (
            f"\n\n[You have already read lines {first}-{last} of this file in "
            "this stage, and it has not changed since. This returned nothing "
            "you did not already have.]"
        )

    def _the_project_is_called(self, wanted: str) -> str:
        """Name the project directory when an agent guesses at it and misses.

        This run has already committed to one and recorded it; the guess is
        the only part that is missing. Measured across six runs, 53 failed
        listings of a directory that never existed while the marker sat on
        disk the whole time:

            ae4b717e 16   37476645 11   304add54 8
            db3a4a0b  8   2eb3aa24  5   d6369866 5

        run-ae4b717e's ui specialist asked for `task-manager-ui` eleven times
        and `task-manager` - the real one - four. The digest already lists the
        files, and it guessed anyway; what changes this model's behaviour is
        being told at the point of failure, which is where the "there is a file
        of that name at ..." hint corrects a path on the very next call.

        Only for a guess that plausibly meant the project: a bare first segment
        with no extension. `ls /docs/nope` is not this.
        """
        root = getattr(self, "cwd", None)
        if not root:
            return ""
        segments = [part for part in str(wanted).strip("/").split("/") if part]
        if len(segments) != 1 or "." in segments[0]:
            return ""
        try:
            from app.tools.repository import pinned_project_directory

            pinned = pinned_project_directory(Path(root))
        except Exception:  # noqa: BLE001 - a hint must never fail the call
            return ""
        if not pinned or pinned == segments[0]:
            return ""
        return (
            f" This run's project directory is '{pinned}' - that is where the "
            "application lives, and it is recorded in the workspace. Use it "
            "rather than guessing another name."
        )

    def _note_if_repeated(self, file_path: str, text: str) -> str:
        """Whether this stage has already been handed these exact bytes.

        Keyed on what came back and which file it came from, not on the call
        that asked for it. The first version keyed on
        `file_path|args|kwargs`, which makes two requests that return the same
        bytes look unrelated, and the model does not repeat itself that
        tidily.

        Measured on run-f0630b10's `specialist_ui_ux_0`, 54 reads of one
        `index.html`:

        - It alternated between `task-manager/index.html` (36 reads) and
          `/task-manager/index.html` (17). Same file, two keys, two
          independent counts, so each had to reach the threshold on its own.
        - It varied `offset` and `limit` around a file smaller than the
          window, so several different ranges returned byte-identical text
          under different keys. Five consecutive reads returned the same bytes
          and none of them was noticed.

        Across that run: 31 reads returned bytes the stage had already been
        given for an unchanged file, and the old key caught 12 of them.

        Two keys do the work. The file's identity - size and mtime, through
        the resolved path, so spelling cannot split it - decides whether this
        is still the same file, and a write moves it, which is what keeps a
        specialist that edits and reads back from ever being told anything.
        The content digest decides whether these particular bytes are new.

        The threshold is unchanged: one repeat is ordinary, the second is the
        one worth mentioning.
        """
        seen = getattr(self, "_read_digests", None)
        if seen is None:
            seen = {}
            self._read_digests = seen  # noqa: SLF001 - own attribute

        identity = self._file_identity(file_path)
        try:
            where = str(self._resolve_path(file_path))
        except Exception:  # noqa: BLE001 - fall back to what the model typed
            where = file_path
        if not identity:
            # Nothing to tell us whether the file changed, so treat every read
            # as a fresh one rather than risk saying "nothing has changed it"
            # about a file that just did.
            return ""

        digest = hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()
        previous_identity, counts = seen.get(where, (None, {}))
        if previous_identity != identity:
            counts = {}
        count = counts.get(digest, 0)
        counts[digest] = count + 1
        seen[where] = (identity, counts)
        if count >= READS_BEFORE_WITHHOLDING:
            self._withheld = True  # noqa: SLF001 - own attribute, read by `read`
            return (
                f"[This file has given you these same bytes {count} times in "
                "this stage and has not changed once. The content is not "
                "repeated here, because you already have it - scroll back to "
                "any of those results. If you need a part of it you have not "
                "seen, ask for a different line range. Otherwise use what you "
                "have and move on.]"
            )
        if count >= REPEATS_BEFORE_SAYING_SO:
            return (
                f"\n\n[These are the same bytes this file gave you {count} "
                "previous times in this stage, and it has not changed since. "
                "Asking for a different range of it will not help - this is "
                "the whole file. Use what you have and move on.]"
            )
        return ""


def _path_of(entry: Any) -> str:
    """The path an entry names, whatever shape the backend returned it in.

    Entries arrive as dicts (`{"path": ..., "is_dir": ...}`), as objects with a
    `.path`, or as bare strings depending on the call. Matching against the
    string form of the whole entry would work by accident and break on the
    first entry whose other fields happened to contain a directory name.
    """
    if isinstance(entry, dict):
        return str(entry.get("path", ""))
    return str(getattr(entry, "path", entry) or "")


def _is_hidden(entry: Any) -> bool:
    """Whether an entry lies in a directory agents are not shown."""
    parts = [part for part in _path_of(entry).replace("\\", "/").split("/") if part]
    return any(part in IGNORED_DIRECTORIES for part in parts)


class WorkspaceBackend(_Suggesting, _NoticingRepeats, FilesystemBackend):
    """A `FilesystemBackend` that omits the run's own machinery from listings.

    Only the three tools that enumerate are filtered. `read` is deliberately
    untouched: an agent that names a path inside one of these directories has a
    reason, and a read that silently failed would be a worse surprise than a
    listing that is quiet about the cache.
    """

    def read(self, file_path: str, *args: Any, **kwargs: Any) -> Any:
        result = super().read(file_path, *args, **kwargs)
        error = getattr(result, "error", None)
        if error:
            if "not found" not in error:
                return result
            # What is in it, before where else it might be: a model that read
            # a directory asked what is in it, and "there is a directory of
            # that name at the path you gave" answers nothing.
            hint = self._what_is_in_it(file_path) or self._where_it_actually_is(file_path)
            return replace(result, error=error + hint) if hint else result

        # The text lives in `file_data["content"]`, not on the result itself.
        # Reading the wrong attribute made this a silent no-op, which is the
        # quietest kind of broken: every test that asked "did it fail?" passed.
        data = getattr(result, "file_data", None)
        content = data.get("content") if isinstance(data, dict) else None
        if not isinstance(content, str):
            return result
        self._withheld = False  # noqa: SLF001 - own attribute
        note = self._note_if_repeated(file_path, content)
        if self._withheld:
            # The bytes are replaced, not prefixed. Repeating them is the whole
            # cost this is here to stop.
            return replace(result, file_data={**data, "content": note})
        if not note:
            # Same waste, different arguments: a range this stage has already
            # been served of a file that has not changed since.
            first = getattr(result, "start_line", None)
            last = getattr(result, "end_line", None)
            if isinstance(first, int) and isinstance(last, int) and last >= first:
                note = self._note_if_already_seen(
                    str(file_path), self._file_identity(file_path), first, last
                )
        if not note:
            return result
        # Ahead of the content, not after it. A file of any size puts an
        # appended note thousands of characters into the payload, and
        # run-3c0c31d2's `technical_lead` read one 3,847-character
        # `milestone_plan.md` seven times with the notice firing from the
        # second read onward. Being told at the end of what you are reading is
        # not being told: the notice exists to change the *next* call, so it
        # belongs where the model starts.
        return replace(result, file_data={**data, "content": note.strip() + "\n\n" + content})

    def ls(self, path: str) -> Any:
        result = super().ls(path)
        error = getattr(result, "error", None)
        if error and "path_not_found" in error:
            hint = self._where_it_actually_is(path) or self._the_project_is_called(path)
            return replace(result, error=error + hint) if hint else result
        entries = getattr(result, "entries", None)
        if not entries:
            return result
        return replace(result, entries=[e for e in entries if not _is_hidden(e)])

    def glob(self, pattern: str, path: str | None = None) -> Any:
        result = super().glob(pattern, path)
        matches = getattr(result, "matches", None)
        if not matches:
            return result
        return replace(result, matches=[m for m in matches if not _is_hidden(m)])

    def grep(self, *args: Any, **kwargs: Any) -> Any:
        result = super().grep(*args, **kwargs)
        matches = getattr(result, "matches", None)
        if not matches:
            return result
        return replace(result, matches=[m for m in matches if not _is_hidden(m)])


__all__ = ["WorkspaceBackend"]
