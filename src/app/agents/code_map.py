"""A map of a seeded codebase for the stages that plan the change (plan WS.7).

A run seeded with an existing product started its intake with the brief and a
branch name: nothing said what the codebase held, so the intake and the
planning stages either planned blind or spent their opening calls listing
folders and opening files to find where things live - and a plan made blind
puts a feature beside the module that already does half of it.

The map is built from the files alone, with no model call: the languages (by
the language table's suffixes), the directories, the manifests, the entry
points (source files nothing else imports, where imports are followed), the
test locations (by the table's test-file conventions and the usual test
folders), and the main modules with the public names they define (the code
graph's definitions). Folders a tool fills or a build writes are left out
(`languages.NOT_THE_PRODUCT`, `languages.is_generated`).

Size-aware, so a large codebase costs no more context than a small one: up to
`SMALL_CODEBASE_FILES` source files, each module is listed with its names; past
that, each directory is summarised by its file count, languages and its most
imported modules. Either way the map stops at `MOST_CHARACTERS`, and says so.
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


def _graph(root: Path) -> dict[str, dict[str, list[str]]]:
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


def build(root: str | Path) -> str:
    """The map of the product under the run's pinned directory (the workspace root before one is pinned); "" for none.

    Paths are workspace-relative, as every stage's tools take them. Never raises.
    """
    try:
        return _build(Path(root).resolve())
    except Exception:  # noqa: BLE001 - no map is a request without one
        logger.debug("Could not map the codebase", exc_info=True)
        return ""


def _build(root: Path) -> str:
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
    tests = [name for name in sources if is_a_test(name)]
    modules = [name for name in sources if name not in set(tests)]
    graph = _graph(root)
    manifests = [name for name in files if is_manifest(name)]
    entry_points = sorted(
        (name for name in modules
         if name in graph and not graph[name]["imported_by"] and _followed(name) and Path(name).stem != "__init__"),
        key=lambda name: (len(Path(name).parts), name))

    out = [f"{HEADING} (nothing was changed to make it). Read a file before changing it; this says where to look.",
           f"Size: {_files(len(sources), 'source file')}, {sum(lines.values()):,} lines"
           + (f" (the walk stopped at {MOST_FILES_WALKED:,} files)" if stopped else "") + ".",
           "Languages: " + ", ".join(f"{name} {_files(count)} ({total:,} lines)" for name, (count, total)
                                     in sorted(languages.items(), key=lambda item: -item[1][0])) + "."]
    if manifests:
        out.append(f"Manifests and build files: {_listed(manifests)}.")
    if entry_points:
        out.append(f"Entry points (source files no other file imports, tests left out): {_listed(entry_points)}.")
    if tests:
        where = Counter(_directory_of(name, depth=3) for name in tests)
        out.append("Tests: " + _listed([f"{folder} ({_files(count)})" for folder, count in where.most_common()]) + ".")
    if len(sources) <= SMALL_CODEBASE_FILES:
        out.append("Modules, with the public names each defines:")
        for name in modules:
            names = _public(graph.get(name, {}).get("defines", []))
            shown = (": " + ", ".join(names[:NAMES_A_MODULE]) + (" ..." if len(names) > NAMES_A_MODULE else "")) if names else ""
            out.append(f"- {name} ({lines[name]} lines){shown}")
    else:
        out.append("Directories, by size, each with its most imported modules and the public names they define:")
        for folder, members in sorted(_by_directory(modules).items(), key=lambda item: (-len(item[1]), item[0])):
            spoken = Counter(language_of(name) for name in members)
            ranked = sorted(members, key=lambda name: (-len(graph.get(name, {}).get("imported_by", [])), name))
            parts = []
            for name in ranked[:MODULES_A_DIRECTORY]:
                names = _public(graph.get(name, {}).get("defines", []))[:4]
                parts.append(Path(name).name + (f" ({', '.join(names)})" if names else ""))
            out.append(f"- {folder} {_files(len(members))}, {', '.join(spoken)}: {'; '.join(parts)}")
    return _capped(out)


def _followed(name: str) -> bool:
    """Whether the code graph follows this file's imports, so "imported by nothing" means something."""
    from app.analysis.reachability import FAMILIES, family_of

    return family_of(name) in FAMILIES


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


def for_a_seeded_run(root: str | Path) -> str:
    """The map, for a run seeded with an existing codebase; "" for any other run."""
    from app.acceptance.regression_contract import seeded

    return build(root) if seeded(root) else ""


def with_the_map(request: dict[str, Any], root: str | Path) -> dict[str, Any]:
    """The request with the seeded codebase's map added to its last message, once; unchanged for any other run."""
    messages = request.get("messages") or []
    if not messages or not isinstance(messages[-1].get("content"), str) or HEADING in messages[-1]["content"]:
        return request
    text = for_a_seeded_run(root)
    if text:
        messages[-1]["content"] += "\n\n" + text + "\n"
    return request


__all__ = ["HEADING", "MOST_CHARACTERS", "SMALL_CODEBASE_FILES", "build", "for_a_seeded_run", "is_a_test",
           "language_of", "with_the_map"]
