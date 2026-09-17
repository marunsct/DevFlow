"""Catch a structurally broken source file at the moment it is written.

run-e37a2bd8 lost a whole sprint to one edit. `confirmDeletePrompt` had its
`return new Promise((resolve) => {` removed and its closing `});` left behind:

    export function confirmDeletePrompt(id, simulate = false) {
      if (simulate) return Promise.resolve(true);

        const modal = document.createElement('div');
        ...
      });     <- closes a callback that was never opened
    }

The write was accepted. The break surfaced later as a failing test, reported as
"Syntax error in app.mjs at line 206", and three remediation attempts edited
around line 206 - which is where the parser gave up, not where the mistake was.
The sprint exhausted its attempts and the run failed with the real fault
untouched.

Everything needed to catch it existed at the moment of the write: the file, and
the fact that `)` closed nothing. A specialist told that at the instant it
saved the file is looking at the edit it just made; one told two stages later
is looking at a stack trace.

Two checkers, by what can be known exactly:

- **Python** is parsed with `ast`, which is the real grammar. A failure there
  is certain, so it is worth refusing over.
- **C-family** braces are counted, which is a structure check and not a parse.
  It cannot see a missing semicolon or a bad keyword, and it is deliberately
  conservative about what it does see - see `_confidently_unbalanced`.

Neither is a linter. The aim is the one failure that is cheap to detect,
impossible for the model to diagnose afterwards, and fatal to a run.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass

#: Extensions whose brackets balance the C way.
_BRACED = frozenset({".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".java", ".c",
                     ".h", ".cpp", ".cs", ".go", ".rs", ".php", ".swift", ".kt"})

_OPEN = {"(": ")", "[": "]", "{": "}"}
_CLOSE = {")": "(", "]": "[", "}": "{"}


@dataclass(frozen=True)
class Imbalance:
    """One structural problem, and where to look for it."""

    line: int
    detail: str


def _scan(text: str, *, regex_opaque: bool) -> Imbalance | None:
    """First bracket problem in `text`, ignoring comments and string literals.

    `regex_opaque` skips anything that could be a regular expression literal.
    Telling `/` as division from `/` as a regex needs a parser, so the caller
    runs this both ways and believes only what both agree on.
    """
    stack: list[tuple[str, int]] = []
    line = 1
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        nxt = text[index + 1] if index + 1 < length else ""

        if char == "\n":
            line += 1
            index += 1
            continue
        if char == "/" and nxt == "/":
            while index < length and text[index] != "\n":
                index += 1
            continue
        if char == "/" and nxt == "*":
            index += 2
            while index < length - 1 and not (text[index] == "*" and text[index + 1] == "/"):
                if text[index] == "\n":
                    line += 1
                index += 1
            index += 2
            continue
        if regex_opaque and char == "/":
            # Everything to the next unescaped `/` on this line, or nothing.
            probe = index + 1
            while probe < length and text[probe] not in "\n":
                if text[probe] == "\\":
                    probe += 2
                    continue
                if text[probe] == "/":
                    index = probe + 1
                    break
                probe += 1
            else:
                index += 1
                continue
            if index <= probe:
                continue
        if char in "\"'`":
            quote = char
            index += 1
            while index < length:
                if text[index] == "\\":
                    index += 2
                    continue
                if text[index] == "\n":
                    line += 1
                if text[index] == quote:
                    index += 1
                    break
                index += 1
            continue
        if char in _OPEN:
            stack.append((char, line))
        elif char in _CLOSE:
            if not stack:
                return Imbalance(
                    line,
                    f"a '{char}' on line {line} closes something that was never opened",
                )
            opened, opened_line = stack.pop()
            if _OPEN[opened] != char:
                return Imbalance(
                    line,
                    f"a '{char}' on line {line} does not match the '{opened}' "
                    f"opened on line {opened_line}",
                )
        index += 1

    if stack:
        opened, opened_line = stack[-1]
        return Imbalance(
            opened_line,
            f"the '{opened}' opened on line {opened_line} is never closed",
        )
    return None


def _confidently_unbalanced(text: str) -> Imbalance | None:
    """A bracket problem both passes agree on, or None.

    A regular-expression literal can hold unmatched brackets - `/[)]/` is valid
    and a naive count reads it as a stray closer. Running the scan twice and
    believing only what survives both means a regex can cost a missed break but
    never a false accusation, which is the right way round for something that
    refuses a write.
    """
    plain = _scan(text, regex_opaque=False)
    if plain is None:
        return None
    guarded = _scan(text, regex_opaque=True)
    if guarded is None:
        return None
    return plain


#: What Node's own modules actually export by name. Fixed, documented, and the
#: thing a model guesses at most often - `assert` is the *default* export of
#: `node:assert`, not a named one, and `node:test` does not export it at all.
#:
#: run-82e1dbdb wrote `import { assert } from 'node:test'` and
#: `import { assert } from 'node:assert'` more than ten times. Each one is
#: valid-looking, parses cleanly, and fails only when the test runs - so the
#: sprint spent all three remediation attempts on it and the run ended with the
#: defects still open. Nine of that run's twenty-six tool failures were this.
_NODE_NAMED_EXPORTS: dict[str, frozenset[str]] = {
    "node:test": frozenset({
        "test", "describe", "it", "suite", "before", "after", "beforeEach",
        "afterEach", "mock", "run", "snapshot", "skip", "todo", "only",
    }),
    "node:assert": frozenset({
        "ok", "equal", "notEqual", "deepEqual", "notDeepEqual", "strictEqual",
        "notStrictEqual", "deepStrictEqual", "notDeepStrictEqual", "throws",
        "doesNotThrow", "rejects", "doesNotReject", "ifError", "match",
        "doesNotMatch", "fail", "strict", "AssertionError", "CallTracker",
    }),
}
_NODE_NAMED_EXPORTS["assert"] = _NODE_NAMED_EXPORTS["node:assert"]
_NODE_NAMED_EXPORTS["node:assert/strict"] = _NODE_NAMED_EXPORTS["node:assert"]

#: Assertion names that belong to Jest and Vitest, not to Node's runner. A
#: model reaching for these has the right idea and the wrong library, and the
#: list of what `node:test` does export does not tell it that.
#:
#: run-a7150a6c wrote `import { test, expect } from "node:test"` and then spent
#: three `grep`s hunting `expect(` through its own test files.
_JEST_ONLY = frozenset({"expect", "jest", "vi", "vitest", "beforeAll", "afterAll"})

#: `import { a, b as c } from 'module'`
_NAMED_IMPORT = re.compile(r"import\s*\{([^}]*)\}\s*from\s*['\"]([^'\"]+)['\"]")

#: CommonJS in a file the runtime will load as ESM.
_REQUIRE = re.compile(r"(?<![\w.])require\s*\(")
_MODULE_EXPORTS = re.compile(r"(?<![\w.])module\.exports\b")


def _unknown_named_imports(content: str) -> str | None:
    """A named import Node does not provide, with the import that works.

    Only for modules whose exports are known exactly. Anything else is left
    alone: guessing at a package's exports would produce false accusations, and
    a false accusation on a write is worth more than a missed one.
    """
    for match in _NAMED_IMPORT.finditer(content):
        names, module = match.group(1), match.group(2)
        known = _NODE_NAMED_EXPORTS.get(module)
        if known is None:
            continue
        for raw in names.split(","):
            name = raw.strip().split(" as ")[0].strip()
            if not name or name in known:
                continue
            if name in _JEST_ONLY and module.startswith(("node:test", "node:assert")):
                return (
                    f"`{module}` does not export `{name}`: that is Jest's and "
                    "Vitest's API, and this project's runner is Node's own. "
                    "Import `assert` from 'node:assert' and write "
                    "`assert.strictEqual(actual, expected)`, "
                    "`assert.deepStrictEqual(...)` or `assert.ok(...)` instead of "
                    f"`{name}(actual).toBe(expected)`."
                )
            if name == "assert" and module in ("node:assert", "assert"):
                return (
                    f"`import {{ assert }} from '{module}'` stops the file "
                    "loading - the module never links, so no test in it runs "
                    "and the failure is a `SyntaxError`, not an assertion. "
                    "`assert` is that module's *default* export, not a named one. "
                    f"Use `import assert from '{module}'`, or import the checks by "
                    # Not an f-string, so the braces are literal: doubling them
                    # here printed `import {{ strictEqual }}`, which is not
                    # JavaScript - a suggested fix the model could not have used.
                    "name - `import { strictEqual, deepStrictEqual, ok } from "
                    f"'{module}'`."
                )
            return (
                f"`{module}` does not export `{name}`, so this import fails when "
                f"the file is loaded. It exports: {', '.join(sorted(known))}."
            )
    return None


def _commonjs_in_a_module(relative_path: str, content: str) -> str | None:
    """`require` or `module.exports` in a file Node will load as ESM."""
    if not relative_path.lower().endswith(".mjs"):
        return None
    if _REQUIRE.search(content):
        return (
            "`require(...)` in a .mjs file fails with \"require is not defined in "
            "ES module scope\" - the extension makes this a module. Use "
            "`import x from '...'` instead."
        )
    if _MODULE_EXPORTS.search(content):
        return (
            "`module.exports` in a .mjs file fails with \"module is not defined in "
            "ES module scope\". Use `export` instead."
        )
    return None


#: JSON files that are allowed to carry comments, and so are not strict JSON.
#: TypeScript's compiler, ESLint and devcontainers all document this, and
#: parsing them as JSON would refuse a file that is perfectly correct.
_TOLERATES_COMMENTS = frozenset({
    "tsconfig.json", "jsconfig.json", "devcontainer.json", ".eslintrc.json",
})


def _broken_json(relative_path: str, content: str) -> str | None:
    """A .json file that will not parse, with where it stops.

    JSON has a real grammar, so this is certain in the way `ast.parse` is
    certain for Python - which is what makes it worth refusing over rather than
    noting.

    `package.json` is the one that matters most: Node reads it to resolve every
    module in the directory, so a broken one does not fail the file that
    contains it, it fails everything near it. run-0deeb8bf wrote one and got
    "Error parsing simple-to-do-list-app/package.json: Expected property name
    or '}' in JSON at position 73" from `package_json_reader` - a stack trace
    naming an internal Node module, two stages from the write.
    """
    name = relative_path.rsplit("/", 1)[-1]
    if name in _TOLERATES_COMMENTS:
        return None
    try:
        json.loads(content)
    except ValueError as failure:
        where = getattr(failure, "lineno", None)
        position = f" at line {where}" if where else ""
        return (
            f"This is not valid JSON{position}: {failure}. "
            + (
                "Node reads package.json to resolve every module in that "
                "directory, so a broken one breaks the whole project, not just "
                "this file. "
                if name == "package.json"
                else ""
            )
            + "Send the file again as complete, valid JSON."
        )
    return None


def structural_problem(relative_path: str, content: str) -> str | None:
    """What is structurally wrong with this file, or None if nothing is.

    Returns prose for the agent, naming the line that actually needs looking
    at rather than the line a parser happens to stop on.
    """
    if not content or not content.strip():
        return None
    suffix = "." + relative_path.rsplit(".", 1)[-1].lower() if "." in relative_path else ""

    if suffix == ".json":
        return _broken_json(relative_path, content)

    if suffix == ".py":
        try:
            ast.parse(content)
        except SyntaxError as failure:
            where = f" on line {failure.lineno}" if failure.lineno else ""
            return f"Python cannot parse this file{where}: {failure.msg}."
        except ValueError:
            # Null bytes and similar; not a syntax question.
            return None
        return None

    if suffix not in _BRACED:
        return None

    # Cheap, exact checks first: these name the fix, where a bracket imbalance
    # can only name a line.
    if suffix in {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx"}:
        for problem in (
            _commonjs_in_a_module(relative_path, content),
            _unknown_named_imports(content),
        ):
            if problem:
                return problem

    found = _confidently_unbalanced(content)
    if found is None:
        return None
    return (
        f"The brackets in this file do not balance: {found.detail}. "
        "Check the block that should contain line "
        f"{found.line} - when a parser reports a syntax error it names the "
        "line where it gave up, which is usually not the line that is wrong."
    )


__all__ = ["Imbalance", "structural_problem"]
