"""Routes, tests and criteria as part of the code graph (plan KG.4, LF.1514; always on: it is FX.2's data).

The code graph knew a file's imports and the acceptance test files that import it, so "tested by" was true only where
a test imports the product's code. A service is tested over HTTP: its acceptance tests import nothing of it, so in a
Go, Java, Rust, Ruby or PHP notes service no file was tested by anything, and a fixer's localisation scanned every
line of the product at each fix for the routes (`localised_fix.handlers_of`), and named the file only, never the
definition that answers. A Go 1.22 route (`"GET /notes/{id}"`, the method inside the quotes) was not read as a route.

This reads, when the graph is built:

- each route of the product's code: its method, its path (with the path its enclosing definition's marker declares,
  where a container is mounted under one) and the definition that handles it - the definition a marker line stands
  above, the name a method word calls (`get(list_notes)`), or the name passed after the path - else the line itself;
- each acceptance test's requests, matched to those routes, so a route knows the criteria of the tests that request
  it and its declaring and handling files know which tests reach them;
- for a page product, each test's selectors by text, label, placeholder, title, test id or a role's name, matched to
  the product files that hold exactly that text between quotes or tags;
- each unit test's references: the definitions of the files it imports that it names. KG.3's references by name add
  the definitions a test names without importing their file (`unit_test_references` is where they join).

Nothing names a language or a framework: a route is a quoted path beside a routing word
(`product_interface.declares_a_route`), a marker is a line opening with `@`, `#[` or `[`.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Callable, Iterable

#: A route row as the graph keeps it: [method ("" for any), path, line, handler file, handler name ("" for the line
#: itself), first line, last line, criteria of the tests that request it].
METHOD, PATH, LINE, HANDLER_FILE, HANDLER, FIRST, LAST, CRITERIA = range(8)

#: A request as a runner's or a server's log prints it: `POST /api/items`, `"GET /api/items/3 HTTP/1.1"`.
_A_LOGGED_REQUEST = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(?:https?://[^/\s\"'`]+)?(/[^\s\"'`)?#]*)")
#: A request as a test's code makes it: `request.post('/api/items'`, `client.get("/api/items/3"`.
_A_REQUEST_CALL = re.compile(r"\.(get|post|put|patch|delete)\(\s*f?([`'\"])(/[^`'\"?#]*)\2", re.I)
#: A quoted path in a line of code, perhaps after its method in the same string (`"GET /notes/{id}"`).
_A_QUOTED_ROUTE = re.compile(r"""["'`](?:(GET|POST|PUT|PATCH|DELETE)\s+)?(/[\w\-{}:<>*.\[\]/$]*)["'`]""")
#: A method word outside quotes: a word of its own in any case (`post`, `@Get`), the first hump of a name
#: (`GetMapping`) or the last (`MapPost`, `HttpGet`); never the start of a name (`getHandler`).
_A_METHOD = re.compile(r"(?<![A-Za-z])(?i:get|post|put|patch|delete)(?![A-Za-z])"
                       r"|(?<![A-Za-z])(?:Get|Post|Put|Patch|Delete)(?=[A-Z])"
                       r"|(?<=[a-z])(?:Get|Post|Put|Patch|Delete)(?![a-z])")
#: A method word calling the name that handles it: `get(list_notes)`, `.post(handlers::create_note)`.
_A_METHOD_CALLING = re.compile(r"(?<![A-Za-z])(get|post|put|patch|delete)\(\s*(?:[\w]+(?:::|\.))*([A-Za-z_]\w*)\s*\)",
                               re.I)
#: The name passed right after a path: `"GET /notes", listHandler(s))`, `("/notes", GetNotes)`.
_A_NAME_AFTER = re.compile(r"^\s*,\s*(?:[A-Za-z_$][\w$]*(?:\.|::))*([A-Za-z_]\w*)\s*[,()]")
#: A marker line: an annotation, attribute or decorator.
_A_MARKER = re.compile(r"^\s*(?:@|#\[|\[)")
#: A path segment that stands for any value: `{id}`, `:id`, `<int:id>`, `[id]`, `*`, `${id}`.
_A_PLACEHOLDER = re.compile(r"^(?:\{[^}]*\}|:\w+|<[^>]*>|\[[^\]]*\]|\*+|\$\{[^}]*\})$")
#: A requested segment that is a value: a number, a long hexadecimal or dashed id.
_A_VALUE = re.compile(r"^(?:\d+|[0-9a-f]{8,}(?:-[0-9a-f]{4,})*)$", re.I)
#: The leading segments routes share, which say nothing about which handler answers.
_SHARED = re.compile(r"^(?:api|v\d+)$", re.I)
#: A path that names a file rather than a route.
_A_FILE = re.compile(r"\.[A-Za-z0-9]{1,5}$")
#: A test's selector by the text a person meets: by its text, label, placeholder, title, alternative text or test id
#: (`getByLabel('Title')`, `get_by_text("Save")`, `.contains('Done')`), and a role's accessible name
#: (`getByRole('link', { name: 'Edit' })`, `get_by_role("link", name="Edit")`).
_A_SELECTOR = re.compile(
    r"(?:get_?by_?(?:text|label|placeholder|title|alt_?text|test_?id)|\.contains)\(\s*(['\"`])([^'\"`\n]{2,80})\1", re.I)
_A_NAMED_ROLE = re.compile(
    r"get_?by_?role\(\s*(['\"`])\w+\1\s*,\s*\{?\s*name\s*[:=]\s*(['\"`])([^'\"`\n]{2,80})\2", re.I)
#: Markup files a page product renders text from, read for selectors alone.
MARKUP_SUFFIXES = (".html", ".htm")
#: The most selector texts a graph matches, and the most files one text names.
MOST_TEXTS = 300
MOST_RENDERING = 4


def segments(path: str) -> list[str]:
    """A path's segments, its query and fragment left out."""
    return [s for s in str(path or "").split("?", 1)[0].split("#", 1)[0].split("/") if s]


def requests_in(text: str) -> list[tuple[str, str]]:
    """The requests `text` records or makes, as (method, path), each once, in order."""
    found: list[tuple[str, str]] = []
    for match in _A_LOGGED_REQUEST.finditer(str(text or "")):
        found.append((match.group(1).upper(), match.group(2)))
    for match in _A_REQUEST_CALL.finditer(str(text or "")):
        found.append((match.group(1).upper(), match.group(3)))
    kept = [(method, path) for method, path in found if segments(path) and not _A_FILE.search(path)]
    return list(dict.fromkeys(kept))


def selectors_in(text: str) -> list[str]:
    """The texts `text`'s selectors look a page up by, each once, in order; none built from a value (`${...}`)."""
    found = [m.group(2) for m in _A_SELECTOR.finditer(str(text or ""))]
    found += [m.group(3) for m in _A_NAMED_ROLE.finditer(str(text or ""))]
    return list(dict.fromkeys(t for t in found if "${" not in t and "{" not in t and t.strip()))


def matches(declared: list[str], requested: list[str]) -> int:
    """How many named segments of `declared` match the end of `requested`; 0 for no match, or for a declared path
    of shared and placeholder segments only (`/api`, `/{id}`), which says nothing about its handler."""
    if not declared or len(declared) > len(requested):
        return 0
    named = 0
    for want, got in zip(declared, requested[-len(declared):]):
        if _A_PLACEHOLDER.match(want):
            continue
        if want.lower() != got.lower() or _A_VALUE.match(got):
            return 0
        if not _SHARED.match(want):
            named += 1
    return named


def best(rows: Iterable[tuple[str, list[Any]]], method: str, path: str) -> list[tuple[str, list[Any]]]:
    """The (declaring file, route row) pairs that best answer `method path`: the most named segments matched, and
    a row naming the request's own method before one naming none. A row of another method never answers."""
    requested = segments(path)
    scored = []
    for where, row in rows:
        if row[METHOD] and method and row[METHOD] != method:
            continue
        score = matches(segments(row[PATH]), requested)
        if score:
            scored.append(((score, bool(row[METHOD] and method)), where, row))
    if not scored:
        return []
    top = max(key for key, _, _ in scored)
    return [(where, row) for key, where, row in scored if key == top]


def _quoted_removed(line: str) -> str:
    return re.sub(r"""(["'`])(?:(?!\1).)*\1""", " ", line)


def _methods(line: str) -> list[str]:
    return list(dict.fromkeys(m.group(0).upper() for m in _A_METHOD.finditer(_quoted_removed(line))))


def _a_pathless_marker(line: str) -> bool:
    """A marker naming a method and no path (`@PostMapping`): a route at its container's path."""
    return bool(_A_MARKER.match(line)) and bool(_methods(line)) and not _A_QUOTED_ROUTE.search(line)


def _definition_below(definitions: list[list[Any]], number: int, lines: list[str]) -> tuple[str, int, int] | None:
    """The definition starting on line `number` (a marker's) or one of the two after it - a marker may be read as part
    of the definition it marks - as (name, first, last)."""
    def marks(d: list[Any]) -> bool:
        first = int(d[2])
        if number <= first <= number + 2:
            return True
        # A definition read from the first of its markers: every line from there to this one is a marker.
        return number - 3 <= first < number and all(_A_MARKER.match(lines[n - 1]) for n in range(first, number + 1))

    below = [d for d in definitions if marks(d)]
    if below:
        first = max(below, key=lambda d: (int(d[2]) <= number + 2, -abs(int(d[2]) - number)))
        return str(first[1]), int(first[2]), int(first[3])
    from app.analysis.project_graph import _DEFINES_ELSEWHERE

    for at in range(number - 1, min(number + 2, len(lines))):
        found = _DEFINES_ELSEWHERE.match(lines[at])
        if found:
            return found.group(1), at + 1, at + 1
    return None


def routes_of(relative: str, text: str, definitions: list[list[Any]],
              defined: Callable[[str, str], tuple[str, int, int] | None]) -> list[list[Any]]:
    """The route rows (`METHOD` .. `CRITERIA`) of one file of the product's code. `definitions`: the file's rows
    (`[kind, name, first, last, enclosing]`, KG.2); `defined(name, relative)`: where the project defines a name, as
    (file, first, last), when exactly one place does (that file first)."""
    from app.acceptance.product_interface import declares_a_route

    lines = text.splitlines()
    declared = {n: line for n, line in enumerate(lines, 1) if declares_a_route(line)}
    if not declared:
        return []
    # A route line standing above a definition that holds other routes or markers mounts them under its path.
    containers: list[tuple[int, int, int, str]] = []
    for number, line in declared.items():
        below = _definition_below(definitions, number, lines)
        paths = [p for _, p in _A_QUOTED_ROUTE.findall(line) if not _A_FILE.search(p)]
        if not (below and paths and below[2] > below[1]):
            continue
        inside = range(max(below[1], number) + 1, below[2] + 1)
        if any(n in declared or _a_pathless_marker(lines[n - 1]) for n in inside):
            containers.append((number, below[1], below[2], paths[0].rstrip("/")))

    def prefix(number: int) -> str:
        held = [c for c in containers if c[1] < number <= c[2] and c[0] != number]
        return max(held, key=lambda c: c[1])[3] if held else ""

    rows: list[list[Any]] = []

    def add(method: str, path: str, number: int, handler: tuple[str, str, int, int] | None) -> None:
        where, name, first, last = handler or (relative, "", number, number)
        rows.append([method, path, number, where, name, first, last, []])

    marked = dict(declared)
    for container in containers:
        for n in range(container[1] + 1, container[2] + 1):
            line = lines[n - 1]
            if n not in marked and _a_pathless_marker(line):
                marked[n] = line
    for number in sorted(marked):
        line = marked[number]
        quoted = [(m.group(1) or "", m.group(2), m.end()) for m in _A_QUOTED_ROUTE.finditer(line)
                  if not _A_FILE.search(m.group(2))]
        paths = [(method, prefix(number) + path.rstrip("/") if prefix(number) else path, end)
                 for method, path, end in quoted] or [("", prefix(number) or "/", len(line))]
        below = _definition_below(definitions, number, lines)
        handler = (relative, *below) if below else None
        calling = [(m.group(1).upper(), m.group(2)) for m in _A_METHOD_CALLING.finditer(_quoted_removed(line))]
        for method, path, end in paths:
            if calling and not method:
                for called_method, name in calling:
                    add(called_method, path, number, _handler_named(defined, name, relative) or handler)
                continue
            after = _A_NAME_AFTER.match(line[end:])
            named = _handler_named(defined, after.group(1), relative) if after and not handler else None
            methods = [method] if method else (_methods(line) or [""])
            for each in methods:
                add(each, path or "/", number, handler or named)
    return rows


def _handler_named(defined: Callable[[str, str], tuple[str, int, int] | None], name: str,
                   relative: str) -> tuple[str, str, int, int] | None:
    found = defined(name, relative)
    return (found[0], name, found[1], found[2]) if found else None


def _per_test(text: str, names: list[str]) -> list[tuple[int, int, list[str]]]:
    """Each test's span of `text` and the criteria its name carries; what comes before the first test belongs to
    the file (criteria [])."""
    from app.acceptance.junit import tags_in

    starts: list[tuple[int, list[str]]] = []
    at = 0
    for name in names:
        found = text.find(name, at)
        if found < 0:
            found = text.find(name)
        if found < 0:
            continue
        starts.append((found, [t for t in tags_in(name) if t.startswith("AC-")]))
        at = found + len(name)
    starts.sort(key=lambda s: s[0])
    spans = [(0, starts[0][0] if starts else len(text), [])]
    for index, (start, criteria) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else len(text)
        spans.append((start, end, criteria))
    return spans


def _a_node() -> dict[str, list[Any]]:
    return {"imports": [], "imported_by": [], "defines": [], "criteria": [], "definitions": []}


def markup_files(project: Path) -> list[Path]:
    """The project's markup files (`MARKUP_SUFFIXES`), outside the folders the graph skips."""
    from app.analysis.project_graph import _SKIPPED
    from app.stacks.languages import is_generated

    found = []
    for directory, subdirectories, files in os.walk(project):
        subdirectories[:] = [d for d in subdirectories
                             if d not in _SKIPPED and not d.startswith(".") and not is_generated(d, files)]
        found += [Path(directory) / name for name in files if name.lower().endswith(MARKUP_SUFFIXES)]
    return sorted(found)


#: A script a markup file loads: `<script type="module" src="src/main.js">`.
_A_SCRIPT = re.compile(r"""<script\b[^>]*\bsrc\s*=\s*["']([^"'?#]+)""", re.I)


def _scripts_loaded(relative: str, text: str, graph: dict[str, Any]) -> list[str]:
    """The project files a markup file's scripts load: its behaviour, where what it renders is changed."""
    import posixpath

    folder = posixpath.dirname(relative)
    found = []
    for source in _A_SCRIPT.findall(text):
        if "://" in source:
            continue
        joined = posixpath.normpath(posixpath.join(folder, source.lstrip("/")) if not source.startswith("/")
                                    else posixpath.join(relative.split("/", 1)[0] if "/" in relative else "",
                                                        source.lstrip("/")))
        if joined in graph:
            found.append(joined)
    return sorted(set(found))


def _rendered(text: str, wanted: str) -> bool:
    """Whether `text` holds `wanted` exactly as a string or between tags: `"Save"`, `>Save<`, `> Save </`."""
    return re.search(r"""(?:["'`]|>\s*)""" + re.escape(wanted) + r"""(?:["'`]|\s*<)""", text) is not None


def attach(root: Path, graph: dict[str, dict[str, Any]], text_of: Callable[[str], str | None],
           markup: Iterable[Path] = ()) -> None:
    """Fill the graph's KG.4 fields: `routes` on the product's files, `requests` and `selects` on the acceptance test
    files, `references` on the unit tests, and on each product file the tests that reach it (`tested_by`, as
    [test file, criteria]), the texts it renders for them (`renders`) and its unit tests (`unit_tests`)."""
    from app.acceptance import suite
    from app.analysis.file_kinds import classify_file

    folder = suite.relative_directory(root)

    def in_the_suite(relative: str) -> bool:
        return bool(folder) and relative.startswith(folder + "/")

    product = [rel for rel in graph if not rel.startswith(("docs/", ".")) and not in_the_suite(rel)
               and classify_file(rel) == "application"]
    where_defined: dict[str, list[tuple[str, int, int]]] = {}
    for rel, node in graph.items():
        for row in node.get("definitions") or []:
            where_defined.setdefault(str(row[1]), []).append((rel, int(row[2]), int(row[3])))

    def defined(name: str, relative: str) -> tuple[str, int, int] | None:
        places = where_defined.get(name) or []
        own = [p for p in places if p[0] == relative]
        return own[0] if own else (places[0] if len({p[0] for p in places}) == 1 else None)

    rows: list[tuple[str, list[Any]]] = []
    for rel in product:
        text = text_of(rel)
        if text is None:
            continue
        found = routes_of(rel, text, list(graph[rel].get("definitions") or []), defined)
        if found:
            graph[rel]["routes"] = found
            rows += [(rel, row) for row in found]
    reached: dict[str, dict[str, set[str]]] = {}

    def tested(relative: str, test: str, criteria: Iterable[str]) -> None:
        reached.setdefault(relative, {}).setdefault(test, set()).update(criteria)

    names: dict[str, list[str]] = {}
    for where, name in suite.declared_tests(root):
        names.setdefault(where, []).append(name)
    pages: dict[str, str] = {rel: text for rel in product if (text := text_of(rel)) is not None}
    for path in markup:
        rel = path.relative_to(root).as_posix()
        if not in_the_suite(rel) and classify_file(rel) == "application":
            try:
                pages.setdefault(rel, path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
    renders: dict[str, set[str]] = {}
    texts_matched: dict[str, list[str]] = {}
    for path in suite.suite_files(root):
        test = path.relative_to(root).as_posix()
        text = text_of(test)
        if text is None:
            continue
        requested: dict[tuple[str, str], set[str]] = {}
        selected: dict[str, set[str]] = {}
        for start, end, criteria in _per_test(text, names.get(test, [])):
            for request in requests_in(text[start:end]):
                requested.setdefault(request, set()).update(criteria)
            for wanted in selectors_in(text[start:end]):
                selected.setdefault(wanted, set()).update(criteria)
        if not requested and not selected:
            continue
        node = graph.setdefault(test, _a_node())
        if requested:
            node["requests"] = [[m, p, sorted(c)] for (m, p), c in requested.items()]
        if selected:
            node["selects"] = [[t, sorted(c)] for t, c in selected.items()]
        for (method, request_path), criteria in requested.items():
            for where, row in best(rows, method, request_path):
                row[CRITERIA] = sorted({*row[CRITERIA], *criteria})
                tested(where, test, criteria)
                tested(row[HANDLER_FILE], test, criteria)
        for wanted, criteria in list(selected.items())[:MOST_TEXTS]:
            if wanted not in texts_matched:
                texts_matched[wanted] = [rel for rel, page in pages.items() if _rendered(page, wanted)]
            for rel in texts_matched[wanted][:MOST_RENDERING]:
                renders.setdefault(rel, set()).add(wanted)
                tested(rel, test, criteria)
    for rel, said in renders.items():
        node = graph.setdefault(rel, _a_node())
        node["renders"] = sorted(said)
        if rel.lower().endswith(MARKUP_SUFFIXES) and not node["imports"]:
            node["imports"] = _scripts_loaded(rel, pages.get(rel, ""), graph)
            for target in node["imports"]:
                graph[target]["imported_by"].append(rel)
    for rel, tests in reached.items():
        if rel in graph:
            graph[rel]["tested_by"] = [[test, sorted(criteria)] for test, criteria in sorted(tests.items())]
    unit_test_references(graph, text_of, in_the_suite)


def unit_test_references(graph: dict[str, dict[str, Any]], text_of: Callable[[str], str | None],
                         in_the_suite: Callable[[str], bool]) -> None:
    """Each unit test's `references`: [file, name] for each definition of a product file it imports that it names;
    and on that file, `unit_tests`. By import only: KG.3's references by name join here for the definitions a test
    names without importing their file (a test in the same package as its code imports nothing of it)."""
    from app.analysis.file_kinds import classify_file

    for rel, node in graph.items():
        if in_the_suite(rel) or classify_file(rel) != "test":
            continue
        targets = [t for t in node.get("imports") or [] if t in graph and classify_file(t) == "application"]
        if not targets:
            continue
        text = text_of(rel) or ""
        words = set(re.findall(r"[A-Za-z_]\w*", text))
        node["references"] = [[t, name] for t in targets for name in graph[t].get("defines") or [] if name in words]
        for target in targets:
            listed = graph[target].setdefault("unit_tests", [])
            if rel not in listed:
                listed.append(rel)


def tests_of(graph: dict[str, dict[str, Any]], relative: str) -> list[tuple[str, list[str]]]:
    """The acceptance test files that reach `relative` and the criteria they carry for it: those that request its
    routes or select its text (KG.4), then those that import it."""
    node = graph.get(relative) or {}
    found: dict[str, list[str]] = {str(t): list(c) for t, c in node.get("tested_by") or []}
    for other, n in graph.items():
        if relative in (n.get("imports") or []) and n.get("criteria") and other not in found:
            found[other] = list(n["criteria"])
    return list(found.items())


def _said(row: list[Any]) -> str:
    return f"{row[METHOD]} {row[PATH]}".strip()


def served(node: dict[str, Any], most: int = 4) -> str:
    """`serves `GET /notes` (`listHandler`), ...` for a node with routes; "" for none."""
    routes = node.get("routes") or []
    if not routes:
        return ""
    shown = [f"`{_said(r)}`" + (f" (`{r[HANDLER]}`)" if r[HANDLER] else "") for r in routes[:most]]
    return "serves " + ", ".join(shown) + (f" and {len(routes) - most} more" if len(routes) > most else "")


def reached_routes(graph: dict[str, dict[str, Any]], requests: Iterable[tuple[str, str]],
                   allowed: set[str]) -> tuple[list[str], list[str]]:
    """For a fixer: the files that answer `requests` - the handlers' files, then the files declaring their routes -
    and one line per route answered, naming its handler and lines. Only files in `allowed`."""
    rows = [(rel, row) for rel, node in graph.items() if rel in allowed for row in node.get("routes") or []]
    files: list[str] = []
    said: list[str] = []
    for method, path in requests:
        for where, row in best(rows, method, path):
            handler_file = row[HANDLER_FILE] if row[HANDLER_FILE] in allowed else where
            files += [handler_file, where]
            if row[HANDLER]:
                said.append(f"- `{_said(row)}` is answered by `{row[HANDLER]}` in `{handler_file}`, "
                            f"lines {row[FIRST]}-{row[LAST]}")
            else:
                said.append(f"- `{_said(row)}` is declared in `{where}` at line {row[LINE]}")
    return list(dict.fromkeys(files)), list(dict.fromkeys(said))


def rendering(graph: dict[str, dict[str, Any]], texts: Iterable[str], allowed: set[str]) -> list[str]:
    """For a fixer of a page: the product files the graph shows rendering the texts its failure's selectors name, and
    the scripts a markup file among them loads."""
    wanted = set(texts)
    found = [rel for rel, node in graph.items() if rel in allowed and wanted & set(node.get("renders") or [])]
    loaded = [t for rel in found if rel.lower().endswith(MARKUP_SUFFIXES) for t in graph[rel].get("imports") or []]
    return list(dict.fromkeys([*found, *(t for t in loaded if t in allowed)]))


def calls_before_the_first_edit(records: Iterable[Any]) -> list[str]:
    """`loop.sh effects` (KG.4): for each fixer localised (FX.2's `fixer_localised` records), the tool calls of its
    stage before its first write, by how it was localised: median and the number that wrote nothing."""
    from statistics import median

    from app.graph.surrender_evidence import WRITING_TOOLS

    records = [r for r in records if isinstance(r, dict)]
    how = {str(r.get("stage")): str(r.get("how") or "none") for r in records if r.get("kind") == "fixer_localised"}
    if not how:
        return ["     -  KG.4 tool calls before a localised fixer's first write: not reached"]
    calls: dict[str, int] = {}
    wrote: set[str] = set()
    for r in records:
        stage = str(r.get("stage"))
        if r.get("kind") != "tool_call" or stage not in how or stage in wrote:
            continue
        if str(r.get("tool")) in WRITING_TOOLS:
            wrote.add(stage)
        else:
            calls[stage] = calls.get(stage, 0) + 1
    parts = []
    for name in sorted(set(how.values())):
        stages = [s for s, h in how.items() if h == name]
        before = [calls.get(s, 0) for s in stages if s in wrote]
        parts.append(f"{name} {len(stages)} (median {median(before) if before else '-'} calls,"
                     f" {sum(1 for s in stages if s not in wrote)} wrote nothing)")
    return [f"  {len(how):>4}  KG.4 tool calls before a localised fixer's first write, by how: " + ", ".join(parts)]


__all__ = ["CRITERIA", "FIRST", "HANDLER", "HANDLER_FILE", "LAST", "LINE", "MARKUP_SUFFIXES", "METHOD", "PATH",
           "attach", "best", "calls_before_the_first_edit", "markup_files", "matches", "reached_routes", "rendering",
           "requests_in", "routes_of", "segments", "selectors_in", "served", "tests_of", "unit_test_references"]
