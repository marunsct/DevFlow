"""A map of a seeded codebase for the stages that plan the change (plan WS.7).

A run seeded with an existing product started its intake with the brief and a
branch name: nothing said what the codebase held, so the intake and the
planning stages either planned blind or spent their opening calls listing
folders and opening files to find where things live - and a plan made blind
puts a feature beside the module that already does half of it.

The map is built from the files alone, with no model call: the languages (by
the language table's suffixes), the directories, the manifests, the entry
points, the test locations (by the table's test-file conventions, the usual
test folders and the tests the code graph knows), and the main modules with the
public names they define (the code graph's definitions). Folders a tool fills or
a build writes are left out (`languages.NOT_THE_PRODUCT`, `languages.is_generated`).

Size-aware, so a large codebase costs no more context than a small one: up to
`SMALL_CODEBASE_FILES` source files, each module is listed with its names; past
that, the main modules are listed first and each directory is summarised by its
file count, languages and its main modules. Either way the map stops at
`MOST_CHARACTERS`, and says so.

KG.9: the entry points, test locations and main modules come from the full code
graph (`analysis.project_graph`), in every language it reads. A module is
reached when another source file imports it or uses a name it defines (KG.3), so
a Go file whose router its package's `main` calls is not an entry point though
nothing imports it; a file that defines a function `main` is one in any
language. Modules are ranked by how much of the project reaches them (the rank
Aider uses: a walk over the uses, each edge weighed by the names it carries), and
the names the request uses (the brief, and what the planning said) weigh
`NAMED_WEIGHT` times as much, so the modules a change touches come first and are
named. Before it, entry points were found in Python and JavaScript alone, and the
directory summary ranked modules by their importers, which a Go or Java codebase
showed none of.
"""
from __future__ import annotations

import logging
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from app.stacks.languages import BUILT_BY_NAME, LANGUAGES, NOT_THE_PRODUCT, TEST_FILE_PATTERNS, is_generated, is_manifest

logger = logging.getLogger(__name__)

#: Up to this many source files, every module is listed with its public names; past it, directories are summarised.
SMALL_CODEBASE_FILES = 80
#: The most characters the map takes in a request, whatever the codebase's size.
MOST_CHARACTERS = 6_000
#: The most files walked: a codebase past this is mapped from what was walked, and the map says so.
MOST_FILES_WALKED = 20_000
#: Names listed for one module, and modules for one directory in the summary.
NAMES_A_MODULE = 8
MODULES_A_DIRECTORY = 3
#: Entries listed of each kind (entry points, manifests, test locations).
MOST_LISTED = 12
#: Main modules listed past `SMALL_CODEBASE_FILES`, and modules listed as defining the request's names.
MAIN_MODULES = 12
#: How much more an edge, and a module to restart the walk at, weighs for each name the request uses (Aider's factor).
NAMED_WEIGHT = 10.0
#: The share of the walk that follows the uses, and the rounds it takes to settle.
DAMPING = 0.85
ROUNDS = 30
#: Folders tests live in by convention, in every language.
TEST_FOLDERS = frozenset({"tests", "test", "__tests__", "spec", "specs", "e2e"})
#: The heading the map opens with; a stage's request carries it once.
HEADING = "The existing codebase, mapped by the harness from its files"
_SKIPPED = NOT_THE_PRODUCT | BUILT_BY_NAME | {"test-results", "playwright-report", "coverage", "htmlcov"}
_TESTS = re.compile("|".join(f"(?:{pattern})" for pattern in TEST_FILE_PATTERNS))
_LANGUAGE_OF = {}
for _row in LANGUAGES:
    for _suffix in _row.suffixes:
        _LANGUAGE_OF.setdefault(_suffix, _row.name)


def language_of(name: str) -> str:
    """The language table's name for a file's suffix, or ""."""
    return _LANGUAGE_OF.get(Path(name).suffix.lower(), "")


def is_a_test(relative: str) -> bool:
    """A test file by its language's convention or by the folder it sits in."""
    return bool(_TESTS.search(relative)) or bool(TEST_FOLDERS & set(Path(relative).parts[:-1]))


