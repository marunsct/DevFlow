"""Where a fixer's failure is handled, found before the fixer opens (plan FX.2, LF.1416; always on).

Measured on a medium run: of eight fixers shown a defect, those whose defect named its file edited within a few calls
and were summarised once or never; those shown an acceptance criterion with "Affected files: (none identified)" read
26-34 times and changed nothing. Their memory held the files the failing tests' output named - the locked suite's
test file and its helper - and what those import, while the route and service files the failing request passes
through were not held: the five files on that request's path were read 91 times in three fixers, 63 of them again.

So, before a fixer is sent, the harness finds where the failure is handled, the way the strongest repair harnesses
localise first (Agentless, AutoCodeRover):

1. the requests its failing tests made (`POST /api/register` in a log line, `request.post('/api/register')` in a
   test's code) matched to the lines of the product's code that declare a route - a quoted path beside a routing word,
   in any language (`product_interface.declares_a_route`): the handler's file;
2. the product's own files a stack trace in its evidence names (`File "x.py", line 9`, `at f (src/x.js:9:5)`);
3. where neither gives a file and the defect names none, the one cheap localisation call the rewrite path has
   (`localisation.asked`: one call without reasoning, given the failure and the project's map).

The files found and the modules they import (the harness's code graph, `.harness/project-graph.json`) are named in
the request's evidence (`HEADING`); a fixer's memory, cut to its evidence, holds them whole first, and drops the locked
suite's files its tests' output alone named (`held_whole`). Nothing names a language or a framework: a route is
whatever line holds a quoted path beside a routing word.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

logger = logging.getLogger(__name__)

#: The section of a fix request naming where its failure is handled.
HEADING = "--- Where the failure is handled (found by the harness) ---"
#: The most files named: the handlers and what they import.
MOST_FILES = 6
#: The transcript record of one fixer's localisation.
RECORD_KIND = "fixer_localised"

#: A request as a runner's or a server's log prints it: `POST /api/items`, `"GET /api/items/3 HTTP/1.1"`.
_A_LOGGED_REQUEST = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(?:https?://[^/\s\"'`]+)?(/[^\s\"'`)?#]*)")
#: A request as a test's code makes it: `request.post('/api/items'`, `client.get("/api/items/3"`.
_A_REQUEST_CALL = re.compile(r"\.(get|post|put|patch|delete)\(\s*f?([`'\"])(/[^`'\"?#]*)\2", re.I)
#: A quoted path in a line of code.
_A_QUOTED_PATH = re.compile(r"""["'`](/[\w\-{}:<>*.\[\]/$]*)["'`]""")
#: A method word in a line of code, outside its quotes.
_A_METHOD = re.compile(r"(?<![A-Za-z])(get|post|put|patch|delete)(?![a-z])", re.I)
#: A path segment that stands for any value: `{id}`, `:id`, `<int:id>`, `[id]`, `*`, `${id}`.
_A_PLACEHOLDER = re.compile(r"^(?:\{[^}]*\}|:\w+|<[^>]*>|\[[^\]]*\]|\*+|\$\{[^}]*\})$")
#: A requested segment that is a value: a number, a long hexadecimal or dashed id.
_A_VALUE = re.compile(r"^(?:\d+|[0-9a-f]{8,}(?:-[0-9a-f]{4,})*)$", re.I)
#: The leading segments routes share, which say nothing about which handler answers.
_SHARED = re.compile(r"^(?:api|v\d+)$", re.I)
#: A path that names a file rather than a route.
_A_FILE = re.compile(r"\.[A-Za-z0-9]{1,5}$")
#: A stack frame: Python's `File "path", line 9`, and `path:line` as every other runtime prints it.
_A_PYTHON_FRAME = re.compile(r"File \"([^\"]+)\", line (\d+)")
_A_FRAME = re.compile(r"([\w.\\/-]+\.[A-Za-z]{1,5}):(\d+)")


@dataclass
class Localised:
    """Where a failure is handled: the files found and how (`route`, `trace`, `asked`; "" for none), and the modules
    they import."""

    found: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    how: str = ""
    requests: list[str] = field(default_factory=list)

    @property
    def files(self) -> list[str]:
        return list(dict.fromkeys([*self.found, *self.imports]))[:MOST_FILES]


def _segments(path: str) -> list[str]:
    return [s for s in str(path or "").split("?", 1)[0].split("#", 1)[0].split("/") if s]


def requests_in(text: str) -> list[tuple[str, str]]:
    """The requests `text` records or makes, as (method, path), each once, in order; method "" when only the code's
    call is known by a word the runner does not print."""
    found: list[tuple[str, str]] = []
    for match in _A_LOGGED_REQUEST.finditer(str(text or "")):
        found.append((match.group(1).upper(), match.group(2)))
    for match in _A_REQUEST_CALL.finditer(str(text or "")):
        found.append((match.group(1).upper(), match.group(3)))
    kept = [(method, path) for method, path in found if _segments(path) and not _A_FILE.search(path)]
    return list(dict.fromkeys(kept))


def _quoted_removed(line: str) -> str:
    return re.sub(r"""(["'`])(?:(?!\1).)*\1""", " ", line)


def _matches(declared: list[str], requested: list[str]) -> int:
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


def handlers_of(code: dict[str, str], requests: Iterable[tuple[str, str]]) -> list[str]:
    """The files of `code` (path -> text) that declare the route each request reaches: per request the best
    matches, those whose line names the request's own method before those whose line names none."""
    from app.acceptance.product_interface import declares_a_route

    declared: list[tuple[str, list[str], str]] = []
    for path, text in code.items():
        for line in str(text).splitlines():
            if not declares_a_route(line):
                continue
            methods = {m.upper() for m in _A_METHOD.findall(_quoted_removed(line))}
            for quoted in _A_QUOTED_PATH.findall(line):
                if not _A_FILE.search(quoted):
                    declared.append((path, _segments(quoted), "|".join(sorted(methods))))
    found: list[str] = []
    for method, requested_path in requests:
        requested = _segments(requested_path)
        scored = []
        for path, segments, methods in declared:
            if methods and method and method not in methods.split("|"):
                continue
            score = _matches(segments, requested)
            if score:
                scored.append(((score, bool(methods and method)), path))
        if scored:
            best = max(key for key, _ in scored)
            found += [path for key, path in scored if key == best]
    return list(dict.fromkeys(found))


def frames_in(text: str, code: Iterable[str]) -> list[str]:
    """The files of `code` that a stack trace in `text` names, in the order named."""
    paths = list(code)
    named = [m.group(1) for m in _A_PYTHON_FRAME.finditer(str(text or ""))]
    named += [m.group(1) for m in _A_FRAME.finditer(str(text or ""))]
    found: list[str] = []
    for frame in named:
        frame = frame.replace("\\", "/").lstrip("./")
        if "/" not in frame:
            # A bare file name names a file only where one file has it.
            alike = [path for path in paths if path.rsplit("/", 1)[-1] == frame]
            found += alike if len(alike) == 1 else []
            continue
        found += [path for path in paths if frame == path or frame.endswith("/" + path) or path.endswith("/" + frame)]
    return list(dict.fromkeys(found))


def _the_suite_s(repo_root: str | Path) -> str:
    try:
        from app.acceptance import suite

        return suite.relative_directory(repo_root)
    except Exception:  # noqa: BLE001 - no suite known
        return ""


def the_product_s_code(repo_root: str | Path, files: dict[str, str] | None = None) -> dict[str, str]:
    """The product's own application code: not its documents, tests, the locked suite or the harness's files."""
    from app.analysis.file_kinds import classify_file

    if files is None:
        from app.agents.project_memory import current

        files = current(repo_root)
    suite = _the_suite_s(repo_root)
    return {path: text for path, text in files.items()
            if not path.startswith(("docs/", ".")) and not (suite and path.startswith(suite + "/"))
            and classify_file(path) == "application"}


def _imports_of(repo_root: str | Path, paths: list[str], code: dict[str, str]) -> list[str]:
    from app.agents.memory_slices import imports_of

    return sorted((imports_of(repo_root, paths) & set(code)) - set(paths))


def where(repo_root: str | Path, evidence: str, *, named: Iterable[str] = (), defect: Any = None, model: Any = None,
          ask: bool = False) -> Localised:
    """Where the failure `evidence` describes is handled. `named`: the defect's own files - when it names any and
    neither a route nor a frame is found, nothing is asked. `ask`: whether the one localisation call may be made
    (`model` its model). Never raises: nothing found."""
    try:
        code = the_product_s_code(repo_root)
        if not code:
            return Localised()
        requests = requests_in(evidence)
        found, how = handlers_of(code, requests), "route"
        frames = frames_in(evidence, code)
        if frames:
            found, how = list(dict.fromkeys([*frames, *found])), ("trace" if not found else "trace and route")
        if not found and ask and model is not None and not [f for f in named if str(f).strip()]:
            from app.graph.localisation import asked

            found, how = asked(defect, evidence, repo_root, model, lambda path: path in code), "asked"
        if not found:
            return Localised(requests=[f"{m} {p}".strip() for m, p in requests])
        found = found[:MOST_FILES]
        return Localised(found=found, imports=_imports_of(repo_root, found, code), how=how,
                         requests=[f"{m} {p}".strip() for m, p in requests])
    except Exception:  # noqa: BLE001 - the request as before
        logger.debug("Could not localise a fixer's failure", exc_info=True)
        return Localised()


def section(found: Localised) -> str:
    """The section of a fix request naming where its failure is handled; "" when nothing was found."""
    if not found.found:
        return ""
    reached = (" reached by " + ", ".join(f"`{r}`" for r in found.requests[:3])) if found.how.endswith("route") else ""
    by = {"route": f"the route{reached}", "trace": "the stack trace", "trace and route": f"the stack trace and the route"
          f"{reached}", "asked": "a reading of the failure against the project's map"}.get(found.how, found.how)
    lines = [f"\n{HEADING}", f"Found from {by}:"]
    lines += [f"- `{path}`" for path in found.found]
    if found.imports:
        lines.append("and what those import:")
        lines += [f"- `{path}`" for path in found.imports if path in found.files]
    lines.append("Start from these files: the cause is in them or in what they call.")
    return "\n".join(lines) + "\n"


_A_LISTED = re.compile(r"^- `([^`]+)`$", re.M)


def files_in(opening: str) -> tuple[str, ...]:
    """The files the `HEADING` section of a request names, in order; () for a request without it."""
    text = str(opening or "")
    at = text.find(HEADING)
    if at < 0:
        return ()
    rest = text[at + len(HEADING):]
    end = re.search(r"^--- ", rest, re.M)
    return tuple(_A_LISTED.findall(rest[:end.start()] if end else rest))


def held_whole(repo_root: str | Path, the_slice: set[str] | None, files: dict[str, str],
               localised: Iterable[str]) -> set[str] | None:
    """A sliced fixer memory's files held whole once its failure is localised: the files found and what they import,
    with the rest of `the_slice` less the locked suite's files (named by its tests' output, not on the failure's path)
    - those stay named, to read when needed. `the_slice` as it is when nothing was localised."""
    found = [path for path in localised if path in files]
    if not found:
        return the_slice
    suite = _the_suite_s(repo_root)
    rest = {path for path in (the_slice or set()) if not (suite and path.startswith(suite + "/"))}
    return set(found) | rest


#: The most of a fixer's target its memory keeps room for, past the least every fixer's keeps, to hold where its
#: failure is handled: the standing sections that do not bear on the defect make way for those files first.
MOST_SHARE_HELD = 0.6


def room_for(repo_root: str | Path, opening: str, target: int) -> int:
    """The characters a fixer's memory keeps room for to hold the files its request names as where the failure is
    handled, at most `MOST_SHARE_HELD` of `target`; 0 when it names none. Never raises."""
    try:
        listed = files_in(opening)
        if not listed:
            return 0
        from app.agents.project_memory import current

        files = current(repo_root)
        size = sum(len(files[path]) + len(path) + 12 for path in listed if path in files)
        return min(int(target * MOST_SHARE_HELD), size)
    except Exception:  # noqa: BLE001 - the least room, as before
        return 0


def noted(stage: str, found: Localised, defect: Any = None) -> None:
    """One `fixer_localised` record: how the failure was localised and the files, or that nothing was. Never raises."""
    try:
        from app.observability.transcript import _run_id_from_config, record

        record(_run_id_from_config(), stage, RECORD_KIND, how=found.how or "none", files=found.files,
               requests=found.requests[:5],
               named=list(getattr(defect, "affected_files", None) or [])[:5])
    except Exception:  # noqa: BLE001 - a record never fails a request
        logger.debug("Could not record a fixer's localisation", exc_info=True)


__all__ = ["HEADING", "Localised", "MOST_FILES", "MOST_SHARE_HELD", "RECORD_KIND", "files_in", "frames_in", "handlers_of",
           "held_whole", "noted", "requests_in", "room_for", "section", "the_product_s_code", "where"]
