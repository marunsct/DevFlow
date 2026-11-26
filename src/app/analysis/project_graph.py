"""A harness-owned code graph of the project (plan CG.1), and the slices of it requests carry (CG.2, CG.3).

Fixers and builders found a file's neighbours by reading: who imports it, what
it imports, which tests reach it. The harness reads all of that already -
imports per language family (`analysis.reachability`), definitions by the same
patterns, the acceptance suite's tests and the criteria their names carry.
This puts it in one index, `.harness/project-graph.json`,
computed from the files as they are - never model-written - and gives a request
the one-hop neighbourhood of its files at most `MOST_CHARACTERS`.

KG.2: every file a grammar reads also gets its definitions from its syntax tree
(`analysis.parsed_definitions`), and in the languages `reachability.FAMILIES`
has no row for, its imports too, through its language's resolver
(`analysis.import_resolvers`). Python and JavaScript/TypeScript keep their
family's imports and definitions as they were.

KG.3: each node also says which names it uses of which file, by name from the
same trees (`analysis.name_references`): `uses`, `used_by`, `ambiguous`, and per
definition `calls` and `called_by`. Data only; KG.5-KG.8 read it.

Two switches, because they are two measurements: `PROJECT_GRAPH_FIXES` (a fix
request gets its defect's files' neighbourhood, CG.2) and
`PROJECT_GRAPH_BUILDERS` (a work order gets its files' slice, CG.3).
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any, Iterable

from app.analysis.name_references import add_uses
from app.analysis.parsed_definitions import Parsed, loads, read, read_cached, row_for
from app.stacks.languages import BUILT_BY_NAME, NOT_THE_PRODUCT, is_generated
from app.switches import is_on

logger = logging.getLogger(__name__)

#: Characters of a neighbourhood a request carries, at most.
MOST_CHARACTERS = 1_500
#: Under `.harness/`, which no commit, digest or review diff carries: at the
#: workspace's top it was committed and led the code reviewer's capped diff.
GRAPH_FILE = ".harness/project-graph.json"
_SKIPPED = NOT_THE_PRODUCT | BUILT_BY_NAME | {"test-results", "vendor", "coverage", "playwright-report", "htmlcov"}


def fixes_enabled() -> bool:
    """CG.2: a fixer's request carries what the harness's code graph knows of the files its defect touches."""
    return is_on("PROJECT_GRAPH_FIXES", False)


def builders_enabled() -> bool:
    """CG.3: a builder's request carries the code graph's map of the files and names its work order touches."""
    return is_on("PROJECT_GRAPH_BUILDERS", False)


#: A line that defines something in a language `reachability.FAMILIES` has no
#: row for, and the name it defines: the fallback where no grammar reads the
#: file (KG.2). Its definitions alone answer `where_is`, which in a Go, Java,
#: Rust, Ruby, PHP, C# or Swift project found nothing at all and sent the agent
#: to search instead.
_DEFINES_ELSEWHERE = re.compile(
    r"^[ \t]*(?:(?:public|private|protected|internal|static|final|abstract|sealed|open|override|async|export|"
    r"default|data|partial|pub(?:\([a-z]+\))?)[ \t]+)*"
    r"(?:class|interface|struct|enum|trait|record|object|module|impl|type|def|fun|func|fn|function)[ \t]+"
    r"(?:\([^)]*\)[ \t]*)?([A-Za-z_]\w*)",
    re.M,
)
#: Source files read for their definitions alone (see `_DEFINES_ELSEWHERE`).
_ELSEWHERE_SUFFIXES = (".go", ".rs", ".java", ".kt", ".cs", ".rb", ".php", ".swift")

_LOCK = threading.Lock()
#: root -> (the source files as they were when it was built, the graph). Built
#: afresh on every `neighbourhood`, `where_is` and `who_uses` - each fix request
#: and each graph question - the graph read every source file of the project
#: each time: nothing on a ten-file product, a full read of a large codebase
#: per call.
_BUILT: dict[str, tuple[tuple[tuple[str, int, int], ...], dict[str, dict[str, list[Any]]]]] = {}


def _sources(project: Path) -> list[tuple[Path, str]]:
    """The project's source files, each with the `FAMILIES` row it is read by ("" for its definitions alone)."""
    from app.analysis.reachability import FAMILIES, family_of

    found = []
    for directory, subdirectories, files in os.walk(project):
        subdirectories[:] = [d for d in subdirectories
                             if d not in _SKIPPED and not d.startswith(".") and not is_generated(d, files)]
        for name in files:
            family = family_of(name)
            if family in FAMILIES or name.endswith(_ELSEWHERE_SUFFIXES):
                found.append((Path(directory) / name, family if family in FAMILIES else ""))
    return found


