"""Which file's definition each name a file uses is, by name alone (plan KG.3).

The code graph knew what a file imports, not what it uses of it: a fixer could be told that the handler imports the
store, not that it calls the store's `Create`, and in a Go package, a Java package or a C# namespace, whose files use
each other without importing, it knew no edge between them at all.

This reads the names each file uses from its syntax tree (`Parsed.references`, through the patterns of its language's
row, `TreeReading.references`) and looks each up among the project's definitions, the way Aider builds its map: by
name, with no type resolution. A name is the use of one file's definition, stated as fact, only when that is the one
file it can be:

- a bare name, or one after the object itself, that the file defines is its own;
- otherwise the definers are the other files the file sees - those it imports, and those its language lets it use
  without importing (`TreeReading.sees`: the package's folder, a declared namespace, whatever its requires load) -
  and, for a method or anything else written inside a type, only where the file names that type;
- a name after a receiver that may be the object itself (`member`) counts the file's own definition among them.

When exactly one remains, the edge is a fact: the user's `uses` names that file, the definer's `used_by` names the
user, and the definitions on both sides say so (`calls`, `called_by`). When none or several remain while some project
file defines the name, it is `ambiguous`, with the files it may be: never stated as fact.

Data only, always on; plan KG.5-KG.8 read it.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from app.analysis.parsed_definitions import Parsed, row_for

#: Files an ambiguous name lists, at most.
MOST_CANDIDATES = 5
#: The keys each graph node gains.
KEYS = ("uses", "used_by", "ambiguous", "calls", "called_by")


def qualified(name: str, enclosing: str) -> str:
    """A definition's key in `calls` and `called_by`: `Type.name` for one written inside another, else its name."""
    return f"{enclosing}.{name}" if enclosing else name


def _innermost(rows: list[list[Any]], line: int) -> str:
    """The key of the innermost definition of `rows` (`[kind, name, first, last, enclosing]`) holding `line`; "" at the
    file's top."""
    best: list[Any] | None = None
    for row in rows:
        if row[2] <= line <= row[3] and (best is None or row[3] - row[2] <= best[3] - best[2]):
            best = row
    return qualified(best[1], best[4]) if best else ""


def _seen_without_importing(graph: dict[str, dict[str, Any]], readings: dict[str, Parsed]) -> dict[str, set[str]]:
    """For each file whose language lets it use files it does not import (`TreeReading.sees`), those files."""
    language = {relative: (found[0].name, found[1].sees) for relative in graph if (found := row_for(relative))}
    by_folder: dict[tuple[str, str], set[str]] = defaultdict(set)
    by_namespace: dict[tuple[str, str], set[str]] = defaultdict(set)
    for relative, (name, sees) in language.items():
        if sees == "folder":
            by_folder[(name, Path(relative).parent.as_posix())].add(relative)
        elif sees == "namespace" and relative in readings:
            for namespace in readings[relative].namespaces:
                by_namespace[(name, namespace)].add(relative)
    seen: dict[str, set[str]] = {}
    for relative, (name, sees) in language.items():
        if sees == "folder":
            seen[relative] = by_folder[(name, Path(relative).parent.as_posix())]
        elif sees == "namespace" and relative in readings:
            seen[relative] = set().union(*(by_namespace[(name, n)] for n in readings[relative].namespaces))
        elif sees == "required":
            reached, queue = set(), list(graph[relative]["imports"])
            while queue:
                current = queue.pop()
                if current not in reached and current in graph:
                    reached.add(current)
                    queue.extend(graph[current]["imports"])
            seen[relative] = reached
    return seen


def add_uses(graph: dict[str, dict[str, Any]], readings: dict[str, Parsed]) -> None:
    """Give every node of `graph` (workspace-relative path -> node with `imports`, `defines` and `definitions`) its
    `uses` {name: file}, `used_by` {name: [files]}, `ambiguous` {name: [files it may be]}, `calls` {definition:
    [[name, file], ...]} and `called_by` {definition: [[file, definition or "" at the file's top], ...]}, from the
    names each file of `readings` (workspace-relative path -> its reading) uses. Never raises."""
    for node in graph.values():
        node.update({key: {} for key in KEYS})
    try:
        _resolve(graph, readings)
    except Exception:  # noqa: BLE001 - no references is the graph as it was
        for node in graph.values():
            node.update({key: {} for key in KEYS})


def _resolve(graph: dict[str, dict[str, Any]], readings: dict[str, Parsed]) -> None:
    #: name -> [(file, the type it is written inside or "")]
    definers: dict[str, list[tuple[str, str]]] = defaultdict(list)
    rows: dict[str, list[list[Any]]] = {}
    for relative, node in graph.items():
        rows[relative] = node["definitions"] or [["", name, 0, 0, ""] for name in node["defines"]]
        for name, enclosing in dict.fromkeys((row[1], row[4]) for row in rows[relative]):
            definers[name].append((relative, enclosing))
    seen = _seen_without_importing(graph, readings)
    used_by: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    called_by: dict[str, dict[str, set[tuple[str, str]]]] = defaultdict(lambda: defaultdict(set))
    for relative, parsed in readings.items():
        node = graph.get(relative)
        if node is None or not parsed.references:
            continue
        own = {row[1] for row in rows[relative]}
        named = {name for _form, name, _line in parsed.references} | own
        visible = set(node["imports"]) | seen.get(relative, set())
        uses: dict[str, set[str]] = defaultdict(set)
        maybe: dict[str, set[str]] = defaultdict(set)
        calls: dict[str, set[tuple[str, str]]] = defaultdict(set)
        for form, name, line in parsed.references:
            found = definers.get(name)
            if not found:
                continue
            if form in ("name", "self") and name in own:
                target: str | None = relative
            else:
                likely = {f for f, enclosing in found
                          if f != relative and f in visible and (not enclosing or enclosing in named)}
                if form == "member" and name in own:
                    likely.add(relative)
                target = next(iter(likely)) if len(likely) == 1 else None
                if target is None:
                    maybe[name].update(likely or {f for f, _ in found if f != relative})
                    continue
            caller = _innermost(rows[relative], line)
            if caller:
                calls[caller].add((name, target))
            for row in rows[target]:
                if row[1] == name:
                    called_by[target][qualified(row[1], row[4])].add((relative, caller))
            if target != relative:
                uses[name].add(target)
        stated = {name: next(iter(files)) for name, files in uses.items() if len(files) == 1}
        for name, files in uses.items():
            if len(files) > 1:  # two ways of writing it named two files: not one
                maybe[name] |= files
        node["uses"] = dict(sorted(stated.items()))
        for name, target in stated.items():
            used_by[target][name].add(relative)
        node["ambiguous"] = {name: sorted(files)[:MOST_CANDIDATES]
                             for name, files in sorted(maybe.items()) if name not in stated and files}
        node["calls"] = {caller: [list(pair) for pair in sorted(pairs)] for caller, pairs in sorted(calls.items())}
    for target, names in used_by.items():
        graph[target]["used_by"] = {name: sorted(files) for name, files in sorted(names.items())}
    for target, callees in called_by.items():
        graph[target]["called_by"] = {callee: [list(pair) for pair in sorted(pairs)]
                                      for callee, pairs in sorted(callees.items())}


__all__ = ["KEYS", "MOST_CANDIDATES", "add_uses", "qualified"]
