"""What each file in this workspace is for, carried between stages.

Every stage is a fresh agent with an empty conversation. The only thing
carried between them is `workspace_digest`, which lists names, line counts
and exported symbol *names*, and stops there.

Measured across the 50 stored transcripts, keying every `read_file` result on
the normalised path and the SHA-1 of the bytes returned:

    first time anyone in the run saw these bytes      2,162   54%
    A LATER STAGE, bytes an earlier stage already had  1,199   30%
    same stage, bytes it already had                     640   16%

The 16% is already under attack - the digest stops a stage going looking, and
`workspace_backend._note_if_repeated` tells it when bytes are ones it has
already been handed. The 30% had nothing aimed at it at all, and that number
says exactly what this module has to carry: enough that a later stage does
not need the bytes.

Two things are missing from a list of names:

* **What the file is for.** `task-manager/app.js (348 lines): createTask,
  toggleTask, deleteTask` does not say whether `app.js` is the model, the
  view or the entry point. Taken from the file's own header comment, which
  its author has usually already written - one run's `server.mjs` opens
  with "Minimal static file server for Playwright testing", a better line
  than any separate model call would produce, and free.
* **How to call it.** `createTask` does not say whether it takes a title, an
  object or nothing. A signature does, and "can I call this with what I
  have" is the commonest reason a later stage opens a file it has already
  been told about.

Nothing here asks a model for anything and no tool gains an argument: every
field is derived from the file. A file whose author wrote no header comment
still gets an entry, without a purpose line. Returning "" is always
preferred to guessing - a wrong purpose line is worse than none, because a
stage will act on it *without reading the file*, which is the entire point.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)

#: Where the index lives, beside the workspace it describes.
MEMORY_FILE = ".project-memory.json"

#: Longer than this and the line is a paragraph, not a purpose.
MAX_PURPOSE_CHARS = 140

#: Signatures past this and the entry is longer than the file is worth.
MAX_SIGNATURES = 8


class FileNote(NamedTuple):
    """One file, as a later stage needs to know it."""

    path: str
    lines: int
    purpose: str
    interface: str
    changed_by: str
    changed_at: str


# --- the purpose, in any language -----------------------------------------

#: A Python module docstring, as the first statement.
_PY_DOCSTRING = re.compile(r'\A\s*(?:#![^\n]*\n)?\s*(?:"""|\'\'\')(.*?)(?:"""|\'\'\')', re.S)

#: A block comment at the top: `/** ... */` or `/* ... */`, before any code.
_BLOCK_COMMENT = re.compile(r"\A\s*/\*+(.*?)\*/", re.S)

#: A run of single-line comments at the top, in whichever marker the language
#: uses. `//` covers C-family, `#` shell/Python/Ruby/YAML, `--` SQL/Haskell/
#: Lua, `;` Lisp/assembly, `%` Erlang/LaTeX, `'` Visual Basic.
_LINE_COMMENTS = re.compile(
    # The final newline is optional: a one-line file that is nothing but its
    # header comment matched nothing at all without this.
    r"\A(?:[ \t]*(?://|#|--|;|%)[^\n]*(?:\n|\Z))+", re.M
)

#: An HTML or XML comment at the top.
_MARKUP_COMMENT = re.compile(r"\A\s*<!--(.*?)-->", re.S)

#: A Markdown heading, which is what a document's purpose is written as.
_MARKDOWN_HEADING = re.compile(r"\A\s*#{1,3}[ \t]+([^\n]+)")

#: Decoration rather than words: a rule of dashes, equals or stars.
_JUST_DECORATION = re.compile(r"\A[\s*=_~#/\\|+.-]*\Z")

#: A licence or copyright header, an encoding line or a linter pragma - none
#: of which says anything about what this file does.
_BOILERPLATE = re.compile(
    r"(?:\bcopyright\b|\blicen[cs]e\b|\ball rights reserved\b|SPDX-"
    r"|\bLicensed under\b|eslint-disable|prettier-ignore|@ts-nocheck"
    r"|shellcheck|coding[:=]\s*[-\w.]+|\bvim:|\bemacs:)",
    re.I,
)


