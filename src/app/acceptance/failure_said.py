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

A page test's matcher says what it looked for on the lines after its error (LF.1459). Measured on 263 failed tests of
19 runs: 45 lines in 6 runs read only `Error: expect(locator).toBeVisible() failed` or `TimeoutError: locator.fill:
Timeout 3000ms exceeded.` - the same for every page failure - while the locator, `Expected: visible`, `Error:
element(s) not found` and the call log's `waiting for getByLabel('Email')` followed. Those lines are read too: the
locator, the timeout, a second error line, and the first thing the call log waited for when no locator was printed.

`first_line_said` is the first line past the heading, for a reader that groups failures by it (LF.1461: three readers
took the heading for the error, so no two tests ever stopped at the same step and a thrown `Error: Login rate limited`
was never read); `what_it_sought` is the names a page test looked for, for the page it failed on to be cut around them
(LF.1460). Pure; never raises.
"""
from __future__ import annotations

import re
from typing import Any

#: A runner's heading for one test: `file:line:col › title`, maybe after a `[project] › `, any line ruled off, or a
#: Python runner's `____ test_name ____` rule.
_HEADING = re.compile(r"^\s*(?:\[[^\]\n]*\]\s+›\s+)?[^\s›]+:\d+:\d+\s+›\s|[─━═]{3,}\s*$|^\s*_{3,}\s.*\s_{3,}\s*$")
#: A matcher's value lines after its error: `Expected: 201`, `Received: 500`, `Expected path: "error"`,
#: `Received value: {...}`, a diff's `- Expected  - 1` / `+ Received  + 1`.
_A_VALUE = re.compile(r"^\s*(?:[-+]\s*)?(?:Expected|Received)\b", re.I)
#: What a page runner prints after a locator's error, in its own words: what it looked for, how long it waited, and a
#: second error line saying what it found (`Locator: getByRole('listitem')`, `Timeout: 3000ms`, `Error: element(s) not
#: found`).
_A_LOCATOR_LINE = re.compile(r"^\s*(?:Locator|Timeout|Error):\s")
#: Where a runner's call log starts, and the line of it that says what it waited for.
_A_CALL_LOG = re.compile(r"^\s*Call log:\s*$")
_WAITED_FOR = re.compile(r"^\s*-\s*waiting for\s+(.+?)\s*$")
#: Where the statement ends: the test's source shown by line number, a frame, an attachment.
_PAST_THE_STATEMENT = re.compile(r"^\s*>?\s*\d+\s*\||^\s*at\s|^\s*attachment #|^\s*Error Context:")
#: A name a locator looks for: the first quoted argument of a `getByLabel('Email')`-like call, and a `name:` or
#: `hasText:` option's value.
_A_SOUGHT_NAME = re.compile(r"""\b(?:get\w+|locator|filter)\(\s*(['"`])(.+?)\1|\b(?:name|hasText)\s*:\s*(['"`])(.+?)\3""")
#: A role's own word (`getByRole('button', ...)`): what it is, not what it is called.
_A_ROLE_WORD = re.compile(r"^[a-z]+$")
#: How much of it a line keeps, as the first line did before.
MOST = 300


def is_a_heading(line: Any) -> bool:
    """Whether `line` is a runner's own heading for a test, not anything the test said."""
    return bool(_HEADING.search(str(line or "")))


def first_line_said(message: Any) -> str:
    """The first line of `message` that is not a runner's heading, stripped; "" when there is none."""
    return next((line.strip() for line in str(message or "").splitlines() if line.strip() and not is_a_heading(line)),
                "")


def what_it_sought(message: Any) -> list[str]:
    """The names a failed page test's locator looked for, from its `Locator:` line or its call log; [] when none."""
    found: list[str] = []
    for line in str(message or "").splitlines():
        if not (line.strip().startswith("Locator:") or _WAITED_FOR.match(line)):
            continue
        for match in _A_SOUGHT_NAME.finditer(line):
            name = (match.group(2) or match.group(4) or "").strip()
            if match.group(2) and _A_ROLE_WORD.match(name):
                continue
            if name and name not in found:
                found.append(name)
    return found


def what_it_said(message: Any, most: int = MOST) -> str:
    """The failure's own statement: the first line of `message` that is not a runner's heading, then the value and
    locator lines printed right after it (blank lines between them passed over, and of a call log only what it waited
    for), joined by "; " and cut to `most`; "" when it says nothing but its heading."""
    lines = str(message or "").splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() and not is_a_heading(line)), None)
    if start is None:
        return ""
    said = [lines[start].strip()]
    in_the_call_log = False
    for line in lines[start + 1:]:
        if not line.strip():
            continue
        if _PAST_THE_STATEMENT.match(line):
            break
        if _A_CALL_LOG.match(line):
            in_the_call_log = True
            continue
        if in_the_call_log:
            # Only what it waited for, and only when no `Locator:` line said it already.
            waited = _WAITED_FOR.match(line)
            if waited and not any(item.startswith(("Locator:", "waiting for")) for item in said):
                said.append(f"waiting for {waited.group(1)}")
            continue
        if not (_A_VALUE.search(line) or _A_LOCATOR_LINE.match(line)):
            break
        said.append(" ".join(line.split()))
    return "; ".join(said)[:most]


__all__ = ["MOST", "first_line_said", "is_a_heading", "what_it_said", "what_it_sought"]
