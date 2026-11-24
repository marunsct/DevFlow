"""An outline of a code file: each thing it defines and each test it declares, with the lines it spans (LF.1287).

Measured on one medium run: the product numbered was about four times the memory a reading stage is given, so 32-37
of its 45 files were "Not included here". The memory's map of them (`project_memory.map_of`) had no line numbers, at
most twelve definitions a file, and a test file showed as its two or three helper functions; a stage that needed one
function read the whole file into its conversation, a summary deleted it, and it read it again. An outline of all 45
files - every definition, every test, each with its first and last line - was 18,475 characters, 6% of the product.
With it in the memory, a stage reads the lines it needs by range.

Read without a parser per language: the patterns the harness already has for a line that defines something
(`project_memory._DEFINES`, `project_graph._DEFINES_ELSEWHERE`) and for a declared test (`suite._TITLED`,
`suite._NAMED`), and the marker line directly above a definition - a line that is not itself a definition, starts
with a character that is not a letter, digit or quote, goes straight on to a name (not a space, as a comment does)
and names something - which is where most languages write a handler's address. Anything a language needs beyond
this belongs in a column of `app.stacks.languages`, not here.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Iterable, Mapping, Sequence

#: The most of a line an entry shows, in characters.
MOST_ENTRY_CHARACTERS = 110
#: The most of a marker line shown before its definition.
MOST_MARKER_CHARACTERS = 60


@lru_cache(maxsize=1)
def _patterns() -> tuple[re.Pattern[str], ...]:
    from app.acceptance.suite import _NAMED, _TITLED
    from app.agents.project_memory import _DEFINES
    from app.analysis.project_graph import _DEFINES_ELSEWHERE

    return _DEFINES, _DEFINES_ELSEWHERE, _TITLED, _NAMED


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _shown(line: str) -> str:
    return " ".join(line.strip().rstrip("{:").split())


#: The characters a marker line opens with, up to the name it marks.
_OPENING = re.compile(r"[^\w\s'\"`]+")


def _a_marker(line: str) -> bool:
    """A line above a definition that marks it: `@app.get("/x")`, `#[test]`, `[HttpGet("x")]`. Not `}` or `*/`, which
    name nothing, and not a comment: its opening characters are followed by a space (`# ...`, `// ...`)."""
    stripped = line.strip()
    opening = _OPENING.match(stripped)
    return bool(opening) and len(stripped) > opening.end() and not stripped[opening.end()].isspace() and any(
        c.isalpha() for c in stripped)


def _a_comment(line: str) -> bool:
    """A line of words after opening characters and a space (`# ...`, `// ...`, `-- ...`): what the next line is."""
    stripped = line.strip()
    opening = _OPENING.match(stripped)
    return bool(opening) and len(stripped) > opening.end() and stripped[opening.end()].isspace() and any(
        c.isalpha() for c in stripped)


def entries(path: str, text: str) -> list[tuple[int, int, str]]:
    """(first line, last line, the line's text) for each definition and test `text` declares, in file order.

    An entry's last line is the line before the next entry at the same or a lesser indent, or before the first line
    less indented than its own (the file's last line when neither comes), less the blank lines before it. A marker
    line directly above a definition is shown with it, and the entry starts there; so does a comment line directly
    above it, not shown. `path` is the file's name; the reading is the same for every language."""
    defines, elsewhere, titled, named = _patterns()
    lines = str(text or "").splitlines()
    found: list[tuple[int, int, str]] = []  # (first line, indent, text), 1-based
    for number, line in enumerate(lines, start=1):
        test = titled.search(line)
        if test and not defines.match(line):
            found.append((number, _indent(line), f"test: {test.group(2)}"))
            continue
        if not (defines.match(line) or elsewhere.match(line) or named.search(line)):
            continue
        first, said = number, _shown(line)
        above = lines[number - 2] if number > 1 else ""
        if above and not (defines.match(above) or elsewhere.match(above) or titled.search(above)):
            if _a_marker(above):
                first, said = number - 1, f"{_shown(above)[:MOST_MARKER_CHARACTERS]}  {said}"
            elif _a_comment(above):
                first = number - 1  # the line saying what it is belongs to it, not to the entry before
        found.append((first, _indent(line), said))
    result: list[tuple[int, int, str]] = []
    for index, (first, indent, said) in enumerate(found):
        last = len(lines)
        for later_first, later_indent, _ in found[index + 1:]:
            if later_indent <= indent:
                last = later_first - 1
                break
        # A line less indented than the entry's own closes it: its block has ended.
        for number in range(first + 1, last + 1):
            if lines[number - 1].strip() and _indent(lines[number - 1]) < indent:
                last = number - 1
                break
        while last > first and not lines[last - 1].strip():
            last -= 1
        result.append((first, max(first, last), said[:MOST_ENTRY_CHARACTERS]))
    return result


def block(path: str, text: str) -> str:
    """One file's part of an outline: `path (N lines)`, then one entry a line as `first-last  text`."""
    count = len(str(text or "").splitlines())
    return f"{path} ({count} lines)\n" + "".join(f"  {a}-{b}  {said}\n" for a, b, said in entries(path, text))


def shown_of(blocks: Mapping[str, str], most_characters: int, order: Sequence[str] = ()) -> list[str]:
    """The files an outline of `blocks` names, in path order: all while they fit in `most_characters`; past it, those
    first in `order` (then the rest by path) that still fit, as `project_memory.map_of` does."""
    if sum(len(b) for b in blocks.values()) <= most_characters:
        return sorted(blocks)
    chosen: set[str] = set()
    used = 0
    for path in [*dict.fromkeys(p for p in order if p in blocks), *sorted(p for p in blocks if p not in set(order))]:
        if used + len(blocks[path]) > most_characters:
            continue
        chosen.add(path)
        used += len(blocks[path])
    return sorted(chosen)


def rendered(files: Mapping[str, str], most_characters: int, order: Sequence[str] = ()) -> str:
    """The outline of `files` (path -> text) within `most_characters`: no cap per file; past the size, the files are
    taken in `order` and the rest counted. "" for no file."""
    blocks = {path: block(path, text) for path, text in files.items()}
    return rendered_blocks(blocks, most_characters, order)


def rendered_blocks(blocks: Mapping[str, str], most_characters: int, order: Sequence[str] = ()) -> str:
    """`rendered` from blocks already made (`block`)."""
    shown = shown_of(blocks, most_characters, order)
    left = len(blocks) - len(shown)
    return "".join(blocks[path] for path in shown) + (
        f"({left:,} more files are not outlined here; list a folder or search to find them.)\n" if left else "")


def texts_of(paths: Iterable[str], files: Mapping[str, str]) -> dict[str, list[str]]:
    """Each path's entry texts, for ranking by the words a request uses (`project_memory._by_relevance`)."""
    return {path: [said for _, _, said in entries(path, files[path])] for path in paths if path in files}


__all__ = ["block", "entries", "rendered", "rendered_blocks", "shown_of", "texts_of"]