def _cleaned(block: str) -> str:
    """The first real sentence of a comment block, or ""."""
    words: list[str] = []
    for raw in block.splitlines():
        line = raw.strip()
        if line.startswith("#!"):
            continue  # a shebang names an interpreter, not a purpose
        # Boilerplate is judged before the markers come off: stripping `#`
        # then `-` turns `# -*- coding: utf-8 -*-` into `*- coding ...`, which
        # the pattern no longer recognises.
        if _BOILERPLATE.search(line):
            if words:
                break
            continue
        for marker in ("*", "//", "#", "--", ";", "%", "!"):
            while line.startswith(marker):
                line = line[len(marker):].lstrip()
        if not line or _JUST_DECORATION.match(line):
            if words:
                break  # a blank line ends the opening paragraph
            continue
        if line.startswith("@"):
            break  # a JSDoc tag block: the prose above it is the purpose
        words.append(line)
        if line.endswith((".", "!", "?")) or len(" ".join(words)) >= MAX_PURPOSE_CHARS:
            break
    text = " ".join(words).strip()
    if not text:
        return ""
    # One sentence. A header that runs to a paragraph says more than a stage
    # needs and costs the context the index exists to save.
    stop = text.find(". ")
    if stop > 0:
        text = text[: stop + 1]
    return text[:MAX_PURPOSE_CHARS].strip()


def _without_the_file_name(purpose: str, path: str) -> str:
    """Drop a leading `server.mjs - ` from a purpose line.

    A common header shape, and the name is already the first thing the entry
    prints. Only when a separator follows it, so a sentence that happens to
    begin with the file's name is left alone.

    The full relative path is tried first: measured on one run, the
    header of `task-manager/app.js` opens `task-manager/app.js — ES module
    with all task management logic`, so matching only the base name left the
    directory in.
    """
    name = Path(path).name
    # A spelling that carries the extension is unmistakably a label, so it may
    # be dropped with or without a separator - measured on one run,
    # "task-manager/style.css Production styles for the Task Manager
    # single-page app". The bare stem still needs one, because a sentence
    # that happens to open with the word must be left alone.
    for prefix, needs_a_separator in ((str(path), False), (name, False),
                                      (Path(path).stem, True)):
        if not prefix or not purpose.lower().startswith(prefix.lower()):
            continue
        rest = purpose[len(prefix):].lstrip()
        if rest[:1] in {"-", "\u2014", "\u2013", ":", ","}:
            return rest[1:].lstrip() or purpose
        if not needs_a_separator and rest:
            return rest
    return purpose


def _is_just_the_file_name(purpose: str, path: str) -> bool:
    """`// app.js` is a label, not a purpose."""
    bare = re.sub(r"[^a-z0-9]", "", purpose.lower())
    name = re.sub(r"[^a-z0-9]", "", Path(path).name.lower())
    stem = re.sub(r"[^a-z0-9]", "", Path(path).stem.lower())
    return bare in {name, stem} or (len(bare) < 4)


def purpose_of(text: str, path: str) -> str:
    """What this file says it is for, from its own header. "" when it does not.

    Never raises and never guesses. A wrong purpose line is worse than none,
    because a stage acts on it instead of reading the file.
    """
    try:
        suffix = Path(path).suffix.lower()
        candidates = []
        if suffix in {".md", ".markdown", ".rst", ".txt"}:
            heading = _MARKDOWN_HEADING.search(text)
            if heading:
                candidates.append(heading.group(1))
        if suffix in {".html", ".htm", ".xml", ".svg", ".vue", ".md"}:
            markup = _MARKUP_COMMENT.match(text)
            if markup:
                candidates.append(markup.group(1))
        docstring = _PY_DOCSTRING.match(text)
        if docstring:
            candidates.append(docstring.group(1))
        block = _BLOCK_COMMENT.match(text)
        if block:
            candidates.append(block.group(1))
        run = _LINE_COMMENTS.match(text)
        if run:
            candidates.append(run.group(0))
        for candidate in candidates:
            purpose = _without_the_file_name(_cleaned(candidate), path)
            if purpose and not _is_just_the_file_name(purpose, path):
                return purpose
    except Exception:  # noqa: BLE001 - an index that throws is worse than an empty one
        logger.debug("Could not read a purpose from %s", path, exc_info=True)
    return ""


# --- the interface, in any language ---------------------------------------

#: Declarations that carry a parameter list, across the languages this
#: harness builds in. Each captures (name, parameters).
_SIGNATURES = (
    # JS/TS: function, const arrow, method-ish
    re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*"
               r"([A-Za-z_$][\w$]*)\s*\(([^)]{0,600})\)", re.M),
    re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*="
               r"\s*(?:async\s*)?\(([^)]{0,600})\)\s*=>", re.M),
    # Python
    re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_][\w]*)\s*\(([^)]{0,600})\)", re.M),
    # Go
    re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\(([^)]{0,600})\)", re.M),
    # Rust
    re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z_]\w*)\s*\(([^)]{0,600})\)", re.M),
    # Java / C# / Kotlin / Swift / PHP / C / C++
    re.compile(r"^\s*(?:public|private|protected|internal|static|final|override|"
               r"suspend|open|abstract|\s)*(?:fun|func|void|[A-Za-z_][\w<>\[\].]*)\s+"
               r"([A-Za-z_]\w*)\s*\(([^)]{0,600})\)\s*(?:\{|;|throws|->|:)", re.M),
    # Ruby
    re.compile(r"^\s*def\s+([A-Za-z_]\w*[?!=]?)\s*\(([^)]{0,600})\)", re.M),
)