def _lines(path: Path) -> int:
    try:
        with path.open("rb") as handle:
            return sum(1 for _ in handle)
    except OSError:
        return 0


def _walk(base: Path) -> tuple[list[str], bool]:
    """The files under `base`, relative to it, outside what a tool fills; and whether the walk stopped at its limit."""
    found: list[str] = []
    for directory, subdirectories, files in os.walk(base, followlinks=False, onerror=lambda _: None):
        subdirectories[:] = sorted(d for d in subdirectories
                                   if d not in _SKIPPED and not d.startswith(".") and not is_generated(d, files))
        here = Path(directory).relative_to(base)
        for name in sorted(files):
            found.append((here / name).as_posix())
            if len(found) >= MOST_FILES_WALKED:
                return found, True
    return found, False


def _graph(root: Path) -> dict[str, dict[str, Any]]:
    try:
        from app.analysis.project_graph import build

        return build(root)
    except Exception:  # noqa: BLE001 - a map without names is still a map
        logger.debug("Could not read the code graph for the map", exc_info=True)
        return {}


def _public(names: list[str]) -> list[str]:
    return [name for name in names if not name.startswith("_")]


def _directory_of(relative: str, depth: int = 2) -> str:
    parts = Path(relative).parts[:-1]
    return "/".join(parts[:depth]) + "/" if parts else "./"


def _files(count: int, noun: str = "file") -> str:
    return f"{count:,} {noun}{'' if count == 1 else 's'}"


def _listed(items: list[str], most: int = MOST_LISTED) -> str:
    shown = ", ".join(items[:most])
    return shown + (f" and {len(items) - most} more" if len(items) > most else "")


def build(root: str | Path, brief: str = "") -> str:
    """The map of the product under the run's pinned directory (the workspace root before one is pinned); "" for none.

    `brief` is the text the map goes with (the brief, the specification): the modules defining the names it uses rank
    higher and are named. Paths are workspace-relative, as every stage's tools take them. Never raises.
    """
    try:
        return _build(Path(root).resolve(), brief)
    except Exception:  # noqa: BLE001 - no map is a request without one
        logger.debug("Could not map the codebase", exc_info=True)
        return ""


