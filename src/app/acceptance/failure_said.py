"""What a failed test said, read past its runner's own heading (LF.1393).

A failure's message as the runner's report keeps it can open with the runner's heading for the test - its file, line
and title, ruled off (`auth.spec.js:23:1 › [AC-1] registration creates a new user ─────`) - and only then the error:
`Error: expect(received).toBe(expected)`, a blank line, `Expected: 201`, `Received: 500`, the code frame. Read by its
first line, every failed test said its own title and nothing else.

Measured on one medium run: the test round was shown 13 failing tests, each line only its heading. It read the
acceptance files 6 times each, ran the whole suite again and read its output to learn that registration answered
500 where 201 was expected and the sign-in 429 where 401 was - the statuses the saved result already held. The same
line opens each failing criterion's defect, which is what its fixer is shown first.

`what_it_said` is the error's own statement: its first line after any heading, with the expected and received values
a matcher prints after it. A message whose first line is already the error (a Python assertion) reads as before.
Pure; never raises.
"""
from __future__ import annotations

import re
from typing import Any

#: A runner's heading for one test: `file:line:col › title`, maybe after a `[project] › `, or any line ruled off.
_HEADING = re.compile(r"^\s*(?:\[[^\]\n]*\]\s+›\s+)?[^\s›]+:\d+:\d+\s+›\s|[─━═]{3,}\s*$")
#: A matcher's value lines after its error: `Expected: 201`, `Received: 500`, `Expected path: "error"`,
#: `Received value: {...}`, a diff's `- Expected  - 1` / `+ Received  + 1`.
_A_VALUE = re.compile(r"^\s*(?:[-+]\s*)?(?:Expected|Received)\b", re.I)
#: How much of it a line keeps, as the first line did before.
MOST = 300


def what_it_said(message: Any, most: int = MOST) -> str:
    """The failure's own statement: the first line of `message` that is not a runner's heading, then the value lines
    printed right after it (blank lines between them passed over), joined by "; " and cut to `most`; "" when it says
    nothing but its heading."""
    lines = str(message or "").splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() and not _HEADING.search(line)), None)
    if start is None:
        return ""
    said = [lines[start].strip()]
    for line in lines[start + 1:]:
        if not line.strip():
            continue
        if not _A_VALUE.search(line):
            break
        said.append(" ".join(line.split()))
    return "; ".join(said)[:most]


__all__ = ["MOST", "what_it_said"]
