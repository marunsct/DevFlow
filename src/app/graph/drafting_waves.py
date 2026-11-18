"""The product's files drafted in waves of what they depend on (behind `DRAFTING_IN_WAVES`).

Deep review 2026-11-18, item 1.6. Drafting wrote every product file in one
concurrent wave, each shown its siblings "as they are on disk" - on a first
draft, nothing. Measured: a Rust run's handlers took one kind of shared state
while the entry file applied another, two files drafted blind to each other,
and every route answered 500; C# runs declared one interface twice in two
files and wrote a service calling a registry nobody wrote.

What is known before a line is written decides the order: the specification's
file plan (each entry names the files it imports from), the work orders' own
`interfaces` and steps, the pack's declared entry files, and what a file's
name says it holds (data shapes and stores). Files with nothing before them
are drafted first, the entry file that wires the rest last, at most
`MOST_WAVES` waves; a product of one or two code files is one wave, which is
drafting as it was. Each later file is shown the earlier files it depends on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Collection, Iterable

from app.switches import is_on

#: Off in code like every switch; the compose file turns it on.
ON_BY_DEFAULT = False
#: Waves at most: each one is a round of drafts and a compile, so more would cost more time than order gains.
MOST_WAVES = 3
#: A product of fewer code files than this is drafted in one wave.
FEWEST_FILES_FOR_WAVES = 3

#: Words a file's name or folder uses, in any language, for what the rest of the code is built on: the shapes of
#: its data and where they are kept. Read from a name, never from content, so a file written before is no different.
_FOUNDATION_WORDS = frozenset({
    "types", "type", "typings", "models", "model", "schema", "schemas", "entities", "entity", "domain", "dto", "dtos",
    "records", "interfaces", "contracts", "errors", "error", "exceptions", "constants", "settings", "config",
    "store", "stores", "storage", "repository", "repositories", "repo", "repos", "db", "database", "persistence",
})
#: A clause that says another file depends on the one it describes: "used by `server.ts`".
_REVERSED = re.compile(
    r"\b(?:used|imported|called|consumed|required|loaded|mounted|wired|served|rendered|included|registered)\s+"
    r"(?:\w+\s+)?by\b", re.I)
#: Where one clause of a plan line ends.
_CLAUSE_END = re.compile(r";|\||\n|\.\s")
#: One line of a file plan: its indent, an optional list marker, then its first word (as `drafting.planned_files`).
_PLAN_LINE = re.compile(r"^(?P<indent>[ \t]*)(?:[-*+]|\d+[.)])?[ \t]*(?P<head>\S+)")


def enabled() -> bool:
    return is_on("DRAFTING_IN_WAVES", ON_BY_DEFAULT)


@dataclass(frozen=True)
class Waves:
    """The files in drafting order, and for each file the earlier waves' files it depends on."""

    waves: list[list[str]]
    needs: dict[str, list[str]] = field(default_factory=dict)


def _plain(path: str) -> str:
    return str(path).strip().replace("\\", "/").lstrip("./")


def _references(path: str) -> set[str]:
    """How a text may name `path`: each trailing part of it, and without its extension as a module (`app.models`)."""
    parts = _plain(path).split("/")
    found = {"/".join(parts[i:]) for i in range(len(parts))}
    stem = [*parts[:-1], PurePosixPath(parts[-1]).stem]
    for i in range(len(stem) - 1):
        tail = stem[i:]
        found.update({"/".join(tail), ".".join(tail), "::".join(tail)})
    return {ref for ref in found if ref}


class _Namer:
    """Finds which of the files a text names, by the references only one of them has."""

    def __init__(self, paths: Iterable[str]):
        owners: dict[str, set[str]] = {}
        for path in paths:
            for ref in _references(path):
                owners.setdefault(ref, set()).add(path)
        self._owner = {ref: next(iter(files)) for ref, files in owners.items() if len(files) == 1}
        refs = sorted(self._owner, key=len, reverse=True)
        self._pattern = (re.compile(r"(?<![\w-])(" + "|".join(re.escape(r) for r in refs) + r")(?![\w])")
                         if refs else None)

    def named(self, text: str) -> list[str]:
        if self._pattern is None:
            return []
        return list(dict.fromkeys(self._owner[m.group(1)] for m in self._pattern.finditer(str(text or ""))))


def _clauses(text: str) -> list[tuple[str, bool]]:
    """(clause, whether it says the files it names depend on the subject), in order."""
    out = []
    for clause in _CLAUSE_END.split(text):
        reversed_at = _REVERSED.search(clause)
        if reversed_at:
            out.append((clause[:reversed_at.start()], False))
            out.append((clause[reversed_at.end():], True))
        else:
            out.append((clause, False))
    return out


