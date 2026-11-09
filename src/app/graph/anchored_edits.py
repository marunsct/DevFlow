"""A file too long to rewrite whole, fixed by edits anchored on its own text (plan SZ.2).

The fast fix (`app.graph.rewritten_fixes`) hands the model each file whole and
takes back the whole file. That is the right shape for the files a small
product has: one reply, no tool to drive, nothing to transcribe. It does not
scale with the file. A reply is capped (32,768 tokens on the local server, the
reasoning before the answer included), so a file of a few thousand lines
cannot come back whole at all, and one that nearly fits comes back with the
parts the model did not mean to change shortened - the elision that whole-file
edit formats are known for on long files (Aider measured the same, and edits
long files by search and replace blocks for that reason).

So past `LARGEST_WHOLE_FILE_CHARACTERS` the request changes shape and nothing
else does: the model is shown the file's outline and the parts the failure
points at, and replies with SEARCH/REPLACE blocks. Each block is matched the
way `edit_artifact` matches - exactly once, else the same repairs of a
transcribed passage, each still unique (`content_with_passage_replaced`) - and
the edited file is written once, through the same write path and its parse
checks as a whole-file reply. A block that matches nowhere or more than once
leaves the file as it was, and the next pass is told which and why. Below the
threshold the request and the write are what they were.
"""

from __future__ import annotations

import re

#: A file longer than this is fixed by anchored edits instead of rewritten whole.
#:
#: From the reply cap, not from taste. The local server caps a reply at 32,768
#: tokens, reasoning included, and measured on one all-on run 57% of the
#: output tokens were reasoning. At the context budget's 3 characters a token
#: (`project_memory.CHARS_PER_TOKEN`), 24,000 characters is 8,000 tokens of
#: file echoed back - a quarter of the cap, which leaves the reasoning its
#: measured share and room to spare. A file past it either does not fit the
#: reply or is the size at which whole-file replies start to shorten what they
#: were not asked to change.
LARGEST_WHOLE_FILE_CHARACTERS = 24_000
#: Lines of the outline shown, at most.
MOST_OUTLINE_LINES = 150
#: Characters of the file's numbered windows shown, at most.
MOST_WINDOW_CHARACTERS = 16_000
#: Lines shown either side of a line the failure names.
LINES_AROUND_A_FAILURE = 20
#: Lines shown before and after a definition the failure or the defect names.
LINES_BEFORE_A_DEFINITION = 3
LINES_AFTER_A_DEFINITION = 40
#: Names from the failure looked for in the file, at most.
MOST_NAMES = 6

#: What a refusal of a block says, so the fix's passes keep it for the next one.
AN_EDIT_NOT_APPLIED = "was not applied"

SYSTEM = (
    "You correct source files of a software product. A file too long to rewrite whole is changed "
    "by SEARCH/REPLACE edits; you reply with those edits and nothing else."
)

#: A line that defines something, and the name it defines.
_DEFINITION = re.compile(
    r"^\s*(?:export\s+(?:default\s+)?)?(?:pub(?:\([a-z]+\))?\s+)?(?:(?:public|private|protected|internal|static|"
    r"abstract|final|override|virtual|async|sealed|partial)\s+)*"
    r"(?:function\*?|class|interface|type|enum|struct|trait|def|func|fn|module|impl|record|object|"
    r"(?:const|let|var)(?=\s+\w+\s*(?::[^=]+)?=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>))"
    r"\s+(?:\([^)]*\)\s*)?([A-Za-z_$][\w$]*)"
)
_A_NAME = re.compile(r"(?<![\w$])([A-Za-z_$][\w$]{3,})(?![\w$])")
_BLOCK = re.compile(
    r"^<{5,9}[ \t]*SEARCH[^\n]*\n(.*?)^={5,9}[ \t]*\n(.*?)^>{5,9}[ \t]*REPLACE[^\n]*$", re.S | re.M
)
_FENCED = re.compile(r"```[^\n`]*\n(.*?)```", re.S)


def too_long_to_rewrite(text: str) -> bool:
    """Whether a file this long is fixed by anchored edits rather than rewritten whole."""
    return len(text) > LARGEST_WHOLE_FILE_CHARACTERS


def _outline(lines: list[str]) -> list[tuple[int, str]]:
    found = []
    for number, line in enumerate(lines, 1):
        if _DEFINITION.match(line):
            found.append((number, " ".join(line.strip().rstrip("{:").split())[:120]))
    return found


def _lines_the_failure_names(path: str, failure: str) -> list[int]:
    """Line numbers the failure text gives for this file, in any of the usual frame shapes."""
    name = re.escape(path.rsplit("/", 1)[-1])
    shapes = re.compile(rf"(?<![\w.-]){name}(?:\"?,? line |:|\(|\", line )(\d+)")
    return sorted({int(found) for found in shapes.findall(failure)})


def _names_to_look_for(failure: str, defect_text: str, lines: list[str]) -> list[int]:
    """Lines where a definition, or else a use, of a name the failure or the defect mentions is."""
    text = f"{failure}\n{defect_text}"
    wanted = set(_A_NAME.findall(text))
    found: list[int] = []
    for number, line in enumerate(lines, 1):
        defined = _DEFINITION.match(line)
        if defined and defined.group(1) in wanted:
            found.append(number)
    if found:
        return found
    # No definition named: the first use of each name the failure gives in backticks
    # or as a call, which is how test output quotes the code it fails on.
    quoted = re.findall(r"`([A-Za-z_$][\w$]{3,})`|([A-Za-z_$][\w$]{3,})\(", failure)
    for name in dict.fromkeys(a or b for a, b in quoted):
        word = re.compile(rf"(?<![\w$]){re.escape(name)}(?![\w$])")
        hit = next((n for n, line in enumerate(lines, 1) if word.search(line)), None)
        if hit:
            found.append(hit)
        if len(found) >= MOST_NAMES:
            break
    return found


