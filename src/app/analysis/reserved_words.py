"""A name the language will not allow, named as the reason the file will not parse.

A parser reports where it stopped. When the fault is that a keyword was used as
an identifier, where it stopped is not useful: the token is legal everywhere
else, so the message reads as a misplaced brace and the edit that follows moves
the problem to a new line instead of removing it.

Measured on run-df4dc6f5's `specialist_testing_1`, which was refused eight times
over four minutes writing `main.js`:

    08:49:06  edit_artifact   Unexpected token 'delete'  on line 57
    08:49:14  edit_artifact   Unexpected token 'delete'  on line 58
    08:49:29  edit_artifact   Unexpected token 'delete'  on line 23
    08:49:42  edit_artifact   Unexpected token 'delete'  on line 20
    08:51:04  replace_lines   Unexpected token 'delete'  on line 21

Five different line numbers for one cause. `delete` is reserved in JavaScript,
so `export const delete = ...` cannot parse however it is laid out, and the
refusals were all correct. None of them said the word `reserved`. The specialist
worked it out eventually and shipped `deleteTask`, which is the right answer and
cost eight model calls to reach.

The name came from the run's own plan - "implement exported functions: add(task),
edit(id, newTask), delete(id)" - so the agent was doing as it was told. That is
worth saying in the message: a document asking for a name does not make the name
legal, and no edit can resolve the contradiction.

Per language, because every language has such a set and they do not agree:
`delete` is reserved in JavaScript and ordinary in Python, `class` the other way
about. Both of this harness's parse checks use this - `node --check` for
JavaScript and `ast.parse` for Python - and a language added later needs only
its set and its binding forms.

Only declaration forms are matched. JavaScript allows a reserved word as a
property or a method name - `obj.delete`, `class A { delete() {} }` are both
legal - so matching a bare occurrence would report a fault in correct code.
`function delete`, `const delete`, `def class` and `class def` cannot be
anything but errors.
"""

from __future__ import annotations

import re

#: Suffix -> the language whose rules apply to it.
LANGUAGE_OF_SUFFIX: dict[str, str] = {
    ".js": "JavaScript",
    ".cjs": "JavaScript",
    ".mjs": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".py": "Python",
}

#: Words that cannot be bound as a name. Not the full keyword list: a word is
#: here because using it as an identifier is an error, so JavaScript's
#: contextual keywords (`async`, `get`, `of`, `let` outside strict mode) are
#: left out rather than reported as faults in code that parses.
RESERVED: dict[str, frozenset[str]] = {
    "JavaScript": frozenset({
        "break", "case", "catch", "class", "const", "continue", "debugger",
        "default", "delete", "do", "else", "enum", "export", "extends",
        "false", "finally", "for", "function", "if", "import", "in",
        "instanceof", "new", "null", "return", "super", "switch", "this",
        "throw", "true", "try", "typeof", "var", "void", "while", "with",
    }),
    "Python": frozenset({
        "and", "as", "assert", "async", "await", "break", "class", "continue",
        "def", "del", "elif", "else", "except", "False", "finally", "for",
        "from", "global", "if", "import", "in", "is", "lambda", "None",
        "nonlocal", "not", "or", "pass", "raise", "return", "True", "try",
        "while", "with", "yield",
    }),
}

# TypeScript reserves everything JavaScript does. Spelled out rather than
# aliased so a set can diverge without the other silently following.
RESERVED["TypeScript"] = RESERVED["JavaScript"]

#: Where a language binds a name. One pattern per language, `{name}` filled in
#: with the candidate. Declarations only - see the module docstring.
_BINDINGS: dict[str, str] = {
    "JavaScript": r"^[ \t]*(?:export[ \t]+)?(?:default[ \t]+)?(?:async[ \t]+)?"
                  r"(?:function|class|const|let|var)[ \t]+{name}\b",
    "Python": r"^[ \t]*(?:async[ \t]+)?(?:def|class)[ \t]+{name}\b",
}
_BINDINGS["TypeScript"] = _BINDINGS["JavaScript"]

#: How many lines one message names. A name bound twice is still one fault.
MAX_LINES_NAMED = 4


def language_of(relative_path: str) -> str | None:
    """The language whose reserved words apply to this file, or None."""
    if "." not in relative_path:
        return None
    return LANGUAGE_OF_SUFFIX.get("." + relative_path.rsplit(".", 1)[-1].lower())


def a_reserved_name_bound_in(
    relative_path: str, content: str
) -> tuple[str, str, list[int]] | None:
    """(language, name, lines) for the first reserved word bound as a name.

    None when the language is unknown, when nothing reserved is bound, or on any
    failure: this runs inside a refusal, and a refusal that raises is worse than
    one that is vague.
    """
    language = language_of(relative_path)
    if language is None or not content:
        return None
    words = RESERVED.get(language)
    template = _BINDINGS.get(language)
    if not words or not template:
        return None
    try:
        for name in sorted(words):
            pattern = re.compile(template.format(name=re.escape(name)), re.M)
            lines = [
                content.count("\n", 0, match.start()) + 1
                for match in pattern.finditer(content)
            ]
            if lines:
                return language, name, lines[:MAX_LINES_NAMED]
    except Exception:  # noqa: BLE001 - a hint must never fail a write
        return None
    return None


def why_the_name_cannot_work(relative_path: str, content: str) -> str:
    """The sentence a parser's own message is missing, or "".

    Leads with the word the parser never says. The line numbers come second,
    because the point is that no line is the problem.
    """
    found = a_reserved_name_bound_in(relative_path, content)
    if found is None:
        return ""
    language, name, lines = found
    listed = " and ".join(str(number) for number in lines)
    where = f"line {listed}" if len(lines) == 1 else f"lines {listed}"
    return (
        f" `{name}` is a reserved word in {language}, so it cannot be the name "
        f"of anything - it is bound here on {where}. This is not about where the "
        f"parser stopped, and moving the code will not help: give it a different "
        f"name and change everything that refers to it, including any export. If "
        f"a plan or specification asked for `{name}`, the document is asking for "
        f"something the language does not allow."
    )


__all__ = [
    "LANGUAGE_OF_SUFFIX",
    "MAX_LINES_NAMED",
    "RESERVED",
    "a_reserved_name_bound_in",
    "language_of",
    "why_the_name_cannot_work",
]
