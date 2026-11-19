"""What a failed start said went wrong: the lines stating an error, ahead of the end of its output.

Measured on one Java run: the product exited at start with a long stack trace, and the 1,200 characters kept from the
end of its output were stack frames and "... 44 common frames omitted" - the exception's own message and its
"Caused by:" line, which named the setting the database refused, were cut, and two fix rounds passed without it.
"""
from __future__ import annotations

import re

#: One frame of a stack trace, in the shapes the common runtimes print; never the line stating the error.
_A_FRAME = re.compile(
    r"^\s*(?:at\s+\S|\.\.\.\s*\d+\s+(?:common\s+frames\s+omitted|more)\b|File\s+\"[^\"]+\",\s+line\s+\d+"
    r"|\d+:\s+0x[0-9a-f]+|\S+\.(?:go|rs):\d+(?:\s+\+0x[0-9a-f]+)?\s*$|goroutine\s+\d+\s+\[)"
)
#: A line that states an error: an exception or error type with its message, a root cause, a panic, a fatal line.
_AN_ERROR = re.compile(
    r"(?:\b[A-Z]\w*(?:Exception|Error)\b\s*[:(]|^\s*Caused by:|\bpanic(?:ked)?\b|\bFATAL\b|^\s*fatal:|^\s*error(?:\[\w+\])?:"
    r"|\bERROR\b)"
)
#: Characters of the stated errors shown.
MOST_STATED = 900


def the_errors_stated(output: str) -> list[str]:
    """The lines of `output` that state an error, frames left out, each once and in order, the last kept."""
    lines = [line.rstrip() for line in str(output or "").splitlines()]
    stated = [" ".join(line.split()) for line in lines
              if line.strip() and not _A_FRAME.search(line) and _AN_ERROR.search(line)]
    kept: list[str] = []
    for line in dict.fromkeys(stated):
        kept.append(line[:300])
    out: list[str] = []
    total = 0
    for line in reversed(kept):
        if total + len(line) > MOST_STATED:
            break
        out.insert(0, line)
        total += len(line) + 1
    return out


def shown(output: str, most: int) -> str:
    """`output` as a fixer needs it, within about `most` characters: the errors it stated that the end of it does not
    show, then its end with the stack frames left out."""
    text = str(output or "").strip()
    if not text:
        return ""
    without_frames = "\n".join(line for line in text.splitlines() if not _A_FRAME.search(line))
    end = without_frames[-most:]
    missing = [line for line in the_errors_stated(text) if line not in " ".join(end.split())]
    if not missing:
        return end
    head = "The errors it stated:\n" + "\n".join(missing) + "\nThe end of its output:\n"
    return head + without_frames[-max(most - len(head), 300):]