def _as_they_are(paths: Iterable[Path]) -> tuple[tuple[str, int, int], ...]:
    """Each file's path, modification time and size; a file that cannot be read is left out."""
    seen = []
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            continue
        seen.append((path.as_posix(), stat.st_mtime_ns, stat.st_size))
    return tuple(seen)


def build(root: str | Path) -> dict[str, dict[str, list[Any]]]:
    """{file: {imports, imported_by, defines, criteria, definitions, uses, used_by, ambiguous, calls, called_by}} for the
    project's source files, workspace-relative. Never raises.

    `definitions` holds `[kind, name, first line, last line, enclosing]` for each definition the file's syntax tree
    shows (KG.2; empty where no grammar reads it). The last five are the names it uses of other files' definitions
    and theirs of its, by name (KG.3, `analysis.name_references.add_uses`). The graph built last, while no source file and no acceptance test
    file has changed since; a file unchanged since it was last parsed is not parsed again.
    """
    from app.analysis.reachability import FAMILIES, _defined

    root = Path(root).resolve()
    graph: dict[str, dict[str, list[Any]]] = {}
    try:
        from app.acceptance import suite
        from app.tools.repository import pinned_project_directory

        project = root / (pinned_project_directory(root) or "")
        sources = _sources(project)
        markup = _markup(project)
        # The suite's test names give the criteria, so its files are part of
        # what the graph was built from; so are the markup files a page's
        # selectors are matched to (KG.4).
        signature = (*_as_they_are(p for p, _ in sources), *_as_they_are(suite.suite_files(root)),
                     *_as_they_are(markup))
        with _LOCK:
            held = _BUILT.get(str(root))
        if held and held[0] == signature:
            return held[1]
        seen = {path: (mtime, size) for path, mtime, size in signature}
        readings: dict[Path, Parsed] = {}
        texts: dict[Path, str] = {}
        for path, family_name in sources:
            text = texts[path] = path.read_text(encoding="utf-8", errors="replace")
            relative = path.relative_to(root).as_posix()
            mtime, size = seen.get(path.as_posix(), (0, -1))
            parsed = read_cached(path, text, mtime, size) if size >= 0 else read(path, text)
            if parsed is not None:
                readings[path] = parsed
            if family_name:
                family = FAMILIES[family_name]
                imports = sorted(p.resolve().relative_to(root).as_posix() for p in family.imports(path, text, project, {})
                                 if p.resolve().is_relative_to(root))
                defines = sorted(_defined(text, family))
            elif parsed is not None:
                imports, defines = [], sorted({d.name for d in parsed.definitions})
            else:
                imports, defines = [], sorted({m.group(1) for m in _DEFINES_ELSEWHERE.finditer(text)})
            graph[relative] = {"imports": imports, "imported_by": [], "defines": defines, "criteria": [],
                               "definitions": [d.as_row() for d in parsed.definitions] if parsed else []}
        _imports_from_the_trees(root, sources, readings, texts, graph)
        for relative, node in graph.items():
            for target in node["imports"]:
                if target in graph:
                    graph[target]["imported_by"].append(relative)
        add_uses(graph, {path.relative_to(root).as_posix(): parsed for path, parsed in readings.items()})
        _criteria_of_the_tests(root, graph)
        _routes_tests_and_pages(root, graph, texts, markup)
        try:
            written, target = json.dumps(graph, indent=1), root / GRAPH_FILE
            if not target.is_file() or target.read_text(encoding="utf-8") != written:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(written, encoding="utf-8")
        except OSError:
            pass
        with _LOCK:
            _BUILT[str(root)] = (signature, graph)
    except Exception:  # noqa: BLE001 - no graph is no neighbourhood
        logger.debug("Could not build the project graph", exc_info=True)
    return graph


