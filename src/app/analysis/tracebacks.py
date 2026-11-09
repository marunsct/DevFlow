"""A long failure output with the stack frames outside the project collapsed (plan SZ.3).

What a model is shown of a command or a failing test is cut to a budget: the
fix's failure text from the front (`rewritten_fixes.what_failed`), a
command's output to its head and tail (`sandbox._truncate`). A traceback that
runs through a framework, a test runner and the language's runtime spends
most of that budget on frames nobody in the project can change, and on a
large product - deeper call chains, more failing tests in one run - the cut
then falls on the project's own frames and the assertion between them.

So, only when an output is over its budget, a run of three or more frames that
point outside the project becomes one line saying how many were left out.
Which frames those are is read from the path each names, never from the
language: a path under a dependency or runtime directory (`site-packages`,
`node_modules`, `vendor`, `pkg/mod`, `/usr/lib`, ...), an absolute path no
workspace file ends with, or a bare file name - a Java or .NET frame gives
`OrderService.java`, not a path - that no workspace file has. A frame whose
file is in the workspace is never collapsed, nor is any line that is not a
frame - the error, the assertion, the test's name - and the frame a traceback
ends on is kept, since that is where the failure was raised. An output within
its budget is returned exactly as it was.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

#: Consecutive frames outside the project that are collapsed into one line, at least.
FEWEST_COLLAPSED = 3

#: A part of a path that puts it outside what the project can change.
_OUTSIDE = re.compile(
    r"site-packages|dist-packages|node_modules|[\\/]\.?venv[\\/]|[\\/]vendor[\\/]|[\\/]pkg[\\/]mod[\\/]|"
    r"^/usr/|^/opt/|^/Library/|[\\/]lib[\\/]python\d|[\\/]go[\\/]src[\\/]|[\\/]gems[\\/]|[\\/]\.cargo[\\/]|"
    r"[\\/]\.rustup[\\/]|[\\/]\.m2[\\/]|[\\/]\.gradle[\\/]|[\\/]\.nuget[\\/]|^node:|^internal[\\/]|<frozen |"
    r"^<anonymous>$|^\[internal function\]$|^\{main\}$|^Native Method$|^Unknown Source$",
)

#: Go's path line, under the function line it belongs to: \t/usr/local/go/src/net/http/server.go:2136 +0x29
_GO_PATH = re.compile(r"^\t(?P<file>\S+\.go):\d+(?: \+0x[0-9a-f]+)?\s*$")
#: Frame shapes, each giving the file the frame is in (empty when it names none). Java's
#: before .NET's: a .NET frame without a file would otherwise take a Java frame's file away.
_FRAMES = (
    # Python: File "/app/svc/routes.py", line 12, in handler
    re.compile(r'^\s+File "(?P<file>[^"]+)", line \d+'),
    # pytest's short traceback: /usr/lib/python3/site-packages/_pytest/x.py:123: in call
    re.compile(r"^(?P<file>[^\s:]+\.py):\d+: in \S+\s*$"),
    # Java, Kotlin, Scala: at com.acme.Orders.create(Orders.java:12) / (Native Method)
    re.compile(r"^\s+at [\w.$<>/]+\((?P<file>[^():]+?)(?::\d+)?\)\s*$"),
    # .NET: at Acme.Orders.Create() in /src/Orders.cs:line 12 (or without " in ...")
    re.compile(r"^\s+at [\w.`<>\[\],+|]+\([^)]*\)(?: in (?P<file>.+?):line \d+)?\s*$"),
    # JavaScript: at fn (/app/x.js:1:2), at /app/x.js:1:2, at async fn (node:internal/x:1:2)
    re.compile(r"^\s+at (?:.*? \()?(?P<file>(?:file://)?(?:[A-Za-z]:)?[^\s()]+?):\d+(?::\d+)?\)?\s*$"),
    re.compile(r"^\s+at (?:async )?[^\s()]+ \((?P<file>[^():]*)\)\s*$"),
    # PHP: #3 /var/www/vendor/x/Y.php(123): Foo->bar() / #4 {main} / #2 [internal function]: ...
    re.compile(r"^#\d+ (?P<file>[^\s(]+?)(?:\(\d+\))?(?::|$)"),
    re.compile(r"^#\d+ (?P<file>\{main\}|\[internal function\])"),
    # Ruby and others: /usr/lib/ruby/gems/x.rb:12:in 'call' / from ./lib/x.rb:3:in ...
    re.compile(r"^\s*(?:from )?(?P<file>(?:/|\./|[A-Za-z]:\\)[^\s:]+):\d+(?::in .*|:\d+)?\s*$"),
    _GO_PATH,
    # Java: ... 23 more
    re.compile(r"^\s+\.\.\. \d+ (?P<file>more)\s*$"),
)
#: A frame followed by the source line it points at (Python's, and pytest's short one).
_CARRIES_ITS_SOURCE = re.compile(r'^\s+File "|^[^\s:]+\.py:\d+: in ')
#: A Go frame's function line, which belongs to the path line after it.
_GO_FUNCTION = re.compile(r"^[\w.\-/*()\[\]{}]+\(.*\)\s*$")


def _the_file(line: str) -> str | None:
    """The file a frame line names - "" for a frame that names none - or None when it is not a frame."""
    for shape in _FRAMES:
        found = shape.match(line)
        if found:
            return found.group("file") or ""
    return None


class _Workspace:
    """Which files a frame may be in, read from the workspace once and only when a frame needs it."""

    def __init__(self, root: str | Path | None) -> None:
        self.root = Path(root) if root else None
        self._names: set[str] | None = None
        self._paths: set[str] | None = None

    def _read(self) -> None:
        from app.tools.repository import IGNORED_DIRECTORIES

        self._names, self._paths = set(), set()
        if self.root is None or not self.root.is_dir():
            return
        for directory, subdirectories, files in os.walk(self.root, onerror=lambda _: None):
            subdirectories[:] = [d for d in subdirectories if d not in IGNORED_DIRECTORIES]
            relative = Path(directory).relative_to(self.root)
            for name in files:
                self._names.add(name)
                self._paths.add((relative / name).as_posix())

    def holds(self, file: str) -> bool:
        if self._names is None:
            self._read()
        assert self._names is not None and self._paths is not None
        cleaned = file.removeprefix("file://").replace("\\", "/")
        if "/" not in cleaned:
            return cleaned in self._names
        parts = [p for p in cleaned.split("/") if p not in ("", ".")]
        # Ends with a workspace file's path, however the root is spelled where it ran:
        # a container's `/workspace/svc/x.py` is the worker's `svc/x.py`.
        return any("/".join(parts[i:]) in self._paths for i in range(len(parts)))


def _is_outside(file: str, workspace: _Workspace) -> bool:
    if _OUTSIDE.search(file) or file in ("", "more"):
        return True
    if workspace.root is None:
        return False
    return not workspace.holds(file)


def without_outside_frames(text: str, workspace: str | Path | None = None) -> str:
    """`text` with each run of `FEWEST_COLLAPSED` or more frames outside the project made one line."""
    lines = text.split("\n")
    known = _Workspace(workspace)
    # Each frame as the lines it spans and whether it is outside; any other line as itself.
    units: list[tuple[int, int, bool | None]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        go_path = _GO_PATH.match(lines[index + 1]) if index + 1 < len(lines) else None
        if go_path and _GO_FUNCTION.match(line):
            units.append((index, index + 2, _is_outside(go_path.group("file"), known)))
            index += 2
            continue
        file = _the_file(line)
        if file is None:
            units.append((index, index + 1, None))
            index += 1
            continue
        end = index + 1
        # Python's frame line is followed by the source line it points at, indented deeper.
        if _CARRIES_ITS_SOURCE.match(line) and end < len(lines):
            margin = len(line) - len(line.lstrip())
            after = lines[end]
            if after.strip() and len(after) - len(after.lstrip()) > margin and _the_file(after) is None:
                end += 1
        units.append((index, end, _is_outside(file, known)))
        index = end

    kept: list[str] = []
    run: list[tuple[int, int, bool | None]] = []

    def close(ends_the_traceback: bool) -> None:
        # The frame a traceback ends on is where the failure was raised: kept.
        last = run[-1:] if ends_the_traceback else []
        omitted = run[:-1] if ends_the_traceback else run
        if len(omitted) >= FEWEST_COLLAPSED:
            first = lines[omitted[0][0]]
            margin = first[: len(first) - len(first.lstrip())]
            frames = len(omitted)
            kept.append(f"{margin}... [{frames} frames outside the project omitted] ...")
            for start, end, _ in last:
                kept.extend(lines[start:end])
        else:
            for start, end, _ in run:
                kept.extend(lines[start:end])
        run.clear()

    for unit in units:
        start, end, outside = unit
        if outside:
            run.append(unit)
            continue
        if run:
            close(ends_the_traceback=outside is None)
        kept.extend(lines[start:end])
    if run:
        close(ends_the_traceback=True)
    return "\n".join(kept)


__all__ = ["FEWEST_COLLAPSED", "without_outside_frames"]