def _build(root: Path, brief: str = "") -> str:
    from app.tools.repository import pinned_project_directory

    pinned = pinned_project_directory(root) or ""
    base = root / pinned if pinned and (root / pinned).is_dir() else root
    prefix = base.relative_to(root).as_posix()
    prefix = "" if prefix == "." else prefix + "/"
    walked, stopped = _walk(base)
    files = [prefix + relative for relative in walked]
    sources = [name for name in files if language_of(name)]
    if not sources:
        return ""
    lines = {name: _lines(root / name) for name in sources}
    languages: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for name in sources:
        languages[language_of(name)][0] += 1
        languages[language_of(name)][1] += lines[name]
    graph = _graph(root)
    tests = [name for name in sources if is_a_test(name)]
    tested = set(tests)
    modules = [name for name in sources if name not in tested]
    manifests = [name for name in files if is_manifest(name)]
    entry_points = sorted(
        (name for name in modules if name in graph and Path(name).stem != "__init__"
         and (_defines_main(graph[name]) or (_followed(name) and not _reached_by(graph, name) - tested))),
        key=lambda name: (not _defines_main(graph[name]), len(Path(name).parts), name))
    named = _named_in(brief, graph, modules)
    rank = _ranked(graph, modules, named)

    out = [f"{HEADING} (nothing was changed to make it). Read a file before changing it; this says where to look.",
           f"Size: {_files(len(sources), 'source file')}, {sum(lines.values()):,} lines"
           + (f" (the walk stopped at {MOST_FILES_WALKED:,} files)" if stopped else "") + ".",
           "Languages: " + ", ".join(f"{name} {_files(count)} ({total:,} lines)" for name, (count, total)
                                     in sorted(languages.items(), key=lambda item: -item[1][0])) + "."]
    if manifests:
        out.append(f"Manifests and build files: {_listed(manifests)}.")
    if entry_points:
        out.append("Entry points (files that define `main`, then source files no other file imports or uses; tests "
                   f"left out): {_listed(entry_points)}.")
    if tests:
        where = Counter(_directory_of(name, depth=3) for name in tests)
        out.append("Tests: " + _listed([f"{folder} ({_files(count)})" for folder, count in where.most_common()]) + ".")
    if named:
        shown = sorted(named, key=lambda name: (-rank.get(name, 0.0), name))[:MAIN_MODULES]
        out.append("Where the names this request uses are defined, most used first, with what uses them and the tests "
                   "that reach them:")
        for name in shown:
            reach = _reach_of(graph, name, named[name])
            out.append(f"- {name}: {', '.join(named[name][:NAMES_A_MODULE])}" + (f" ({reach})" if reach else ""))
    if len(sources) <= SMALL_CODEBASE_FILES:
        out.append("Modules, with the public names each defines:")
        for name in modules:
            names = _public(graph.get(name, {}).get("defines", []))
            shown = (": " + ", ".join(names[:NAMES_A_MODULE]) + (" ..." if len(names) > NAMES_A_MODULE else "")) if names else ""
            out.append(f"- {name} ({lines[name]} lines){shown}")
    else:
        main = [name for name in sorted(rank, key=lambda name: (-rank[name], name)) if _reached_by(graph, name)]
        if main:
            out.append("Main modules, by how much of the project reaches them (the names this request uses weigh "
                       "more), with the public names they define:")
            for name in main[:MAIN_MODULES]:
                names = _public(graph.get(name, {}).get("defines", []))[:4]
                out.append(f"- {name}" + (f": {', '.join(names)}" if names else ""))
        out.append("Directories, by size, each with its main modules and the public names they define:")
        for folder, members in sorted(_by_directory(modules).items(), key=lambda item: (-len(item[1]), item[0])):
            spoken = Counter(language_of(name) for name in members)
            ranked = sorted(members, key=lambda name: (-rank.get(name, 0.0), name))
            parts = []
            for name in ranked[:MODULES_A_DIRECTORY]:
                names = _public(graph.get(name, {}).get("defines", []))[:4]
                parts.append(Path(name).name + (f" ({', '.join(names)})" if names else ""))
            out.append(f"- {folder} {_files(len(members))}, {', '.join(spoken)}: {'; '.join(parts)}")
    return _capped(out)


def _reach_of(graph: dict[str, dict[str, Any]], name: str, names: list[str]) -> str:
    """What a module defining `names` reaches: the other files using those names (KG.3) and the tests that reach the
    module (KG.4: acceptance tests by its routes or text, unit tests by what they import); "" for none."""
    node = graph.get(name) or {}
    used_by = sorted({user for defined in names for user in (node.get("used_by") or {}).get(defined, ())
                      if user != name and not is_a_test(user)})
    tests = list(dict.fromkeys([str(row[0]) for row in node.get("tested_by") or []] + list(node.get("unit_tests") or [])))
    said = []
    if used_by:
        said.append("used by " + _listed(used_by, 4))
    if tests:
        said.append("tests " + _listed(tests, 4))
    return "; ".join(said)


def _defines_main(node: dict[str, Any]) -> bool:
    """Whether a file defines a function or method named `main`, where a program starts in most languages."""
    return any(len(row) > 1 and row[1] == "main" and str(row[0]) in ("function", "method")
               for row in node.get("definitions") or [])


def _reached_by(graph: dict[str, dict[str, Any]], name: str) -> set[str]:
    """The other files that import `name` or use a name it defines."""
    node = graph.get(name) or {}
    users = set(node.get("imported_by") or [])
    for files in (node.get("used_by") or {}).values():
        users.update(files)
    users.discard(name)
    return users


_WORD = re.compile(r"[A-Za-z][A-Za-z0-9]*")
_CAMEL = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z0-9]+")


def _words(text: str) -> list[str]:
    """The words of an identifier or of prose, in lower case, a trailing plural `s` dropped (`notes` is `note`)."""
    found = []
    for word in _WORD.findall(text.replace("_", " ")):
        for part in _CAMEL.findall(word):
            part = part.lower()
            found.append(part[:-1] if len(part) > 3 and part.endswith("s") and not part.endswith("ss") else part)
    return found