def _windows(lines: list[str], failing: list[int], defined: list[int]) -> list[tuple[int, int]]:
    spans = [(max(1, n - LINES_AROUND_A_FAILURE), min(len(lines), n + LINES_AROUND_A_FAILURE)) for n in failing]
    spans += [(max(1, n - LINES_BEFORE_A_DEFINITION), min(len(lines), n + LINES_AFTER_A_DEFINITION)) for n in defined]
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def excerpt(path: str, text: str, failure: str, defect_text: str = "") -> str:
    """What the model is shown of a long file: its outline, then the parts the failure points at."""
    lines = text.splitlines()
    windows = _windows(lines, _lines_the_failure_names(path, failure), _names_to_look_for(failure, defect_text, lines))
    if not windows:
        # Nothing the failure names is in this file: its opening, as far as the room allows.
        windows = [(1, len(lines))]
    shown, used = [], 0
    for start, end in windows:
        body = "\n".join(lines[start - 1:end])
        if used + len(body) > MOST_WINDOW_CHARACTERS:
            room = MOST_WINDOW_CHARACTERS - used
            if room <= 0:
                break
            kept = body[:room].rsplit("\n", 1)[0]
            end = start + kept.count("\n")
            body = kept
        shown.append(f"[lines {start}-{end}]\n{body}")
        used += len(body)
    outline = _outline(lines)
    head = (
        f"--- `{path}` as it is now: {len(lines)} lines, too long to rewrite whole, so its outline and the "
        "parts the failure points at ---"
    )
    parts = [head]
    if outline:
        listed = "\n".join(f"{number}: {line}" for number, line in outline[:MOST_OUTLINE_LINES])
        more = f"\n(and {len(outline) - MOST_OUTLINE_LINES} more)" if len(outline) > MOST_OUTLINE_LINES else ""
        parts.append(f"Outline (line: definition):\n{listed}{more}")
    parts.append("\n\n".join(shown))
    return "\n\n".join(parts)


def in_the_memory(path: str) -> str:
    """What stands for a long file the project memory above already holds whole: it is not shown twice."""
    return (
        f"--- `{path}` is in the project memory above, whole, as it is now. It is too long to rewrite "
        "whole, so it is changed by edits ---"
    )


def instruction(path: str) -> str:
    """How the model is asked to reply for a long file."""
    return (
        f"Reply with the edits to `{path}` that fix this, each in exactly this form:\n\n"
        "<<<<<<< SEARCH\n"
        "the lines to change, copied exactly from the file shown above\n"
        "=======\n"
        "the lines that replace them\n"
        ">>>>>>> REPLACE\n\n"
        "Each SEARCH must match the file exactly once: copy it from the lines shown, with their "
        "indentation and without the line numbers, and include a line next to the change if the "
        "lines alone could match elsewhere. Change only what the failure needs; keep every name, "
        "signature and message the specification gives. If this file needs no change for this "
        "failure, reply with no edit."
    )


def edits_in(reply: str) -> list[tuple[str, str]]:
    """The (SEARCH, REPLACE) pairs a reply holds, in its order.

    Each part without the newline that ends its last line, so the two stay alike
    however the passage is matched: a repaired match is found without it, and a
    replacement that kept it left a blank line behind. Except when REPLACE is
    empty, which deletes the lines and their line ending with them.
    """
    edits = []
    for search, replace in _BLOCK.findall(str(reply or "")):
        if replace:
            search, replace = search.removesuffix("\n"), replace.removesuffix("\n")
        edits.append((search, replace))
    return edits


def applied(path: str, original: str, reply: str) -> str:
    """`original` with every edit in `reply` made; `original` when it holds none.

    Raises RepositoryToolError naming the edit and why when one cannot be made,
    in which case none is: a file half-edited by a fix is harder to repair than
    one left as it was.
    """
    from app.tools.repository import RepositoryToolError, content_with_passage_replaced

    edits = edits_in(reply)
    if not edits:
        fenced = _FENCED.findall(str(reply or ""))
        if fenced and len(max(fenced, key=len)) > len(original) // 2:
            raise RepositoryToolError(
                f"The reply for `{path}` gave the whole file, which {AN_EDIT_NOT_APPLIED}: the file is too long "
                "to rewrite whole. Reply with SEARCH/REPLACE edits of only the lines to change."
            )
        return original
    content = original
    for number, (search, replace) in enumerate(edits, 1):
        try:
            content = content_with_passage_replaced(path, content, search, replace)
        except RepositoryToolError as refused:
            raise RepositoryToolError(
                f"Edit {number} of {len(edits)} {AN_EDIT_NOT_APPLIED}, so none of them were: {refused}"
            ) from refused
    return content


__all__ = [
    "AN_EDIT_NOT_APPLIED", "LARGEST_WHOLE_FILE_CHARACTERS", "SYSTEM", "applied", "edits_in", "excerpt",
    "in_the_memory", "instruction", "too_long_to_rewrite",
]
