"""Parse a JavaScript file with the parser that will actually load it.

`syntax_balance` counts brackets for the C family and says so plainly: it is a
structure check, not a parse, and it cannot see a missing semicolon or a
misplaced keyword. That is why a JavaScript file is warned about and a Python
file is refused - `ast.parse` is proof and brace counting is not.

For JavaScript there is proof available and it costs nothing. `node --check`
parses a file and reports its syntax errors without executing a line of it,
and Node is on the allowlist of every role because the products this harness
builds are mostly JavaScript. Measured in the worker container: five checks in
83 milliseconds.

One run is what this is for. `app.js` was written with a stray `try`, and
the whole of `test_round_0` was spent discovering `SyntaxError: Unexpected
token 'try'` at line 83 and routing it back as a defect - a round trip through
the test round, the triage and a defect-fix stage, for something the parser
would have named at the moment of the write.

Only `.js`, `.cjs` and `.mjs`. `.jsx`, `.ts` and `.tsx` are not JavaScript and
Node will not parse them; running this on one would report a syntax error in a
file that is perfectly correct, which is the one outcome worth avoiding.

The check runs on a temporary sibling of the real file, so `package.json`'s
`type` resolves exactly as it will for the real one - `.js` is ESM or CommonJS
depending on that, and getting it wrong would invent errors.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

#: Extensions Node parses as JavaScript.
PARSEABLE = (".js", ".cjs", ".mjs")

#: A parse that takes longer than this is not a parse. Node reports a syntax
#: error in milliseconds; a hang means something else is wrong, and a write
#: must not wait on it.
TIMEOUT_SECONDS = 10

#: `/path/to/file.mjs:83` then the offending line, a caret line, and the
#: message. The parts worth repeating are the line number and the message.
_LINE = re.compile(r"^[^\n]*?:(\d+)$", re.M)
_MESSAGE = re.compile(r"^(SyntaxError:.*)$", re.M)


def _node() -> str | None:
    return shutil.which("node")


#: Top-level `export` or `import`, which makes a file an ES module.
_ES_MODULE_SYNTAX = re.compile(r"""^\s*(?:export\b|import\s+[\w{*'"])""", re.M)


def _the_module_goal_also_rejects(node: str, path: Path, content: str) -> str | None:
    """Node's error when `content` is parsed as a module, or None.

    `node --check foo.js` parses with the script goal, and a typeless `.js`
    holding `export` is *loaded* as a module - detect-module has been on since
    Node 20.19. The two goals do not agree, and the module goal is the stricter
    one: its early errors (a duplicate export, an export of a name the module
    does not define) have no script-goal equivalent, so `--check` passes a file
    Node then refuses to load.

    Measured over every `.js` write in the stored transcripts that uses ES
    module syntax: 16 of 116 pass `node --check` and throw on import. Four
    runs paid for it - one run twice on `Duplicate export of 'init'`,
    one run on `Export 'addTask' is not defined in module`, one run
    thirteen times, and one run spent 177 events of a defect-fix stage
    on `Duplicate export of 'deleteHandler'` that this would have named at
    the write.

    Verified by loading each of them rather than by reading the flags: all
    four sampled pass `--check` and raise `SyntaxError` on a real `import()`.

    Only for `.js`. `.mjs` is already parsed with the module goal by the
    check above, and `.cjs` is never a module.
    """
    if path.suffix.lower() != ".js" or not _ES_MODULE_SYNTAX.search(content):
        return None
    if _the_manifest_says_commonjs(path):
        # Then it is not loaded as a module, and `export` here is a different
        # problem that `_the_module_type_this_declares_breaks_files_here`
        # already names. Reporting a module-goal error would be misleading.
        return None
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [node, "--input-type=module", "--check"],
            input=content,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except Exception:  # noqa: BLE001 - a check that cannot run says nothing
        return None
    return None if result.returncode == 0 else f"{result.stderr}\n{result.stdout}"


def _the_manifest_says_commonjs(path: Path) -> bool:
    """Whether the nearest `package.json` pins this directory to CommonJS."""
    import json as _json

    for directory in (path.parent, *path.parent.parents[:4]):
        manifest = directory / "package.json"
        try:
            if manifest.is_file():
                return _json.loads(manifest.read_text(encoding="utf-8")).get("type") == "commonjs"
        except (OSError, ValueError):
            return False
    return False


def parse_error(path: Path, content: str) -> str | None:
    """Node's syntax error for `content` at `path`, or None. Never raises.

    None also means "could not be checked" - no Node, a timeout, anything
    unexpected. A write must not fail because a check could not run, and this
    is the same rule every other hint in this codebase follows.
    """
    if path.suffix.lower() not in PARSEABLE:
        return None
    node = _node()
    if node is None:
        return None
    probe = path.with_name(f"{path.stem}.{uuid.uuid4().hex[:8]}.tmp{path.suffix}")
    try:
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text(content, encoding="utf-8")
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [node, "--check", str(probe)],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except Exception:  # noqa: BLE001 - a check that cannot run says nothing
        logger.debug("Could not run `node --check` on %s", path, exc_info=True)
        return None
    finally:
        try:
            probe.unlink(missing_ok=True)
        except OSError:  # pragma: no cover - the file is in our own workspace
            logger.debug("Could not remove the parse probe %s", probe)
    if result.returncode == 0:
        # The script goal accepted it. A typeless `.js` using `export` is
        # loaded as a module, whose early errors the script goal has no
        # equivalent for - see `_the_module_goal_also_rejects`.
        stricter = _the_module_goal_also_rejects(node, path, content)
        if stricter is None:
            return None
        report = stricter
    else:
        report = f"{result.stderr}\n{result.stdout}"
    message = _MESSAGE.search(report)
    line = _LINE.search(report)
    where = f" on line {line.group(1)}" if line else ""
    detail = message.group(1) if message else "the file could not be parsed"
    return (
        f"Node cannot parse this file{where}: {detail}. "
        "This is `node --check`, the same parser that loads the file, so the "
        "error is certain - it is not a guess about style."
        + _the_other_half(detail, content, path)
        + _around_the_failure(line.group(1) if line else None, content)
    )


#: Lines of context either side of the line the parser stopped on. Enough to
#: see a block boundary without reprinting the file.
CONTEXT_LINES = 4


def _around_the_failure(line: str | None, content: str) -> str:
    """The text at the line the parser named, with its neighbours, or "".

    The message named a line number and never showed the line. Measured on one
    run's `test_round_0`: an edit refused with "Node cannot parse this
    file on line 26: SyntaxError: Unexpected token '}'", sent again unchanged,
    and again, and again - four attempts, the last two answered only by the
    repeat guard. The agent had the number and not the text, and the text is
    what it was about to rewrite.

    This is the content the tool is refusing to write, not the file on disk, so
    the numbering matches the error exactly.
    """
    if line is None:
        return ""
    try:
        at = int(line)
    except ValueError:
        return ""
    lines = content.splitlines()
    if not 1 <= at <= len(lines):
        return ""
    first = max(1, at - CONTEXT_LINES)
    last = min(len(lines), at + CONTEXT_LINES)
    quoted = "\n".join(
        f"{'>' if n == at else ' '} {n:>4} | {lines[n - 1]}" for n in range(first, last + 1)
    )
    return (
        "\n\nThis is what you sent, around that line (> marks it):\n"
        + quoted
        + "\n"
    )


#: `SyntaxError: Identifier 'newTitle' has already been declared`
_DUPLICATE = re.compile(r"Identifier '([^']+)' has already been declared")

#: Where a name is bound: `const x`, `let x`, `var x`, `function x`, `class x`.
def _declarations_of(name: str, content: str) -> list[int]:
    pattern = re.compile(
        rf"^\s*(?:export\s+)?(?:async\s+)?(?:const|let|var|function|class)\s+{re.escape(name)}\b",
        re.M,
    )
    return [content.count("\n", 0, m.start()) + 1 for m in pattern.finditer(content)]


def _the_other_half(detail: str, content: str, path: Path | None = None) -> str:
    """The fact the parser's own message is missing, or "".

    Node names one end of the problem. For the errors this harness actually
    produces, the other end is what the agent needs and is cheap to find.

    Measured on one run's `specialist_backend_2`: five consecutive edits
    refused, three of them `Unexpected token '}'` and one `Identifier
    'newTitle' has already been declared`. It had the line number each time
    and still could not place the fault, because the line a parser stops on is
    not the line that is wrong.
    """
    duplicate = _DUPLICATE.search(detail)
    if duplicate:
        lines = _declarations_of(duplicate.group(1), content)
        if len(lines) > 1:
            listed = " and ".join(str(number) for number in lines[:4])
            return (
                f" `{duplicate.group(1)}` is declared on lines {listed}; remove "
                "or rename one of them."
            )
        return ""
    if "Unexpected token" in detail or "Unexpected end of input" in detail:
        # Before the bracket guess: a keyword bound as a name is certain, and
        # `Unexpected token 'delete'` is otherwise indistinguishable from a
        # misplaced brace. One run took five edits to five different line
        # numbers on one such name - see `app.analysis.reserved_words`.
        if path is not None:
            try:
                from app.analysis.reserved_words import why_the_name_cannot_work

                reserved = why_the_name_cannot_work(path.name, content)
            except Exception:  # noqa: BLE001 - a hint on a hint must not fail
                reserved = ""
            if reserved:
                return reserved
        try:
            from app.analysis.syntax_balance import _confidently_unbalanced

            found = _confidently_unbalanced(content)
        except Exception:  # noqa: BLE001 - a hint on a hint must not fail
            return ""
        if found is not None:
            return (
                f" The brackets do not balance either: {found.detail}. The block "
                f"that should contain line {found.line} is where to look - a "
                "parser reports where it gave up, not where the mistake is."
            )
    return ""


__all__ = ["PARSEABLE", "parse_error"]
