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
from app.agents.workspace_paths import the_same_place
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

    def _where_this_stage_moved_it(self, wanted: str) -> str:
        """The exact new name, when this stage renamed the file itself.

        `_where_it_actually_is` searches by basename, which is the part an
        agent usually gets right - but a rename that changes the extension
        changes the basename too, so it finds nothing. Measured on run
        d6297b2f: `specialist_backend_0` moved `test/loadTasks.test.mjs` to
        `test/loadTasks.test.js`, then spent a read and an edit on the old
        name, each answered only "not found". That stage ran 47 model calls
        against a next-longest of 10.

        This memo is exact rather than a guess, so it goes first.
        """
        try:
            from app.tools.seen_content import where_this_stage_moved_it

            destination = where_this_stage_moved_it(str(wanted).lstrip("/"))
        except Exception:  # noqa: BLE001 - a hint must never fail the call
            return ""
        if not destination:
            return ""
        return (
            f" This stage moved that file to '/{destination}'. Read that "
            "instead - the old name is gone because you renamed it."
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

    def _the_one_path_it_meant(self, wanted: str) -> str:
        """The workspace path this request unambiguously names, or "".

        `_where_it_actually_is` already finds the file and says where it is. It
        then returns an error, and the stage spends a model call re-asking with
        the path it was just handed.

        Measured on the run of 2026-09-21. `technical_lead` asked for
        `/home/user/workspace/task-manager/package.json`,
        `/home/user/workspace/task-manager/style.css`,
        `/home/user/task-manager/style.css` and
        `/home/user/task-manager/package.json` - four reads, four errors, each
        one naming the real path in its own message. The container path prefix
        is invented; everything after it was right.

        Resolved only when the answer cannot be wrong:

        - exactly one file in the workspace carries that basename, so there is
          nothing to choose between, and
        - the path asked for *ends with* that workspace path, so the request
          agrees with the answer about the directory as well as the name.

        `/home/user/workspace/task-manager/app.js` ends with
        `task-manager/app.js`, so the only thing wrong with it is a prefix the
        agent imagined. A bare `/app.js` that happens to be unique does not end
        with `task-manager/app.js` and is left alone: the agent may have meant a
        file at the root that does not exist, and silently reading a different
        one is the wrong kind of helpful.

        The candidate comes from an `rglob` rooted at the workspace, so the file
        resolved is inside it by construction - this widens what a path may be
        *spelled* as, never what it may reach.
        """
        root = getattr(self, "cwd", None)
        name = _basename(wanted)
        if not root or not name or "." not in name:
            return ""
        try:
            found = [
                str(candidate.relative_to(root))
                for candidate in Path(root).rglob(name)
                if candidate.is_file()
                and not any(part in IGNORED_DIRECTORIES for part in candidate.parts)
            ]
        except Exception:  # noqa: BLE001 - a convenience must never fail the call
            return ""
        if len(found) != 1:
            return ""
        here = found[0].replace("\\", "/")
        asked = str(wanted).replace("\\", "/").lstrip("/")
        if not asked.endswith(here) or asked == here:
            return ""
        return "/" + here


#: How many identical read failures to let pass before saying so. One repeat is
#: ordinary - a stage may reasonably look twice while it works out what to
#: build. The second is the one worth mentioning, matching the threshold the
#: repeated-query middleware uses for every other tool.
READ_FAILURES_BEFORE_SAYING_SO = 1

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
#:
#: Measured across all 50 stored transcripts, counting how often one stage was
#: handed byte-identical content for one unchanged file:
#:
#:     read once   3,013 (file, stage) pairs      read 4 times   39
#:     twice         293                          5 times        25
#:     three times    87                          6 or more      9
#:
#: At 5 this withholds 20 reads across those fifty runs. At 3 it withholds
#: 127, which is about two and a half model calls per run, and on the model
#: these runs use a call costs three and a half minutes.
#:
#: Not 2, which would withhold 287 - because `REPEATS_BEFORE_SAYING_SO` is
#: also 2 and the withholding is tested first, so the note rung would never
#: fire at all. The note is the most-obeyed rung this codebase has measured
#: (91%, against 58% for withholding), and skipping straight past it to the
#: harsher one is the mistake the escalation ladder in
#: `REPEATED_READS_BEFORE_NAMING_THE_EXIT` documents.
#:
#: Three is safe because of what has already happened by then: the model has
#: been handed these exact bytes three times and told about it once, the file
#: has not changed (the count is keyed on the file's identity, so a write
#: resets it), and any other line range still returns content. The
#: withholding message also carries the file's length and its first and last
#: lines, so a stage whose context was compacted away still has an anchor.
READS_BEFORE_WITHHOLDING = 3

#: Repeated reads across ALL files in a stage before the notice stops being
#: about the file and starts being about the stage.
#:
#: Both rungs above are per file, and a stage that cycles three files reaches
#: neither quickly. Measured live on run-cac07d52: `specialist_ui_ux_0`,
#: restarted on a fresh conversation, made 55 reads of which 50 were files the
#: previous attempt had already read, cycling `index.html`, `app.js` and
#: `styles.css` about a dozen times. Both per-file rungs fired - 24 notes and
#: 19 withholdings across the run - and it kept going until the model-call
#: budget stopped it.
#:
#: Deliberately NOT a harsher rung. Measured across all 50 transcripts, every
#: notice that takes something away does worse than the note above it:
#:
#:     note, read repeat   91%    withhold the content  58%
#:     note, write unchanged 64%  refuse the call       38%
#:
#: The order is inverse to harshness, and the working explanation is that a
#: note leaves the model able to act while the harsher rungs do not. So this
#: rung adds information rather than removing more: it names the exit, which
#: is the one thing none of the others say.
REPEATED_READS_BEFORE_NAMING_THE_EXIT = 6

#: Repeated reads across all files before a redundant read stops succeeding.
#:
#: Every rung below this one is a notice attached to a successful result, and
#: measured across the stored transcripts, notices do not stop the reading:
#:
#:     after a note      27.3% read the same file again,   31% did any work
#:     after a withhold  30.0% read the same file again,   61.5% read a
#:                       *different* file, and 8% did any work
#:     after the exit    93.0% read again
#:     notice above
#:
#: The exit notice fired 515 times across 29 stages, and
#: `run-b0db10b1`'s `specialist_ui_ux_0` received it 115 times. Withholding
#: the bytes reduces what a redundant read costs and moves the stage to a
#: different file rather than to work; naming the exit is ignored outright.
#:
#: What does move this model is an error. The `node -e` refusal was answered
#: by writing the code to a file 49% of the time and retried in the same shape
#: 9% of the time - the opposite profile - because a refusal arrives in the
#: channel the model reads as "that did not work", and a withheld result
#: arrives as a success.
#:
#: So past this, a read that would return nothing the stage has not already
#: been given fails instead of succeeding quietly. Twice the exit-notice
#: threshold, and derived from it rather than written again, so the two cannot
#: drift apart: by the time this fires the stage has been handed the exit at
#: least six times and gone on reading.
#:
#: Narrow, in the way that makes it safe: it applies only to a read that is
#: provably redundant - the same bytes, or a range already served, of a file
#: that has not changed since. A read of anything new always succeeds, so a
#: stage that has genuinely lost its context has a way back that a loop does
#: not take.
REPEATED_READS_BEFORE_REFUSING = REPEATED_READS_BEFORE_NAMING_THE_EXIT * 2

#: The opening words of that refusal, named here so the middleware that counts
#: them cannot drift from the backend that writes them. Counting a message by
#: a phrase written somewhere else is how a marker goes stale silently.
READ_REFUSED_MARKER = "Refusing to read"


#: Lines of the withheld file shown at each end, so the message is an anchor
#: rather than only a refusal.
ANCHOR_LINES = 3


def _an_anchor_to_what_was_withheld(text: str) -> str:
    """The shape of the file whose content was not repeated.

    Withholding assumes the model can scroll back to a result it was given
    earlier in the stage. Usually it can. It cannot when the conversation has
    been compacted since, and that is exactly the case where a stage would
    otherwise be told "you already have it" about text that is no longer
    anywhere it can see.

    So the withholding carries the file's length and its first and last few
    lines. A model that still has the earlier result loses nothing; one that
    does not has enough to recognise the file, confirm it has not changed,
    and ask for the line range it needs - which is never withheld, because a
    different range is different bytes.
    """
    lines = (text or "").splitlines()
    if not lines:
        return ""
    if len(lines) <= ANCHOR_LINES * 2:
        # Short enough that the anchor would be the whole file anyway.
        # Withholding a six-line file saves nothing and costs clarity, so
        # this rung quietly becomes a note for files that small.
        shown = "\n".join(f"  {n:>4} | {line[:100]}" for n, line in enumerate(lines, 1))
        return f"\n(All {len(lines)} lines of it, unchanged:\n{shown}\n)"
    head = "\n".join(f"  {n:>4} | {line[:100]}" for n, line in enumerate(lines[:ANCHOR_LINES], 1))
    tail_from = len(lines) - ANCHOR_LINES + 1
    tail = "\n".join(
        f"  {n:>4} | {line[:100]}"
        for n, line in enumerate(lines[-ANCHOR_LINES:], tail_from)
    )
    return (
        f"\n(It is {len(lines)} lines, unchanged. It begins and ends:\n"
        f"{head}\n   ... |\n{tail}\n"
        "Ask for a line range if you need a part you cannot see.)"
    )


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

    def _note_if_already_seen(
        self, path: str, digest: str, first: int, last: int, text: str = ""
    ) -> str:
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
        from app.agents.stage_memory import store

        own = getattr(self, "_read_spans", None)
        if own is None:
            own = {}
            self._read_spans = own  # noqa: SLF001 - own attribute
        seen = store("read_spans", own)
        # Three elements since the withholding rung was added; entries written
        # by the two-element version still unpack.
        entry = seen.get(path, (None, set(), 0))
        previous_digest, covered, nothing_new = (*entry, 0)[:3]
        if previous_digest != digest:
            seen[path] = (digest, set(range(first, last + 1)), 0)
            return ""
        wanted = set(range(first, last + 1))
        fresh = wanted - covered
        covered |= wanted
        if fresh:
            # Bounded: a file large enough for this to matter is already paged.
            seen[path] = (digest, covered if len(covered) < 100_000 else set(), 0)
            return ""
        nothing_new += 1
        seen[path] = (digest, covered if len(covered) < 100_000 else set(), nothing_new)
        self._repeated_reads = getattr(self, "_repeated_reads", 0) + 1
        if nothing_new >= READS_BEFORE_WITHHOLDING:
            # The same rung the byte-identical ladder reaches, on the same
            # count, because they are the same waste. Measured on run-d483f554's
            # `specialist_ui_ux_0`, reading a 391-line `app.js` it had just
            # written:
            #
            #   reads  2-11  whole file      withheld from the 4th   1,111 bytes
            #   read     12  limit=120       3,483 bytes returned in full
            #   reads 12-14  limit=120       withheld on the 3rd
            #   read     15  limit=100       2,897 bytes returned in full
            #   reads 15-17  limit=100       withheld on the 3rd
            #
            # Narrowing the window reset the digest counter and the file came
            # back whole, twice, after ten withholdings - about 19,000
            # characters of lines the stage had already been given. Those six
            # calls are what carried it to the edge of its model-call budget.
            #
            # This rung knows they were not new: it is the check that printed
            # "you have already read lines 1-120" on reads 12 and 13 and
            # returned the bytes anyway.
            self._withheld = True  # noqa: SLF001 - own attribute, read by `read`
            return (
                f"[Lines {first}-{last} are ones this stage has already been "
                f"given, and the file has not changed since. This is the "
                f"{nothing_new}th read of it that returned nothing new, so the "
                "content is not repeated here - scroll back to any earlier "
                "result. A narrower or wider window of the same lines is still "
                "the same lines; if there is a part you have not seen, ask for "
                "a range outside what you have read. Otherwise use what you "
                "have and move on.]"
                + _an_anchor_to_what_was_withheld(text)
                + self._the_way_out()
            )
        return (
            f"\n\n[You have already read lines {first}-{last} of this file in "
            "this stage, and it has not changed since. This returned nothing "
            "you did not already have.]"
            + self._the_way_out()
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

    def _note_if_it_failed_this_way_before(self, file_path: str, error: str) -> str:
        """Whether this stage has already been told exactly this, or "".

        `read_file` is deliberately outside the repeated-query middleware,
        because the read path here keeps a better record - keyed on the file's
        identity as well as its bytes. But that record is only kept for reads
        that succeed. A read that fails is not counted anywhere, so a stage can
        ask for a file that is not there as often as it likes and be told
        "not found" each time, in silence.

        Measured on run 0afef410's `specialist_backend_2`, asked to create
        `app.js`: two identical `read_file` calls for `/task-manager/app.js`,
        two identical `Error: File '/task-manager/app.js' not found`, no notice
        of any kind. `edit_artifact` has had this note since run-9506d3ab -
        "failed the same way the N previous times you ran it in this stage" -
        and a read deserves the same.

        Keyed on the path as the model spelled it and on the error text, so a
        different failure at the same path still reads as new information.
        """
        from app.agents.stage_memory import store

        own = getattr(self, "_failed_reads", None)
        if own is None:
            own = {}
            self._failed_reads = own  # noqa: SLF001 - own attribute
        seen = store("failed_reads", own)

        # Normalised: `/todo/app.js` and `todo/app.js` are the same miss, and
        # keying on the raw spelling gave each its own allowance. See
        # `the_same_place`.
        key = f"{the_same_place(str(file_path))}|{error}"
        count = seen.get(key, 0)
        seen[key] = count + 1
        if count < READ_FAILURES_BEFORE_SAYING_SO:
            return ""
        return (
            f" This read failed the same way the {count} previous "
            "time(s) you ran it in this stage. Nothing has created that file "
            "since, and running it again will fail again. Create it, or carry "
            "on without it."
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
        # Kept in `stage_memory`, not on this instance: the backend is rebuilt
        # with the agent on every approval resume, and a stage that writes a
        # file between two reads - which is what a working stage does - would
        # otherwise start counting again from zero every time. See
        # `app.agents.stage_memory`.
        from app.agents.stage_memory import store

        own = getattr(self, "_read_digests", None)
        if own is None:
            own = {}
            self._read_digests = own  # noqa: SLF001 - own attribute
        seen = store("read_digests", own)

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
        if count >= REPEATS_BEFORE_SAYING_SO:
            self._repeated_reads = getattr(self, "_repeated_reads", 0) + 1
        if count >= READS_BEFORE_WITHHOLDING:
            self._withheld = True  # noqa: SLF001 - own attribute, read by `read`
            return (
                f"[This file has given you these same bytes {count} times in "
                "this stage and has not changed once. The content is not "
                "repeated here, because you already have it - scroll back to "
                "any of those results. If you need a part of it you have not "
                "seen, ask for a different line range. Otherwise use what you "
                "have and move on.]"
                + _an_anchor_to_what_was_withheld(text)
                + self._the_way_out()
            )
        if count >= REPEATS_BEFORE_SAYING_SO:
            return (
                f"\n\n[These are the same bytes this file gave you {count} "
                "previous times in this stage, and it has not changed since. "
                "Asking for a different range of it will not help - this is "
                "the whole file. Use what you have and move on.]"
                + self._the_way_out()
            )
        return ""

    def _refuse_a_read_that_returns_nothing_new(self, file_path: str) -> str:
        """Why this read failed, or "" while it should still succeed.

        The last rung of the ladder, and the first one that is not a notice.
        Reached only by a read that would return nothing this stage has not
        already been given, and only after the stage has ignored the exit
        notice for another six repeated reads - see
        `REPEATED_READS_BEFORE_REFUSING` for the measurement that says notices
        stop working long before this.
        """
        if getattr(self, "_repeated_reads", 0) < REPEATED_READS_BEFORE_REFUSING:
            return ""
        return (
            f"{READ_REFUSED_MARKER} '{file_path}' again: this returns nothing you "
            f"have not already been given, and it is the "
            f"{self._repeated_reads}th time this stage has asked for content "
            "it already has. The file has not changed since you last saw it, "
            "so nothing here can tell you anything new.\n"
            "A range you have NOT read still works, and so does `grep` for "
            "something specific. If you have what you need, return your "
            "structured response now. If something is stopping you, return it "
            "in `blockers` and say what you would need - a blocker is a "
            "complete answer and the workflow acts on it."
        )

    def _the_way_out(self) -> str:
        """Name the exit once a stage is circling over its whole file set.

        Both rungs above are about one file, and say what not to do. A stage
        cycling three files hits neither quickly, and neither ever says what
        it should do instead. This does, and only once the reading has stopped
        being research - see `REPEATED_READS_BEFORE_NAMING_THE_EXIT` for the
        run this was measured on and why it adds information rather than
        taking more away.
        """
        if getattr(self, "_repeated_reads", 0) < REPEATED_READS_BEFORE_NAMING_THE_EXIT:
            return ""
        return (
            "\n\n[You have now re-read files this stage had already been given "
            f"{self._repeated_reads} times, and written nothing between them. "
            "Reading again cannot tell you anything new: nothing has changed "
            "these files since you last saw them. There are two ways out and "
            "both end this stage. If you have what you need, return your "
            "structured response now. If something is stopping you, return it "
            "in `blockers` and say what you would need - a blocker is a "
            "complete answer and the workflow acts on it.]"
        )


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
            # Before explaining where the file is: read it. The explanation was
            # already correct and already cost a model call to act on. See
            # `_the_one_path_it_meant` for what makes this unambiguous.
            instead = self._the_one_path_it_meant(file_path)
            if instead:
                corrected = super().read(instead, *args, **kwargs)
                if not getattr(corrected, "error", None):
                    return self.read(instead, *args, **kwargs)
            # What is in it, before where else it might be: a model that read
            # a directory asked what is in it, and "there is a directory of
            # that name at the path you gave" answers nothing.
            hint = (
                self._what_is_in_it(file_path)
                or self._where_this_stage_moved_it(file_path)
                or self._where_it_actually_is(file_path)
            )
            # After the hint, not instead of it: where the file really is
            # answers the question, and this only adds that asking again will
            # not. A hint that never arrives is what makes the repeat happen.
            hint += self._note_if_it_failed_this_way_before(str(file_path), error)
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
            refusal = self._refuse_a_read_that_returns_nothing_new(file_path)
            if refusal:
                return replace(result, error=refusal)
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
                    str(file_path), self._file_identity(file_path), first, last, content
                )
                if self._withheld:
                    refusal = self._refuse_a_read_that_returns_nothing_new(file_path)
                    if refusal:
                        return replace(result, error=refusal)
                    # Same as the byte-identical rung above: the bytes are
                    # replaced, not prefixed.
                    return replace(result, file_data={**data, "content": note})
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
        path = path.strip()
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
