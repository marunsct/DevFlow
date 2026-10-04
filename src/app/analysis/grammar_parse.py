"""Parse a source file with its language's grammar, whatever the language.

Three kinds of file were parsed at the moment they were written: Python by
`ast`, JSON by `json`, and JavaScript by `node --check`. Everything else got a
bracket count, which says so itself: it is a structure check, it cannot see a
missing comma, and it only warns.

One run is what that cost. Its `playwright.config.ts` was written one comma
short:

    testDir: 'tests'
    webServer: { ... }

The write was accepted, because nothing in the worker could parse TypeScript.
Every browser test then failed to start, three test rounds described that
three different ways, and the sprint ran out of attempts three hours later with
no stage having been told what a parser reports in a millisecond.

So this parses the rest, from three sources, by what is exact:

- **Formats the standard library reads** - TOML, YAML, XML. The parser that
  will load the file is the one asked.
- **TypeScript and JSX** - the TypeScript compiler's own parser, in
  `app.analysis.typescript_parse`, reached through `javascript_parse` beside
  `node --check`. Not here, because it needs the file's place on disk.
- **Other programming languages** - a tree-sitter grammar each, bundled with
  the package, so nothing is installed per project and nothing is fetched. The
  language is chosen from the file's name and from nothing else: no rule here
  knows what a project is built with.

A grammar is not the compiler, and which languages may be judged by one was
measured rather than assumed - every grammar was run over real projects
before it was listed, and a language is here only if its grammar reported
nothing in any file its compiler accepts:

    Java 0 of 295    Ruby 0 of 148    PHP 0 of 125
    Rust 0 of 110    Go   0 of 99     Lua 0 of 62

and these are *not* here, for what the same measurement found: TypeScript 40
of 3,573 (hence the compiler), C# 43 of 951, Kotlin 22 of 322, Dart 34 of 338,
Swift 20 of 109, C and C++ about one file in three - a preprocessor, or syntax
newer than the grammar, reads as an error. A check that refuses a correct
file costs a run more than the broken file would have, so those keep the
bracket count in `syntax_balance`, which warns and lets the write stand.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

#: The grammar for each extension. Every language here compiles or loads
#: all-or-nothing - one syntax error and no line of the file runs - and each
#: measured clean; see the module docstring.
_BY_SUFFIX: dict[str, tuple[str, ...]] = {
    ".java": ("java",), ".go": ("go",), ".rs": ("rust",),
    ".rb": ("ruby",), ".php": ("php",), ".lua": ("lua",),
}

#: TypeScript and JSX, for when no TypeScript compiler can be found. A note
#: then, never a refusal: about one real file in a hundred trips the grammar.
_WITHOUT_THE_COMPILER: dict[str, tuple[str, ...]] = {
    ".ts": ("typescript",), ".mts": ("typescript",), ".cts": ("typescript",),
    ".tsx": ("tsx",), ".jsx": ("javascript",),
}

#: Stylesheets read by their grammar rather than a brace count. Measured over
#: the 122 stored stylesheets: the CSS grammar flagged two and both were real -
#: one an unpaired brace the count also found, one `backgroundrgba(...)`, a
#: missing colon the count cannot see, which a browser answers by dropping the
#: declaration without a word. SCSS and LESS stay with the count: no stored
#: file measured the one grammar, and the other is not bundled.
_STYLESHEETS: dict[str, str] = {".css": "css"}

#: Pages, for the scripts written inside them.
_PAGES = frozenset({".html", ".htm"})

#: Data formats the standard library parses, by extension.
_DATA = {".toml": "TOML", ".yaml": "YAML", ".yml": "YAML", ".xml": "XML", ".svg": "XML"}

#: Text a template engine fills in before the file is ever parsed. A Helm
#: chart's YAML is not YAML until it is rendered, and judging it as written
#: would refuse a correct file.
_A_TEMPLATE_MARKER = re.compile(r"\{\{|\{%|<%|\$\{\{")

_NAMES = {
    "typescript": "TypeScript", "tsx": "TypeScript (TSX)", "javascript": "JavaScript",
    "php": "PHP",
}


def _suffix(relative_path: str) -> str:
    name = relative_path.replace("\\", "/").rsplit("/", 1)[-1]
    return "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""


def languages_for(relative_path: str) -> tuple[str, ...]:
    """The grammars that may read this file, by its name alone; `()` for none."""
    suffix = _suffix(relative_path)
    return _BY_SUFFIX.get(suffix) or _WITHOUT_THE_COMPILER.get(suffix, ())


@lru_cache(maxsize=None)
def _parser(language: str) -> Any | None:
    """A parser for `language`, or None when the grammar is not installed."""
    try:
        from tree_sitter_language_pack import get_parser

        return get_parser(language)  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001 - a check that cannot run says nothing
        logger.debug("No grammar available for %s", language, exc_info=True)
        return None


def is_certain(relative_path: str) -> bool:
    """Whether a failure for this file is exact enough to refuse a write over."""
    suffix = _suffix(relative_path)
    if suffix in _DATA:
        return True
    if suffix in _PAGES:
        return _parser("javascript") is not None
    languages = _BY_SUFFIX.get(suffix, ())
    return bool(languages) and all(_parser(language) is not None for language in languages)


def is_measured_not_proven(relative_path: str) -> bool:
    """Whether a refusal for this file rests on a grammar and not on its compiler.

    The standard library's parsers are the ones that load the file. A grammar
    is a measurement: none reported a correct file here, over a few hundred
    each, and that is not never. So a caller refusing on one keeps a way out.
    """
    suffix = _suffix(relative_path)
    return suffix in _BY_SUFFIX or suffix in _PAGES


def _first_fault(node: Any) -> Any | None:
    """The earliest node the grammar could not place, or a token it had to invent."""
    if not node.has_error:
        return None
    stack = [node]
    found = None
    while stack:
        current = stack.pop()
        if current.is_missing or current.type == "ERROR":
            if found is None or current.start_byte < found.start_byte:
                found = current
            continue
        stack.extend(child for child in current.children if child.has_error or child.is_missing)
    return found


def _describe(fault: Any, source: bytes) -> tuple[int, str]:
    """`(line, what is wrong there)` for one fault."""
    line = fault.start_point[0] + 1
    if fault.is_missing:
        # A token the grammar had to supply to go on. It is placed where the
        # parser noticed, which is the start of whatever came next - so the
        # line that needs it is usually the one before.
        token = fault.type
        return line, (
            f"a `{token}` is missing at or just before line {line}"
            if not token.isidentifier()
            else f"something is missing at or just before line {line} (the grammar expected {token.replace('_', ' ')})"
        )
    text = source[fault.start_byte:fault.end_byte].decode("utf-8", "replace")
    first = next((part.strip() for part in text.splitlines() if part.strip()), "")
    shown = first if len(first) <= 80 else first[:77] + "..."
    if not shown:
        return line, f"the text at line {line} does not fit the grammar"
    return line, (
        f"`{shown}` on line {line} does not fit where it is - usually a separator, "
        "bracket or keyword is missing just before it, or one too many came before"
    )


def _fault_in(language: str, source: bytes) -> tuple[int, str] | None:
    """`(line, what is wrong)` for the first thing `language`'s grammar rejects, or None."""
    parser = _parser(language)
    if parser is None:
        return None
    fault = _first_fault(parser.parse(source).root_node)
    return None if fault is None else _describe(fault, source)