#: A type or class declaration, which has no parameter list but is an
#: interface all the same.
_TYPES = re.compile(
    r"^\s*(?:export\s+)?(?:public\s+|pub\s+)?(?:abstract\s+)?"
    r"(?:class|interface|struct|enum|type|trait|record|protocol)\s+([A-Za-z_]\w*)",
    re.M,
)

#: Keywords a declaration regex mistakes for a function name. Control flow
#: only, deliberately: `go`, `new`, `print`, `match`, `select`, `is` and `as`
#: were on this list and every one of them is a name a real function has.
#: Dropping a genuine name from the interface is the failure that matters -
#: the line exists so a stage need not open the file, and a missing entry
#: sends it there.
_NOT_A_NAME = frozenset({
    "if", "for", "while", "switch", "catch", "return", "else", "do", "try",
    "when", "defer", "case", "default", "break", "continue", "throw",
    "yield", "await", "typeof", "sizeof", "with", "elif", "except",
    "finally", "unless", "until", "foreach",
})


def _balanced(parameters: str) -> bool:
    """Whether a captured parameter list closes everything it opens."""
    depth = 0
    for character in parameters:
        if character in "([{":
            depth += 1
        elif character in ")]}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def interface_of(text: str, limit: int = MAX_SIGNATURES) -> str:
    """The callable surface of a file: names with their parameters.

    `createTask(title, dueDate)` answers "can I call this with what I have";
    `createTask` does not. Never raises - an index that throws is worse than
    one with an empty field.
    """
    found: list[str] = []
    seen: set[str] = set()
    try:
        for match in _TYPES.finditer(text):
            name = match.group(1)
            if name in _NOT_A_NAME or name in seen:
                continue
            seen.add(name)
            found.append(name)
            if len(found) >= limit:
                return ", ".join(found)
        for pattern in _SIGNATURES:
            for match in pattern.finditer(text):
                name = match.group(1)
                if name in _NOT_A_NAME or name in seen:
                    continue
                seen.add(name)
                parameters = " ".join(match.group(2).split())
                if not _balanced(parameters):
                    # `[^)]` stops at the first `)`, which a default value or
                    # a destructured argument can contain: measured on
                    # one run, `createMockStorage({ getItemFn = ()`. A
                    # signature cut mid-expression is worse than a bare name,
                    # because a stage will try to call it.
                    found.append(name)
                else:
                    if len(parameters) > 80:
                        parameters = parameters[:77] + "..."
                    found.append(f"{name}({parameters})")
                if len(found) >= limit:
                    return ", ".join(found)
    except Exception:  # noqa: BLE001 - never fail a digest over a signature
        logger.debug("Could not read an interface", exc_info=True)
    return ", ".join(found)


# --- who last changed it --------------------------------------------------


def _memory_path(root: Path) -> Path:
    return Path(root) / MEMORY_FILE


#: Held across the read-modify-write in `record`.
#:
#: One entry is written by reading the whole file, changing one key and writing
#: the whole file back. With one stage running at a time that is sound. Parallel
#: execution mode fans a milestone's specialists out to run at once, and two of
#: them recording a write together means each reads the file before the other's
#: change lands, so one entry is silently dropped - and `write_text` truncates
#: before it writes, so a reader arriving mid-write sees invalid JSON and
#: `_load` starts the memory over from empty.
_WRITING = threading.Lock()


def _load(root: Path) -> dict[str, dict]:
    try:
        raw = _memory_path(root).read_text(encoding="utf-8")
        held = json.loads(raw)
        return held if isinstance(held, dict) else {}
    except Exception:  # noqa: BLE001 - no memory is a fresh start, not a failure
        return {}


