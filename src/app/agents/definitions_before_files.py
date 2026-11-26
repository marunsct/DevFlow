"""Definitions, not files, when a fixer's or a builder's files do not fit its memory (plan KG.5).

Behind `DEFINITIONS_BEFORE_FILES`, off in code until measured.

A fixer's memory holds whole first the files its failure is handled in and what they import (FX.2,
`graph.localised_fix`); a builder's sliced memory the files its work order names and what they import
(`memory_slices`). Measured: a five-file path of 12,800 tokens was handed over as whole files when the fixer needed four
functions, and where those files were larger than the memory's room a file that did not fit was only named, and read.

With the switch on, where those files together are larger than `SHARE_OF_THE_MEMORY` of the memory's budget, each is
held as:

- the definitions the request reaches whole, numbered as in the file: the handler its failure's route is answered by
  (`is answered by ... lines a-b`, FX.2's section), the definition holding each line its failure names (`path:line`),
  and each definition it names (`` `name` `` or `name(`);
- each definition those call (one hop, the code graph's `calls`, KG.3) whole while the room lasts - one in another
  file under the caller's file;
- the outline of the rest, each definition with its first and last line, to read by range.

Where they fit, the whole files as today; a ten-file product never meets it. Nothing names a language: the
definitions are the grammar's (`analysis.parsed_definitions`), the outline `analysis.outline`'s.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Iterable

from app.analysis import graph_lookups
from app.switches import is_on

logger = logging.getLogger(__name__)

NAME = "DEFINITIONS_BEFORE_FILES"
#: `DEFINITIONS_BEFORE_FILES` set to on or off overrides this.
ON_BY_DEFAULT = False
#: The most of the memory's budget the files a request is about may take before they are held as definitions; the
#: definitions held whole take at most this much too.
SHARE_OF_THE_MEMORY = 0.6
#: Said in the heading of every file held this way; the switch-firing check reads it in the request.
SAID = "held as the definitions this work reaches"
#: What the admin page says this switch does.
explanation = ("Where the files a fixer's failure is handled in (or a builder's work order names) are together larger "
               "than its memory's room, each is held as the definitions the request reaches - the route's handler, "
               "the definition at each failing line, each one named - and what those call, whole and numbered, with "
               "an outline of the rest by line. Where they fit, whole files as before.")

#: FX.2's line for a route answered: `` - `POST /x` is answered by `name` in `file`, lines a-b ``.
_ANSWERED = re.compile(r"is answered by `([^`]+)` in `([^`]+)`, lines (\d+)-(\d+)")
#: A name a request writes: in backquotes, or before an opening parenthesis.
_A_NAME = re.compile(r"`([A-Za-z_$][\w$]*(?:[.:]+[A-Za-z_$][\w$]*)*)`|\b([A-Za-z_$][\w$]*)\(")


def enabled() -> bool:
    return is_on(NAME, ON_BY_DEFAULT)


def past_the_room(files: dict[str, str], paths: Iterable[str], budget_characters: int) -> bool:
    """Whether `paths` held whole would take more than `SHARE_OF_THE_MEMORY` of a memory of `budget_characters`."""
    size = sum(len(files[path]) + len(path) + 12 for path in dict.fromkeys(paths) if path in files)
    return size > int(budget_characters * SHARE_OF_THE_MEMORY)


def _names_in(ask: str) -> set[str]:
    names: set[str] = set()
    for quoted, called in _A_NAME.findall(ask or ""):
        written = quoted or called
        names.add(re.split(r"[.:]+", written)[-1])
    return names


def _reached(graph: dict[str, Any], path: str, ask: str, product: list[str]) -> list[list[Any]]:
    """The definitions of `path` the request reaches: the handlers it names, those holding its failing lines, those it
    names; in that order, each once."""
    from app.agents.memory_slices import lines_named

    found = graph_lookups.rows(graph, path)
    chosen: list[list[Any]] = []
    for name, file, first, _last in _ANSWERED.findall(ask or ""):
        if file == path:
            chosen += [row for row in found if row[1] == name and row[2] <= int(first) <= row[3]]
    for line in lines_named(ask, path, product):
        row = graph_lookups.innermost(found, line)
        if row is not None:
            chosen.append(row)
    names = _names_in(ask)
    chosen += [row for row in found if row[1] in names]
    unique: dict[tuple[int, int, str], list[Any]] = {}
    for row in chosen:
        unique.setdefault((row[2], row[3], row[1]), row)
    return list(unique.values())


def _inside(row: list[Any], held: Iterable[list[Any]]) -> bool:
    return any(other is not row and other[2] <= row[2] and row[3] <= other[3] for other in held)


def blocks(repo_root: str | Path, files: dict[str, str], ask: str, budget_characters: int,
           paths: Iterable[str]) -> dict[str, str]:
    """{path: its memory block} for each of `paths` when, together, they are past the room (`past_the_room`) and the
    switch is on; {} otherwise. Never raises: {}."""
    paths = [path for path in dict.fromkeys(paths) if path in files]
    if not paths or not enabled() or not past_the_room(files, paths, budget_characters):
        return {}
    try:
        return _blocks(repo_root, files, ask, budget_characters, paths)
    except Exception:  # noqa: BLE001 - the memory as before
        logger.debug("Could not hold the definitions in place of the files", exc_info=True)
        return {}


def _blocks(repo_root: str | Path, files: dict[str, str], ask: str, budget_characters: int,
            paths: list[str]) -> dict[str, str]:
    from app.analysis import outline
    from app.analysis.project_graph import build

    graph = build(repo_root)
    product = [path for path in files if not path.startswith(("docs/", "."))]
    room = int(budget_characters * SHARE_OF_THE_MEMORY)
    lines = {path: files[path].splitlines() for path in files}
    #: file -> the rows held whole there; caller file -> [(callee file, row)] held under it.
    held: dict[str, list[list[Any]]] = {path: [] for path in paths}
    elsewhere: dict[str, list[tuple[str, list[Any]]]] = {path: [] for path in paths}
    used = 0

    def take(file: str, row: list[Any], under: str) -> bool:
        nonlocal used
        if file not in lines:
            return False
        kept = held.get(file) if file in held else [r for _f, r in elsewhere[under] if _f == file]
        if any(r[2] <= row[2] and row[3] <= r[3] for r in kept):
            return True  # already held, whole or inside one held
        size = sum(len(line) + 8 for line in lines[file][row[2] - 1:row[3]])
        if used + size > room:
            return False
        used += size
        if file in held:
            held[file].append(row)
        else:
            elsewhere[under].append((file, row))
        return True

    seeds = [(path, row) for path in paths for row in _reached(graph, path, ask, product)]
    for path, row in seeds:
        take(path, row, path)
    for path, row in seeds:
        for name, callee_file in graph_lookups.callees(graph, path, graph_lookups.key(row)):
            callee = graph_lookups.by_key(graph, callee_file, name)
            if callee is not None and callee_file in files:
                take(callee_file, callee, path)
    found: dict[str, str] = {}
    for path in paths:
        text_lines = lines[path]
        whole = sorted((row for row in held[path] if not _inside(row, held[path])), key=lambda r: r[2])
        parts = [f"=== {path} ({len(text_lines)} lines; {SAID}: each whole and numbered as in the file, the rest "
                 "outlined by line - read other lines by range) ==="]
        for row in whole:
            parts.append(f"[lines {row[2]}-{row[3]}] {graph_lookups.signature(text_lines, row)}\n"
                         + graph_lookups.numbered(text_lines, row[2], row[3]))
        if elsewhere[path]:
            parts.append("What those call in other files:")
            for file, row in sorted(elsewhere[path], key=lambda item: (item[0], item[1][2])):
                parts.append(f"[`{file}` lines {row[2]}-{row[3]}] {graph_lookups.signature(lines[file], row)}\n"
                             + graph_lookups.numbered(lines[file], row[2], row[3]))
        rest = [(a, b, said) for a, b, said in outline.entries(path, files[path])
                if not any(row[2] <= a and b <= row[3] for row in whole)]
        if rest:
            parts.append("The rest of the file:\n" + "\n".join(f"  {a}-{b}  {said}" for a, b, said in rest))
        found[path] = "\n".join(parts) + "\n"
    return found


def for_the_memory(repo_root: str | Path, files: dict[str, str], ask: str, budget_characters: int, *,
                   for_a_fixer: bool, localised: Iterable[str] = (), the_slice: Iterable[str] | None = None
                   ) -> dict[str, str]:
    """The blocks of a fixer's localised files, else of a builder's sliced files, when past the room; {} otherwise."""
    paths = list(localised) if for_a_fixer and localised else sorted(the_slice or ())
    return blocks(repo_root, files, ask, budget_characters, paths) if paths else {}


def effects_lines(records: Iterable[Any]) -> list[str]:
    """`loop.sh effects` (KG.5): fix stages whose memory held definitions in place of files against the others -
    reads, repeat reads and the opening's input tokens, each a median."""
    records = [r for r in records if isinstance(r, dict)]
    carried = graph_lookups.stages_carrying(records, SAID)
    stages = graph_lookups.per_stage(records)
    fixers = {stage: seen for stage, seen in stages.items() if stage.startswith("defect_fix_")}
    head = "KG.5 fix stages handed definitions, not files"
    if not carried:
        return [f"     -  {head}: not reached"]

    def described(group: dict[str, dict[str, int]]) -> str:
        return (f"reads {graph_lookups.median_of([s['reads'] for s in group.values()])}, repeat reads "
                f"{graph_lookups.median_of([s['reads'] - s['distinct'] for s in group.values()])}, opening tokens "
                f"{graph_lookups.median_of([s['opening'] for s in group.values() if s['opening']])}")

    on = {s: v for s, v in fixers.items() if s in carried}
    off = {s: v for s, v in fixers.items() if s not in carried}
    return [f"  {len(carried):>4}  {head} (medians: {described(on)}; other fix stages {described(off)})"]


__all__ = ["NAME", "ON_BY_DEFAULT", "SAID", "SHARE_OF_THE_MEMORY", "blocks", "effects_lines", "enabled",
           "explanation", "for_the_memory", "past_the_room"]