def _grammar_problem(relative_path: str, content: str) -> str | None:
    suffix = _suffix(relative_path)
    source = content.encode("utf-8", "replace")
    from app.analysis.javascript_parse import _around_the_failure

    if suffix in _WITHOUT_THE_COMPILER:
        from app.analysis.typescript_parse import compiler_for

        if compiler_for(None) is not None:
            return None  # the compiler has the say; see `typescript_parse`
        (language,) = _WITHOUT_THE_COMPILER[suffix]
        found = _fault_in(language, source)
        if found is None:
            return None
        line, detail = found
        return (
            f"This file may not parse as {_NAMES.get(language, language)}: {detail}. "
            "No TypeScript compiler is installed here to confirm it, and this reading "
            "is occasionally wrong about syntax newer than it is - so the file was "
            "written. Look at that line; if it is correct as it stands, carry on."
            + _around_the_failure(str(line), content)
        )

    languages = _BY_SUFFIX.get(suffix, ())
    if not languages:
        return None
    found = None
    for language in languages:
        found = _fault_in(language, source)
        if found is None:
            return None
    line, detail = found  # type: ignore[misc]
    name = _NAMES.get(languages[-1], languages[-1].capitalize())
    return (
        f"This file does not parse as {name}: {detail}. This is the language's own "
        "grammar, not a style rule - a file with a syntax error does not compile or "
        "load, so nothing in it runs."
        + _around_the_failure(str(line), content)
    )


#: `<script ...>body</script>`, attributes and body.
_A_SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script\s*>", re.I | re.S)

#: A `type` that makes the block something other than JavaScript: JSON data,
#: an import map, a template for another engine.
_TYPE = re.compile(r"""\btype\s*=\s*["']?([^"'\s>]+)""", re.I)
_JAVASCRIPT_TYPES = frozenset({
    "module", "text/javascript", "application/javascript", "text/ecmascript",
    "application/ecmascript",
})