def record(root: str | Path, relative_path: str, stage: str = "") -> None:
    """Remember that `stage` last changed `relative_path`. Never raises.

    Only the authorship is stored. Purpose and interface are read from the
    file when the digest is built, so they cannot go stale - a file changed
    outside the tools, by a formatter or a test runner writing a snapshot, is
    described correctly whether or not anything told this module.
    """
    try:
        from app.agents.workspace_paths import the_same_place

        path = the_same_place(str(relative_path))
        if not path:
            return
        root = Path(root)
        with _WRITING:
            held = _load(root)
            before = held.get(path, {})
            held[path] = {
                "changed_by": str(stage or "") or before.get("changed_by", ""),
                "changed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                # Kept from the first write on: see `who_created`.
                "created_by": before.get("created_by", "") if before else str(stage or ""),
            }
            _write_atomically(_memory_path(root), json.dumps(held, indent=1, sort_keys=True))
    except Exception:  # noqa: BLE001 - a memory that fails a write is worse than none
        logger.debug("Could not record %s in the project memory", relative_path, exc_info=True)


def record_move(root: str | Path, from_path: str, to_path: str) -> None:
    """The file's record follows it to its new name. Never raises.

    A move keeps the bytes, so it keeps who wrote them. Without this a renamed
    file had no author at all, and the checks that ask "did this stage create
    it?" - a testing stage deleting its own probe after renaming it out of the
    test runner's way - found nobody.
    """
    try:
        from app.agents.workspace_paths import the_same_place

        source, target = the_same_place(str(from_path)), the_same_place(str(to_path))
        if not source or not target:
            return
        root = Path(root)
        with _WRITING:
            held = _load(root)
            if source not in held:
                return
            held[target] = held.pop(source)
            _write_atomically(_memory_path(root), json.dumps(held, indent=1, sort_keys=True))
    except Exception:  # noqa: BLE001 - a memory that fails a write is worse than none
        logger.debug("Could not move %s to %s in the project memory", from_path, to_path, exc_info=True)


def _write_atomically(path: Path, content: str) -> None:
    """Replace `path`'s contents in one step, or leave them as they were.

    `write_text` opens for truncation first, so there is a window in which the
    file on disk is empty or half written. Every reader of this file treats
    unreadable as "no memory at all", which is the worst possible reading of a
    write in progress. A temporary file in the same directory followed by
    `os.replace` has no such window: readers see either the old contents or the
    new ones.
    """
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(path.parent),
        prefix=f".{path.name}.", suffix=".tmp", delete=False,
    )
    try:
        with handle:
            handle.write(content)
        os.replace(handle.name, path)
    except Exception:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise


def who_changed(root: str | Path, relative_path: str) -> str:
    """The stage that last wrote this file, or "". Never raises."""
    try:
        from app.agents.workspace_paths import the_same_place

        entry = _load(Path(root)).get(the_same_place(str(relative_path)), {})
        return str(entry.get("changed_by") or "")
    except Exception:  # noqa: BLE001
        return ""


def files_changed_by(root: str | Path, stage: str) -> list[str]:
    """The files `stage` was the last to change, oldest change first; [] when none or unknown. Never raises."""
    try:
        held = _load(Path(root))
        mine = [(str(e.get("changed_at") or ""), path) for path, e in held.items()
                if isinstance(e, dict) and stage and e.get("changed_by") == stage]
        return [path for _, path in sorted(mine)]
    except Exception:  # noqa: BLE001
        return []


def who_created(root: str | Path, relative_path: str) -> str:
    """The stage that first wrote this file, or "". Never raises.

    Not the same question as `who_changed`. One run's `specialist_testing_2`
    edited a suite `specialist_backend_1` had written, which made it the last
    writer, and then renamed the suite out of the test runner's reach as though
    it were its own scratch file.
    """
    try:
        from app.agents.workspace_paths import the_same_place

        entry = _load(Path(root)).get(the_same_place(str(relative_path)), {})
        return str(entry.get("created_by") or "")
    except Exception:  # noqa: BLE001
        return ""


def note_for(root: str | Path, relative_path: str, text: str) -> FileNote:
    """Everything the index knows about one file. Never raises."""
    root = Path(root)
    entry = _load(root).get(str(relative_path), {})
    return FileNote(
        path=str(relative_path),
        lines=text.count("\n") + 1 if text else 0,
        purpose=purpose_of(text, relative_path),
        interface=interface_of(text),
        changed_by=str(entry.get("changed_by") or ""),
        changed_at=str(entry.get("changed_at") or ""),
    )


__all__ = [
    "who_created",
    "MAX_PURPOSE_CHARS",
    "MAX_SIGNATURES",
    "MEMORY_FILE",
    "FileNote",
    "interface_of",
    "note_for",
    "purpose_of",
    "record",
    "who_changed",
]