def _imports_from_the_trees(root: Path, sources: list[tuple[Path, str]], readings: dict[Path, Parsed],
                            texts: dict[Path, str], graph: dict[str, dict[str, list[Any]]]) -> None:
    """KG.2: the imports of each file no `FAMILIES` row follows, from its syntax tree through its language's resolver
    (`app.analysis.import_resolvers`)."""
    from app.analysis.import_resolvers import Project, resolved

    known = Project(root, readings, texts)
    for path, family_name in sources:
        found = None if family_name or path not in readings else row_for(path)
        if found is None or not found[1].resolver:
            continue
        graph[path.relative_to(root).as_posix()]["imports"] = sorted(
            target.relative_to(root).as_posix() for target in resolved(path, found[1].resolver, known)
            if target.is_relative_to(root))


def _criteria_of_the_tests(root: Path, graph: dict[str, dict[str, list[Any]]]) -> None:
    """Each acceptance test file's criteria, from the ids its tests' names carry; and the files it imports."""
    try:
        from app.acceptance import suite
        from app.acceptance.junit import tags_in

        for where, name in suite.declared_tests(root):
            if where in graph:
                graph[where]["criteria"] = sorted({*graph[where]["criteria"], *(t for t in tags_in(name) if t.startswith("AC-"))})
    except Exception:  # noqa: BLE001
        pass


def _markup(project: Path) -> list[Path]:
    """KG.4: the project's markup files, which a page product's tests select text in."""
    from app.analysis.routes_and_tests import markup_files

    return markup_files(project)


def _routes_tests_and_pages(root: Path, graph: dict[str, dict[str, list[Any]]], texts: dict[Path, str],
                            markup: list[Path]) -> None:
    """KG.4: each route and the definition that handles it, the routes and page texts each acceptance test reaches
    and so its criteria, and what each unit test references (`app.analysis.routes_and_tests`)."""
    try:
        from app.analysis.routes_and_tests import attach

        def text_of(relative: str) -> str | None:
            path = root / relative
            if path in texts:
                return texts[path]
            try:
                return path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return None

        attach(root, graph, text_of, markup)
    except Exception:  # noqa: BLE001 - the graph without them
        logger.debug("Could not read the routes and tests into the code graph", exc_info=True)


def _tests_of(graph: dict[str, dict[str, list[Any]]], relative: str) -> list[tuple[str, list[str]]]:
    from app.analysis.routes_and_tests import tests_of

    return tests_of(graph, relative)


def _relative(files: Iterable[str]) -> list[str]:
    """`files` workspace-relative, each once, in order."""
    return list(dict.fromkeys(str(f).strip().removeprefix("./").lstrip("/") for f in files if str(f).strip()))


def _criterion_order(criterion: str) -> tuple[str, int]:
    """`AC-2` before `AC-10`."""
    kind, _, number = criterion.partition("-")
    return kind, int(number) if number.isdigit() else 0


def neighbourhood(root: str | Path, files: Iterable[str], heading: str) -> str:
    """The one-hop neighbourhood of `files`: what each defines and imports, what imports it and which tests reach it; "" when none."""
    graph = build(root)
    lines: list[str] = []
    for relative in _relative(files):
        node = graph.get(relative)
        if node is None:
            continue
        tests = _tests_of(graph, relative)
        parts = []
        if node.get("routes"):
            from app.analysis.routes_and_tests import served

            parts.append(served(node))
        if node["defines"]:
            parts.append("defines " + ", ".join(node["defines"][:8]))
        if node["imports"]:
            parts.append("imports " + ", ".join(f"`{p}`" for p in node["imports"][:6]))
        if node["imported_by"]:
            parts.append("imported by " + ", ".join(f"`{p}`" for p in node["imported_by"][:6]))
        if tests:
            criteria = sorted({c for _, said in tests for c in said}, key=_criterion_order)
            parts.append("tested by " + ", ".join(f"`{t}`" for t, _ in tests[:3]) + (f" ({', '.join(criteria[:8])})" if criteria else ""))
        if node.get("unit_tests"):
            parts.append("unit tests " + ", ".join(f"`{t}`" for t in node["unit_tests"][:3]))
        if parts:
            lines.append(f"- `{relative}`: " + "; ".join(parts))
    if not lines:
        return ""
    text = heading + "\n" + "\n".join(lines)
    return text[:MOST_CHARACTERS].rstrip() + "\n"


FIX_HEADING = "--- The files this defect touches, and their neighbours (from the harness's code graph) ---"
BUILD_HEADING = "--- Your files and their neighbours (from the harness's code graph) ---"


def _appended(request: dict[str, Any], text: str) -> dict[str, Any]:
    if text and request.get("messages") and isinstance(request["messages"][-1].get("content"), str):
        request["messages"][-1]["content"] += "\n\n" + text
    return request


