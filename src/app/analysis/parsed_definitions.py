"""What a source file defines and imports, read from its syntax tree with the bundled grammar (plan KG.2).

The code graph read definitions with one line pattern for every language and followed imports in Python and
JavaScript/TypeScript only. In a Go, Java, Kotlin, C#, Rust, Ruby or PHP project the graph therefore knew no edge at
all: a fixer was told nothing its handler imports, a sliced memory held only the files named, and the map ranked
every module as imported by none.

This reads each file's tree with the grammar `tree_sitter_language_pack` bundles (a worker dependency already, see
`grammar_parse`), through the patterns its language's row of `app.stacks.languages` gives (`LanguageSupport.tree`):
every definition with its kind, name, first and last line and the definition it sits in; every import statement's
text, for the row's resolver in `app.analysis.import_resolvers`; and the package or namespace the file declares.

A tree with error nodes is still read. A grammar that mis-reads one valid file in a hundred is unfit to refuse a
write (which is why `grammar_parse` leaves some languages out) but fit to list what a file defines: the definitions
around the misread part are still found. Where no grammar loads, `read` answers None and the caller keeps its
patterns.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import PurePath
from typing import Any

from app.stacks.languages import LANGUAGES, Gap, LanguageSupport, TreeReading

logger = logging.getLogger(__name__)

#: Kinds a function written inside is a method of.
_TYPE_KINDS = frozenset({"class", "interface", "struct", "trait", "impl", "object", "enum", "record"})
#: Files whose reading is kept, at most; past it the oldest go first.
MOST_HELD = 20_000


@dataclass(frozen=True)
class Definition:
    """One thing a file defines: its kind (`function`, `class`, `method`, ...), its name, its first and last line
    (1-based), and the name of the definition it sits in ("" at the file's top)."""

    kind: str
    name: str
    first: int
    last: int
    enclosing: str = ""

    def as_row(self) -> list[Any]:
        """`[kind, name, first, last, enclosing]`, the code graph's stored form."""
        return [self.kind, self.name, self.first, self.last, self.enclosing]


@dataclass(frozen=True)
class Parsed:
    """A file as its syntax tree reads: what it defines, its imports and the namespaces it declares."""

    definitions: tuple[Definition, ...]
    #: (the capture's name - `import`, `import.relative`, ... - and the text it captured), in file order.
    imports: tuple[tuple[str, str], ...]
    namespaces: tuple[str, ...]

    @property
    def top_names(self) -> frozenset[str]:
        """The names defined at the file's top, outside any other definition."""
        return frozenset(d.name for d in self.definitions if not d.enclosing)


def row_for(path: str | PurePath) -> tuple[LanguageSupport, TreeReading, str] | None:
    """(the language's row, its tree reading, the grammar) for a file, by its suffix; None when none reads it."""
    return _by_suffix().get(PurePath(path).suffix.lower())


@lru_cache(maxsize=1)
def _by_suffix() -> dict[str, tuple[LanguageSupport, TreeReading, str]]:
    found: dict[str, tuple[LanguageSupport, TreeReading, str]] = {}
    for row in LANGUAGES:
        if isinstance(row.tree, Gap):
            continue
        for suffix, grammar in row.tree.grammars.items():
            found.setdefault(suffix, (row, row.tree, grammar))
    return found


@lru_cache(maxsize=None)
def _compiled(language_name: str, grammar: str) -> tuple[Any, Any, Any, Any] | None:
    """(the parser, the definitions query, the imports query, the namespaces query) for a language's grammar; None
    when the grammar does not load or a pattern does not fit it."""
    try:
        reading = next(row.tree for row in LANGUAGES if row.name == language_name)
        if not isinstance(reading, TreeReading):
            return None
        from tree_sitter import Query
        from tree_sitter_language_pack import get_language, get_parser

        language = get_language(grammar)  # type: ignore[arg-type]
        parser = get_parser(grammar)  # type: ignore[arg-type]
        definitions = Query(language, "\n".join(reading.definitions))
        imports = Query(language, "\n".join(reading.imports)) if reading.imports else None
        namespaces = Query(language, "\n".join(reading.namespaces)) if reading.namespaces else None
        return parser, definitions, imports, namespaces
    except Exception:  # noqa: BLE001 - no grammar is the patterns' answer
        logger.debug("No tree reading for grammar %s", grammar, exc_info=True)
        return None


def loads(path: str | PurePath) -> bool:
    """Whether a grammar reads this file: its language has a tree reading and the grammar loads."""
    found = row_for(path)
    return found is not None and _compiled(found[0].name, found[2]) is not None


def _matches(query: Any, node: Any) -> list[tuple[int, dict[str, list[Any]]]]:
    from tree_sitter import QueryCursor

    return QueryCursor(query).matches(node)


def _text(node: Any) -> str:
    return (node.text or b"").decode("utf-8", "replace")


def _lines(node: Any) -> tuple[int, int]:
    first, last = node.start_point[0] + 1, node.end_point[0] + 1
    if node.end_point[1] == 0 and last > first:
        last -= 1  # a node ending at the start of a line ends on the line before
    return first, last


def _definitions(query: Any, root: Any) -> tuple[Definition, ...]:
    chosen: dict[tuple[int, int], tuple[int, str, str, str, Any]] = {}
    for pattern, captures in _matches(query, root):
        kinds = [name for name in captures if name not in ("name", "owner") and not name.startswith("_")]
        if not kinds or not captures.get("name"):
            continue
        node = captures[kinds[0]][0]
        key = (node.start_byte, node.end_byte)
        held = chosen.get(key)
        if held is not None and held[0] <= pattern:
            continue  # the pattern listed first says what it is
        owner = _text(captures["owner"][0]) if captures.get("owner") else ""
        chosen[key] = (pattern, kinds[0], _text(captures["name"][0]).strip(), owner, node)
    ordered = sorted(chosen.items(), key=lambda item: (item[0][0], -item[0][1]))
    found: list[Definition] = []
    open_ones: list[tuple[int, str, str]] = []  # (end byte, name, kind) of the definitions around this one
    for (start, end), (_pattern, kind, name, owner, node) in ordered:
        while open_ones and open_ones[-1][0] <= start:
            open_ones.pop()  # it ended before this one starts
        around = open_ones[-1] if open_ones else None
        enclosing = owner or (around[1] if around else "")
        if kind == "function" and around is not None and around[2] in _TYPE_KINDS:
            kind = "method"
        first, last = _lines(node)
        if name:
            found.append(Definition(kind=kind, name=name, first=first, last=last, enclosing=enclosing))
        open_ones.append((end, name, kind))
    return tuple(found)


def read(path: str | PurePath, text: str) -> Parsed | None:
    """`text` read as the file `path` names: None when no grammar reads its language. Never raises."""
    found = row_for(path)
    if found is None:
        return None
    compiled = _compiled(found[0].name, found[2])
    if compiled is None:
        return None
    parser, definitions, imports, namespaces = compiled
    try:
        root = parser.parse(str(text or "").encode("utf-8", "replace")).root_node
        imported: list[tuple[int, str, str]] = []
        if imports is not None:
            for _pattern, captures in _matches(imports, root):
                for name, nodes in captures.items():
                    if name.startswith("import"):
                        imported.extend((node.start_byte, name, _text(node)) for node in nodes)
        declared: list[str] = []
        if namespaces is not None:
            for _pattern, captures in _matches(namespaces, root):
                declared.extend("".join(_text(node).split()) for node in captures.get("namespace", ()))
        return Parsed(
            definitions=_definitions(definitions, root),
            imports=tuple((name, said) for _start, name, said in sorted(imported)),
            namespaces=tuple(dict.fromkeys(declared)),
        )
    except Exception:  # noqa: BLE001 - a file the grammar cannot read falls back to the patterns
        logger.debug("Could not read %s with its grammar", path, exc_info=True)
        return None


_LOCK = threading.Lock()
#: (path, modification time, size) -> its reading, so an unchanged file is not parsed again when another changed.
_HELD: dict[tuple[str, int, int], Parsed | None] = {}


def read_cached(path: str | PurePath, text: str, mtime_ns: int, size: int) -> Parsed | None:
    """`read`, kept for the file as it is (its modification time and size): one changed file is the only one
    parsed again."""
    key = (str(path), int(mtime_ns), int(size))
    with _LOCK:
        if key in _HELD:
            return _HELD[key]
    parsed = read(path, text)
    with _LOCK:
        if len(_HELD) >= MOST_HELD:
            for old in list(_HELD)[: MOST_HELD // 4]:
                del _HELD[old]
        _HELD[key] = parsed
    return parsed


__all__ = ["Definition", "MOST_HELD", "Parsed", "loads", "read", "read_cached", "row_for"]