def _inline_script_problem(content: str) -> str | None:
    """The first script written inside this page that does not parse, or None.

    A page's own `<script>` is a file nobody parses: `node --check` reads
    `.js`, and a browser reports the error to a console no stage is looking
    at. One syntax error and the whole block is dropped - every handler in it -
    while the page still loads and looks finished.

    Only blocks that are JavaScript: no `src`, and a `type` that is absent or a
    JavaScript one. Line numbers are the page's own.
    """
    if _A_TEMPLATE_MARKER.search(content):
        return None
    from app.analysis.javascript_parse import _around_the_failure

    for block in _A_SCRIPT.finditer(content):
        attributes, body = block.group(1), block.group(2)
        if re.search(r"\bsrc\s*=", attributes, re.I) or not body.strip():
            continue
        kind = _TYPE.search(attributes)
        if kind and kind.group(1).lower() not in _JAVASCRIPT_TYPES:
            continue
        found = _fault_in("javascript", body.encode("utf-8", "replace"))
        if found is None:
            continue
        line, detail = found
        offset = content.count("\n", 0, block.start(2))
        detail = re.sub(r"\bline (\d+)", lambda m: f"line {int(m.group(1)) + offset}", detail)
        return (
            f"The script inside this page does not parse as JavaScript: {detail}. A "
            "browser drops a script block with a syntax error whole - nothing in it "
            "runs, and the page still loads as if it had."
            + _around_the_failure(str(line + offset), content)
        )
    return None


def _data_problem(kind: str, content: str) -> str | None:
    """What the standard parser for this format says is wrong, or None."""
    if _A_TEMPLATE_MARKER.search(content):
        return None
    line: int | None = None
    if kind == "TOML":
        import tomllib

        try:
            tomllib.loads(content)
            return None
        except tomllib.TOMLDecodeError as failure:
            detail = str(failure)
            at = re.search(r"at line (\d+)", detail)
            line = int(at.group(1)) if at else None
    elif kind == "YAML":
        try:
            import yaml
        except ImportError:
            return None
        try:
            # Composed, not loaded: the structure is the question, and a
            # custom tag nothing here can construct is not a syntax error.
            for _ in yaml.compose_all(content):
                pass
            return None
        except yaml.YAMLError as failure:
            mark = getattr(failure, "problem_mark", None)
            line = mark.line + 1 if mark is not None else None
            detail = " ".join(
                str(part) for part in (getattr(failure, "problem", None), getattr(failure, "context", None)) if part
            ) or str(failure).splitlines()[0]
    else:
        from xml.parsers import expat

        parser = expat.ParserCreate()
        try:
            # As text, so the declared encoding is not applied a second time
            # to content that has already been decoded.
            parser.Parse(content, True)
            return None
        except expat.ExpatError as failure:
            detail = expat.ErrorString(failure.code) or str(failure)
            # A named entity comes from a DTD this parser does not fetch, and
            # an encoding it does not carry is not a mistake in the file.
            if failure.code in (
                expat.errors.codes[expat.errors.XML_ERROR_UNDEFINED_ENTITY],
                expat.errors.codes[expat.errors.XML_ERROR_UNKNOWN_ENCODING],
                expat.errors.codes[expat.errors.XML_ERROR_INCORRECT_ENCODING],
            ):
                return None
            line = failure.lineno
    from app.analysis.javascript_parse import _around_the_failure

    where = f" at line {line}" if line else ""
    return (
        f"This is not valid {kind}{where}: {detail}. Whatever reads this file reads "
        "all of it or none of it, so one mistake loses the whole file."
        + _around_the_failure(str(line) if line else None, content)
    )


def reads_stylesheet(relative_path: str) -> bool:
    """Whether this stylesheet is read by its grammar here (else a brace count stands in)."""
    language = _STYLESHEETS.get(_suffix(relative_path))
    return language is not None and _parser(language) is not None


def stylesheet_problem(relative_path: str, content: str) -> str | None:
    """What the stylesheet's grammar rejects, or None. Never raises."""
    language = _STYLESHEETS.get(_suffix(relative_path))
    if language is None or not content.strip():
        return None
    try:
        found = _fault_in(language, content.encode("utf-8", "replace"))
    except Exception:  # noqa: BLE001 - a check that cannot run says nothing
        return None
    if found is None:
        return None
    from app.analysis.javascript_parse import _around_the_failure

    line, detail = found
    return (
        f"This stylesheet does not parse as CSS: {detail}. A browser does not refuse it - "
        "it drops the declaration or the whole rule it cannot read, without any error, so "
        "the style is silently missing. Common causes: a missing `:` or `;`, or a brace "
        "that closes nothing."
        + _around_the_failure(str(line), content)
    )


def parse_problem(relative_path: str, content: str) -> str | None:
    """What stops this file parsing in its own language, or None. Never raises.

    None also means "not checked": no grammar for this kind of file, the
    grammar package not installed, or a file a template engine has yet to
    fill in. A write must not fail because a check could not run.
    """
    if not content or not content.strip():
        return None
    try:
        suffix = _suffix(relative_path)
        if suffix in _DATA:
            return _data_problem(_DATA[suffix], content)
        if suffix in _PAGES:
            return _inline_script_problem(content)
        return _grammar_problem(relative_path, content)
    except Exception:  # noqa: BLE001 - a check that cannot run says nothing
        logger.debug("Could not parse %s", relative_path, exc_info=True)
        return None


__all__ = ["is_certain", "is_measured_not_proven", "languages_for", "parse_problem", "reads_stylesheet", "stylesheet_problem"]