def _named_in(brief: str, graph: dict[str, dict[str, Any]], modules: list[str]) -> dict[str, list[str]]:
    """{module: the public names it defines that `brief` uses}: a name is used when each of its words of three letters
    or more is a word of the brief (`NoteService` by "the note service", `createNote` by "create a note")."""
    said = {word for word in _words(brief) if len(word) >= 3}
    if not said:
        return {}
    found: dict[str, list[str]] = {}
    for name in modules:
        for defined in _public((graph.get(name) or {}).get("defines") or []):
            words = [word for word in _words(defined) if len(word) >= 3]
            if words and all(word in said for word in words):
                found.setdefault(name, []).append(defined)
    return found


def _ranked(graph: dict[str, dict[str, Any]], modules: list[str], named: dict[str, list[str]]) -> dict[str, float]:
    """Each module's share of a walk over the project's uses (PageRank): from a file to the files it imports and whose
    names it uses, each edge weighed by its names (one the request uses weighs `NAMED_WEIGHT`); the walk restarts at
    any module, at one defining the request's names `NAMED_WEIGHT` times more for each."""
    if not modules:
        return {}
    held = set(modules)
    request_names = {defined for names in named.values() for defined in names}
    edges: dict[str, dict[str, float]] = {}
    for source in modules:
        node = graph.get(source) or {}
        out: dict[str, float] = defaultdict(float)
        for target in node.get("imports") or []:
            if target in held and target != source:
                out[target] += 1.0
        for used, target in (node.get("uses") or {}).items():
            if target in held and target != source:
                out[target] += NAMED_WEIGHT if used in request_names else 1.0
        if out:
            edges[source] = dict(out)
    weights = {name: 1.0 + NAMED_WEIGHT * len(named.get(name, ())) for name in modules}
    total = sum(weights.values())
    restart = {name: weight / total for name, weight in weights.items()}
    rank = dict(restart)
    for _ in range(ROUNDS):
        following = dict.fromkeys(modules, 0.0)
        stranded = 0.0
        for source, share in rank.items():
            out = edges.get(source)
            if not out:
                stranded += share
                continue
            weight = sum(out.values())
            for target, w in out.items():
                following[target] += share * w / weight
        rank = {name: (1 - DAMPING) * restart[name] + DAMPING * (following[name] + stranded * restart[name])
                for name in modules}
    return rank


def _followed(name: str) -> bool:
    """Whether the code graph follows this file's imports, so "imported by nothing" means something: by its family's
    patterns, or by its language's grammar and import resolver (KG.2)."""
    from app.analysis.parsed_definitions import loads, row_for
    from app.analysis.reachability import FAMILIES, family_of

    if family_of(name) in FAMILIES:
        return True
    found = row_for(name)
    return bool(found and found[1].resolver and loads(name))


def _by_directory(modules: list[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for name in modules:
        grouped[_directory_of(name)].append(name)
    return grouped


def _capped(lines: list[str]) -> str:
    kept: list[str] = []
    used = 0
    for index, line in enumerate(lines):
        if used + len(line) + 1 > MOST_CHARACTERS:
            kept.append(f"... {len(lines) - index} more lines left out: the map stops at {MOST_CHARACTERS:,} characters.")
            break
        kept.append(line)
        used += len(line) + 1
    return "\n".join(kept)


def for_a_seeded_run(root: str | Path, brief: str = "") -> str:
    """The map, for a run seeded with an existing codebase; "" for any other run."""
    from app.acceptance.regression_contract import seeded

    return build(root, brief) if seeded(root) else ""


def with_the_map(request: dict[str, Any], root: str | Path) -> dict[str, Any]:
    """The request with the seeded codebase's map added to its last message, once; unchanged for any other run. The
    message's own text is what the map ranks the modules by."""
    messages = request.get("messages") or []
    if not messages or not isinstance(messages[-1].get("content"), str) or HEADING in messages[-1]["content"]:
        return request
    text = for_a_seeded_run(root, messages[-1]["content"])
    if text:
        messages[-1]["content"] += "\n\n" + text + "\n"
    return request


__all__ = ["HEADING", "MOST_CHARACTERS", "SMALL_CODEBASE_FILES", "build", "for_a_seeded_run", "is_a_test",
           "language_of", "with_the_map"]