def declared_dependencies(paths: Collection[str], tasks: list[Any], specification: Any) -> dict[str, list[str]]:
    """{file: the other files it depends on}, from the file plan and the work orders; files with none map to []."""
    namer = _Namer(paths)
    deps: dict[str, list[str]] = {path: [] for path in paths}

    def add(user: str, used: str) -> None:
        if user != used and used not in deps[user]:
            deps[user].append(used)

    def read(subject: str, text: str) -> None:
        for clause, reverse in _clauses(text):
            for other in namer.named(clause):
                add(other, subject) if reverse else add(subject, other)

    # The file plan: an entry about one file names the files it imports from.
    for entry in getattr(specification, "file_plan", None) or []:
        subject = None
        for line in str(entry).expandtabs(4).splitlines():
            match = _PLAN_LINE.match(line)
            head = match.group("head").strip("`*:,;") if match else ""
            about = namer.named(head) if head else []
            if about:
                subject, rest = about[0], line[match.end():]
            else:
                rest = line
            if subject is not None:
                read(subject, rest)
    # The work orders: a contract or step that names only other orders' files is one these files use.
    for task in tasks:
        own = [_plain(f) for f in getattr(task, "files", None) or []]
        mine = [path for path in paths if _plain(path) in own]
        if not mine:
            continue
        for line in [*(getattr(task, "interfaces", None) or []), *(getattr(task, "steps", None) or [])]:
            named = namer.named(line)
            if not named or any(path in mine for path in named):
                continue
            for subject in mine:
                read(subject, str(line))
    return deps


def _is_foundation(path: str) -> bool:
    """Whether a file's name or folder says it holds data shapes or a store: `models/`, `noteStore.ts`, `db.rs`."""
    parts = _plain(path).split("/")
    parts[-1] = PurePosixPath(parts[-1]).stem
    words = {word.lower() for part in parts for piece in re.split(r"[._\-]+", part)
             for word in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z0-9]+", piece)}
    return bool(words & _FOUNDATION_WORDS)


def _is_entry(path: str, entrypoints: Collection[str]) -> bool:
    plain = _plain(path)
    return any(plain == e or plain.endswith("/" + e) or e.endswith("/" + plain) for e in map(_plain, entrypoints) if e)


def _reaches(graph: dict[str, list[str]], start: str, goal: str) -> bool:
    seen, stack = set(), [start]
    while stack:
        node = stack.pop()
        if node == goal:
            return True
        if node not in seen:
            seen.add(node)
            stack.extend(graph.get(node, ()))
    return False


def _ranks(graph: dict[str, list[str]]) -> dict[str, int]:
    """Each file's depth: 0 with nothing before it, else one more than the deepest it depends on. A cycle is cut."""
    rank: dict[str, int] = {}
    on_path: set[str] = set()

    def depth(node: str) -> int:
        if node in rank:
            return rank[node]
        on_path.add(node)
        deepest = -1
        for used in graph.get(node, ()):
            if used in on_path:
                continue
            deepest = max(deepest, depth(used))
        on_path.discard(node)
        rank[node] = deepest + 1
        return rank[node]

    for node in graph:
        depth(node)
    return rank


def drafting_waves(paths: list[str], tasks: list[Any], specification: Any,
                   entrypoints: Collection[str] = ()) -> Waves:
    """`paths` - the product's code files to draft, no tests - in at most `MOST_WAVES` waves, each in `paths`' order."""
    from app.analysis.file_kinds import classify_file, is_presentation

    paths = list(dict.fromkeys(paths))
    if len(paths) < FEWEST_FILES_FOR_WAVES:
        return Waves([paths] if paths else [])
    # Configuration, documents and styling hold no code another file is built against: drafted with the first wave.
    floating = [p for p in paths if classify_file(p) != "application" or is_presentation(p)]
    code = [p for p in paths if p not in floating]
    graph = {path: list(used) for path, used in declared_dependencies(code, tasks, specification).items()}
    entries = [p for p in code if _is_entry(p, entrypoints)]
    foundation = [p for p in code if p not in entries and _is_foundation(p)]
    # What a file's kind says, where nothing declared says otherwise: the entry wires everything, and the rest are
    # built on the data shapes and stores. An edge that would close a cycle with a declared one is left out.
    implied = [(entry, other) for entry in entries for other in code if other not in entries]
    implied += [(user, base) for user in code if user not in entries and user not in foundation for base in foundation]
    for user, used in implied:
        if used not in graph[user] and not _reaches(graph, used, user):
            graph[user].append(used)
    rank = _ranks(graph)
    levels = sorted(set(rank.values()))
    if len(levels) <= 1:
        return Waves([paths])
    if len(levels) <= MOST_WAVES:
        wave_of = {path: levels.index(rank[path]) for path in code}
    else:
        wave_of = {path: 0 if rank[path] == levels[0] else MOST_WAVES - 1 if rank[path] == levels[-1] else 1
                   for path in code}
    wave_of.update({path: 0 for path in floating})
    count = max(wave_of.values()) + 1
    waves = [[path for path in paths if wave_of[path] == number] for number in range(count)]
    needs = {
        path: [used for used in graph.get(path, ()) if wave_of[used] < wave_of[path]]
        for path in code
    }
    return Waves([wave for wave in waves if wave], {path: used for path, used in needs.items() if used})


__all__ = ["MOST_WAVES", "ON_BY_DEFAULT", "Waves", "declared_dependencies", "drafting_waves", "enabled"]
