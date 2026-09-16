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


def structural_problem(relative_path: str, content: str) -> str | None:
    """What is structurally wrong with this file, or None if nothing is.

    Returns prose for the agent, naming the line that actually needs looking
    at rather than the line a parser happens to stop on.
    """
    if not content or not content.strip():
        return None
    suffix = "." + relative_path.rsplit(".", 1)[-1].lower() if "." in relative_path else ""

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