def with_the_neighbourhood(request: dict[str, Any], root: str | Path, files: Iterable[str]) -> dict[str, Any]:
    """A fix request with its defect's files' neighbourhood (CG.2); as it was when off. Never raises."""
    if not fixes_enabled():
        return request
    try:
        files = _relative(files)
        text = neighbourhood(root, files, FIX_HEADING)
        noted("fix", root, files, text)
        return _appended(request, text)
    except Exception:  # noqa: BLE001
        return request


def with_the_slice(request: dict[str, Any], root: str | Path, files: Iterable[str]) -> dict[str, Any]:
    """A work order's request with its files' slice (CG.3); as it was when off. Never raises."""
    if not builders_enabled():
        return request
    try:
        files = _relative(files)
        text = neighbourhood(root, files, BUILD_HEADING)
        noted("build", root, files, text)
        return _appended(request, text)
    except Exception:  # noqa: BLE001
        return request


#: KG.1: the transcript record of what the code graph named for one request that asked it; `switch_firing` reads its
#: `message`, which says the switch acted only when the request carried a neighbourhood.
RECORD_KIND = "project_graph_reach"
#: What that record's message says for a fix request (`PROJECT_GRAPH_FIXES`) and a work order's request
#: (`PROJECT_GRAPH_BUILDERS`) that carried one.
SAID = {"fix": "A fix request carried its files' neighbours from the code graph",
        "build": "A work order's request carried its files' neighbours from the code graph"}
#: The record's language for a file with no suffix, and for a request naming no source file.
NO_LANGUAGE, NO_FILE = "other", "no source file"
_NOTED: set[tuple] = set()
_MOST_NOTED = 4_096


def _language_of(relative: str) -> str:
    """The language table's name for a file's suffix; the suffix itself where the table has no row for it."""
    from app.stacks.languages import LANGUAGES

    suffix = Path(relative).suffix.lower()
    return next((row.name for row in LANGUAGES if suffix in row.suffixes), suffix.lstrip(".") or NO_LANGUAGE)


def reach(root: str | Path, files: Iterable[str]) -> dict[str, dict[str, int]]:
    """What the code graph knows of `files`, by language: {language: {files, held, edges, tests}} - the source files
    named, those the graph holds, their import edges both ways, and the acceptance test files with criteria that
    import them; {NO_FILE: zeros} for no source file. A file of no language the table or the graph knows (a `.txt`,
    a `.json`) is not counted: it read as "txt 7 of 7 with no edge", noise beside the languages the graph reads
    (LF.1536). Never raises."""
    from app.stacks.languages import LANGUAGES

    suffixes = {suffix for row in LANGUAGES for suffix in row.suffixes}
    found: dict[str, dict[str, int]] = {}
    try:
        graph = build(root)
        for relative in _relative(files):
            if relative not in graph and Path(relative).suffix.lower() not in suffixes:
                continue
            counts = found.setdefault(_language_of(relative), {"files": 0, "held": 0, "edges": 0, "tests": 0})
            counts["files"] += 1
            node = graph.get(relative)
            if node is None:
                continue
            counts["held"] += 1
            counts["edges"] += len(node["imports"]) + len(node["imported_by"])
            counts["tests"] += len(_tests_of(graph, relative))
    except Exception:  # noqa: BLE001 - a record never fails a request
        logger.debug("Could not read what the code graph knows of a request's files", exc_info=True)
    return found or {NO_FILE: {"files": 0, "held": 0, "edges": 0, "tests": 0}}


def noted(purpose: str, root: str | Path, files: Iterable[str], text: str) -> None:
    """One `RECORD_KIND` record for a request that asked the graph (`purpose` "fix" or "build"): what the graph knows of
    its files by language, and whether the request carried a neighbourhood (`text`); once for the same stage, files and
    neighbourhood, not on each resume of a stage. Never raises."""
    try:
        from app.observability.transcript import _run_id_from_config, _stage_from_config, record

        run_id, stage, files = _run_id_from_config(), _stage_from_config(purpose), _relative(files)
        if not run_id:
            return
        key = (run_id, str(root), stage, purpose, tuple(files), hash(text))
        with _LOCK:
            if key in _NOTED:
                return
            if len(_NOTED) >= _MOST_NOTED:
                _NOTED.clear()
            _NOTED.add(key)
        record(run_id, stage, RECORD_KIND, purpose=purpose, message=SAID[purpose] if text else "",
               carried=bool(text), files=files[:12], languages=reach(root, files))
    except Exception:  # noqa: BLE001 - a record never fails a request
        logger.debug("Could not record what the code graph named", exc_info=True)


