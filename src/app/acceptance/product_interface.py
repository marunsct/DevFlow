"""The product's interface as the earlier sprints built it, for the writer of a later sprint's tests (PA.12, LF.1362).

Measured on one medium run: a later sprint's acceptance suite writer, one visit of 30 minutes, made 123 model calls,
118 of them `read_file` and 3 writes - the product's schemas read 21 times, a service 19, an earlier sprint's test
file 21 - with 12 summaries. Across the run the writer made 764 reads of 43 files, about half of them the product's
source, read to learn the routes, the shapes they take and give, and the earlier tests' helpers. Its memory held the
product's source, the most of which did not fit, and each summary sent it back to read.

So the harness reads them and hands them over: the lines of the product's code that declare or mount a route, each
with its handler's signature; the shapes those handlers name, as the code defines them; and the signatures of the
helpers and fixtures the earlier sprints' locked tests define. The contract and the specification's API reference
are in the same request already. The writer's memory then leaves the product's source out
(`project_memory.written_from_the_interface`). It may still read a file; it no longer needs to.

Read without a parser per language, as `app.analysis.outline` reads: a line holding a quoted path ("/...") beside a
routing word, a definition line (`project_graph._DEFINES_ELSEWHERE`), and the entries of the outline. A stack whose
routes this misses gets the contract and the shapes alone, as before plus what was found.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterable, Sequence

logger = logging.getLogger(__name__)

#: The most each part of the block takes, in characters: about 5,000 tokens in all.
MOST_ROUTE_CHARACTERS = 5_000
MOST_SHAPE_CHARACTERS = 6_000
MOST_HELPER_CHARACTERS = 4_000
#: The most of one shape's body shown, in lines.
MOST_SHAPE_LINES = 30
#: The most lines a signature is joined from, and its most characters.
MOST_SIGNATURE_LINES = 8
MOST_SIGNATURE_CHARACTERS = 260

#: A quoted path: "/", "/items", "/items/{id}", "/items/:id", "/api/v1/items/<int:id>"; and one after its method in
#: the same string, "GET /items/{id}" (KG.4: such a route was not read as one).
_A_QUOTED_PATH = re.compile(r"""["'`](?:(?:GET|POST|PUT|PATCH|DELETE)\s+)?(/[\w\-{}:<>*.\[\]/]*)["'`]""")
#: A path that names a file rather than a route.
_A_FILE = re.compile(r"\.[A-Za-z]{1,5}$")
#: The words a line that declares or mounts a route holds beside its path, in any language's spelling.
_ROUTING_WORDS = re.compile(r"get|post|put|patch|delete|route|mapping|handle|prefix|mount|endpoint|\buse\(", re.I)
_A_NAME = re.compile(r"\b[A-Z][a-z]\w*[A-Z]?\w*\b")


def _quoted_removed(line: str) -> str:
    return re.sub(r"""(["'`])(?:(?!\1).)*\1""", " ", line)


#: A line that is a comment: `# `, `//`, `/*`, `* `, `-- `. Not `#[`, which is an attribute.
_A_COMMENT = re.compile(r"^\s*(?:#\s|#$|//|/\*|\*\s|--\s)")


def declares_a_route(line: str) -> bool:
    """Whether a line of code declares or mounts a route: a quoted path beside a routing word outside its quotes."""
    if _A_COMMENT.match(line):
        return False
    paths = [found for found in _A_QUOTED_PATH.findall(line) if not _A_FILE.search(found)]
    return bool(paths) and bool(_ROUTING_WORDS.search(_quoted_removed(line)))


def _a_definition(line: str) -> re.Match[str] | None:
    from app.analysis.project_graph import _DEFINES_ELSEWHERE

    return _DEFINES_ELSEWHERE.match(line)


def _signature(lines: list[str], at: int) -> str:
    """The definition starting at `lines[at]`, joined over its lines until its parentheses close."""
    joined, depth = [], 0
    for line in lines[at:at + MOST_SIGNATURE_LINES]:
        joined.append(line.strip())
        depth += line.count("(") - line.count(")")
        if depth <= 0:
            break
    return " ".join(" ".join(joined).split())[:MOST_SIGNATURE_CHARACTERS]


def _the_product_s_code(repo_root: str | Path, files: dict[str, str]) -> dict[str, str]:
    """The product's application code outside the suite, as `review_files.under_review` accepts code."""
    from app.acceptance import suite
    from app.agents.review_files import under_review
    from app.analysis.file_kinds import classify_file

    folder = suite.relative_directory(repo_root)
    candidates = [path for path in files if not path.startswith(("docs/", "."))
                  and not (folder and path.startswith(folder + "/")) and classify_file(path) == "application"]
    return dict(under_review(repo_root, candidates))


def the_product_s_source(repo_root: str | Path, files: dict[str, str]) -> list[str]:
    """The paths of the product's own code and unit tests outside the suite: what a later sprint's suite writer's memory
    leaves out. Configuration, markup and documents stay. Never raises: []."""
    try:
        from app.acceptance import suite
        from app.analysis.file_kinds import BEHAVIOUR_SUFFIXES, classify_file

        folder = suite.relative_directory(repo_root)
        return [path for path in files if not path.startswith(("docs/", "."))
                and not (folder and path.startswith(folder + "/")) and Path(path).suffix.lower() in BEHAVIOUR_SUFFIXES
                and classify_file(path) in ("application", "test")]
    except Exception:  # noqa: BLE001 - the memory as before
        return []


def _routes(code: dict[str, str]) -> list[str]:
    """`path:line  the line, then its handler's signature` for each line of `code` that declares or mounts a route."""
    found: list[str] = []
    for path, text in code.items():
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if not declares_a_route(line):
                continue
            said = " ".join(line.split())[:MOST_SIGNATURE_CHARACTERS]
            # The handler a marker line stands above: the next definition within two lines.
            for after in range(index + 1, min(index + 3, len(lines))):
                if _a_definition(lines[after]):
                    said += "  " + _signature(lines, after)
                    break
            found.append(f"- `{path}:{index + 1}`  {said}")
    return found


def _definitions(code: dict[str, str]) -> dict[str, tuple[str, int, int, list[str]]]:
    """name -> (path, first line, last line, the lines) for each definition `code` holds, by the outline's spans."""
    from app.analysis import outline

    found: dict[str, tuple[str, int, int, list[str]]] = {}
    for path, text in code.items():
        lines = text.splitlines()
        for first, last, _ in outline.entries(path, text):
            for number in range(first, min(first + 2, last + 1)):
                match = _a_definition(lines[number - 1]) if number - 1 < len(lines) else None
                if match:
                    found.setdefault(match.group(1), (path, number, last, lines[number - 1:last]))
                    break
    return found


def _shapes(named_in: Iterable[str], definitions: dict[str, tuple[str, int, int, list[str]]]) -> list[str]:
    """The definitions of the names `named_in` holds, and of the names their bodies hold, one level on; in order."""
    shown: list[str] = []
    seen: set[str] = set()
    wanted = list(dict.fromkeys(name for text in named_in for name in _A_NAME.findall(text)))
    for depth in range(2):
        later: list[str] = []
        for name in wanted:
            if name in seen or name not in definitions:
                continue
            seen.add(name)
            path, first, last, lines = definitions[name]
            body = lines[:MOST_SHAPE_LINES]
            more = len(lines) - len(body)
            shown.append(f"`{path}:{first}-{last}`\n" + "\n".join(f"    {line.rstrip()}" for line in body)
                         + (f"\n    ... ({more} more lines)" if more > 0 else ""))
            if depth == 0:
                later.extend(_A_NAME.findall("\n".join(body[1:])))
        wanted = list(dict.fromkeys(later))
    return shown


def _helpers(repo_root: str | Path, earlier: Sequence[str], files: dict[str, str]) -> list[str]:
    """`path:line  signature` of each definition in the earlier sprints' locked files that is neither a test nor
    private (a name opening with `_`)."""
    from app.acceptance import suite
    from app.analysis import outline

    tests = {(file, name) for file, name in suite.declared_tests(repo_root)}
    found: list[str] = []
    for path in earlier:
        text = files.get(path)
        if text is None:
            try:
                text = (Path(repo_root) / path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
        lines = text.splitlines()
        for first, _last, said in outline.entries(path, text):
            if said.startswith("test: "):
                continue
            marker = said.split("  ", 1)[0] if "  " in said else ""
            at = next((n for n in range(first - 1, min(first + 1, len(lines))) if _a_definition(lines[n])), None)
            name = _a_definition(lines[at]).group(1) if at is not None else ""
            if name.startswith("_") or (path, name) in tests:
                continue
            shown = (marker + "  " if marker else "") + (_signature(lines, at) if at is not None else said)
            found.append(f"- `{path}:{first}`  {' '.join(shown.split())[:MOST_SIGNATURE_CHARACTERS]}")
    return found


def _within(entries: Sequence[str], most: int, joiner: str = "\n") -> str:
    kept: list[str] = []
    used = 0
    for entry in entries:
        if used + len(entry) + 1 > most:
            break
        kept.append(entry)
        used += len(entry) + 1
    left = len(entries) - len(kept)
    return joiner.join(kept) + (f"\n(and {left} more, not shown here)" if left else "")


def block(repo_root: str | Path, earlier: Sequence[str]) -> str:
    """The request's section on the product the earlier sprints built and their tests' helpers; "" when none is
    found. Bounded: at most the sum of the three parts' sizes. Never raises: "" ."""
    try:
        from app.agents.project_memory import current

        files = current(repo_root)
        code = _the_product_s_code(repo_root, files)
        routes = _routes(code)
        shapes = _shapes(routes, _definitions(code)) if routes else []
        helpers = _helpers(repo_root, earlier, files)
        if not routes and not helpers:
            return ""
        parts = ["--- The product as the earlier sprints built it, read by the harness from its code ---"]
        if routes:
            parts.append(
                "The lines of its code that declare or mount a route, each with its handler's signature. A route "
                "declared in a group mounted under a path is served at that path followed by its own; the contract "
                "above gives each route's full path and what it must answer:\n" + _within(routes, MOST_ROUTE_CHARACTERS))
        if shapes:
            parts.append("The shapes those handlers take and give, as its code defines them:\n"
                         + _within(shapes, MOST_SHAPE_CHARACTERS))
        if helpers:
            parts.append("The helpers and fixtures the earlier sprints' locked tests define, to import and use "
                         "as they are:\n" + _within(helpers, MOST_HELPER_CHARACTERS))
        parts.append(
            "These say how to reach the product: its paths, and the fields a request carries. What a test expects of "
            "an answer is still decided by the criteria, the brief and the contract. The product's source is not in "
            "your project memory, and you need not open it.")
        return "\n\n".join(parts) + "\n\n"
    except Exception:  # noqa: BLE001 - the request goes as it did
        logger.debug("Could not read the product's interface", exc_info=True)
        return ""


__all__ = ["MOST_HELPER_CHARACTERS", "MOST_ROUTE_CHARACTERS", "MOST_SHAPE_CHARACTERS", "block", "declares_a_route",
           "the_product_s_source"]