def effects_lines(records: Iterable[Any]) -> list[str]:
    """`loop.sh effects` (KG.1): per purpose, the requests that asked the code graph, how many carried a neighbourhood,
    and the share whose files it named no import edge and no test for, by language; and how each fixer was localised
    (FX.2's `fixer_localised` records: route, trace, asked or none)."""
    from collections import Counter

    records = [r for r in records if isinstance(r, dict)]
    lines = []
    for purpose, label in (("fix", "fix requests"), ("build", "work orders' requests")):
        head = f"KG.1 {label} that asked the code graph"
        asked = [r for r in records if r.get("kind") == RECORD_KIND and r.get("purpose") == purpose]
        if not asked:
            lines.append(f"     -  {head}: not reached")
            continue
        languages: Counter = Counter()
        empty: Counter = Counter()
        for r in asked:
            for language, counts in (r.get("languages") or {}).items():
                languages[language] += 1
                empty[language] += not (int((counts or {}).get("edges") or 0) or int((counts or {}).get("tests") or 0))
        by_language = ", ".join(f"{language} {empty[language]} of {n} ({100 * empty[language] // n}%)"
                                for language, n in languages.most_common())
        lines.append(f"  {len(asked):>4}  {head}, {sum(1 for r in asked if r.get('carried'))} carrying a neighbourhood;"
                     f" with no import edge and no test named, by language: {by_language}")
    localised = Counter(str(r.get("how") or "none") for r in records if r.get("kind") == "fixer_localised")
    if localised:
        lines.append(f"  {sum(localised.values()):>4}  FX.2 fixers localised, by how: "
                     + ", ".join(f"{how} {n}" for how, n in localised.most_common()))
    else:
        lines.append("     -  FX.2 fixers localised, by how: not reached")
    from app.analysis.routes_and_tests import calls_before_the_first_edit

    lines.extend(calls_before_the_first_edit(records))
    return lines


def where_is(root: str | Path, name: str) -> list[str]:
    """The files that define `name` - exactly, else by a part of the name - at most 8."""
    graph, wanted = build(root), str(name).strip()
    if not wanted:
        return []
    exact = [f for f, n in graph.items() if wanted in n["defines"]]
    return (exact or [f for f, n in graph.items() if any(wanted.lower() in d.lower() for d in n["defines"])])[:8]


def who_uses(root: str | Path, path: str) -> dict[str, Any]:
    """What imports `path`, which acceptance tests reach it and their criteria; {} for a file the graph does not hold."""
    graph, relative = build(root), str(path).strip().removeprefix("./").lstrip("/")
    node = graph.get(relative)
    if node is None:
        return {}
    tests = _tests_of(graph, relative)
    answer: dict[str, Any] = {"imported_by": node["imported_by"][:12], "tests": [t for t, _ in tests][:6],
                              "criteria": sorted({c for _, said in tests for c in said}, key=_criterion_order)[:12],
                              "defines": node["defines"][:20]}
    if node.get("routes"):
        from app.analysis.routes_and_tests import served

        answer["serves"] = served(node, most=12)
    from app.analysis.reachability import FAMILIES, family_of

    found = row_for(relative)
    if family_of(relative) not in FAMILIES and not (found and found[1].resolver and loads(relative)):
        # Its definitions are read, its imports are not: an empty
        # `imported_by` here is not "nothing uses it".
        answer["note"] = (f"The code graph does not follow imports in `{relative}`'s language, so what uses it is "
                          "not known here. Search the files for its names to find out.")
    return answer


class _Switch:
    """One switch of this module, for `provenance.SWITCHES`."""

    def __init__(self, enabled: Any) -> None:
        self.enabled = enabled
        self.ON_BY_DEFAULT = False


fixes_switch = _Switch(fixes_enabled)
builders_switch = _Switch(builders_enabled)

__all__ = ["BUILD_HEADING", "FIX_HEADING", "GRAPH_FILE", "RECORD_KIND", "SAID", "build",
           "builders_enabled", "effects_lines", "fixes_enabled", "neighbourhood", "noted", "reach", "where_is", "who_uses", "with_the_neighbourhood", "with_the_slice"]
