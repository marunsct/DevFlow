"""What a failed start said went wrong: the lines stating an error, ahead of the end of its output.

Measured on one Java run: the product exited at start with a long stack trace, and the 1,200 characters kept from the
end of its output were stack frames and "... 44 common frames omitted" - the exception's own message and its
"Caused by:" line, which named the setting the database refused, were cut, and two fix rounds passed without it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

#: One frame of a stack trace, in the shapes the common runtimes print; never the line stating the error.
_A_FRAME = re.compile(
    r"^\s*(?:at\s+\S|\.\.\.\s*\d+\s+(?:common\s+frames\s+omitted|more)\b|File\s+\"[^\"]+\",\s+line\s+\d+"
    r"|\d+:\s+0x[0-9a-f]+|\S+\.(?:go|rs):\d+(?:\s+\+0x[0-9a-f]+)?\s*$|goroutine\s+\d+\s+\[)"
)
#: A line that states an error: an exception or error type with its message (a JavaScript runtime's bare `Error:` too),
#: a dotted exception name standing alone (`sqlalchemy.exc.InvalidRequestError.` - measured on one run, a test round's
#: defect named the error that way, with no message, and no lookup found an error in it; LF.1412), a root cause, a
#: panic, a fatal line.
_AN_ERROR = re.compile(
    r"(?:\b[A-Z]\w*(?:Exception|Error)\b\s*[:(]|(?<![\w.])[A-Za-z_]\w*(?:\.\w+)*\.[A-Z]\w*(?:Exception|Error)\b"
    r"|^\s*Caused by:|\bpanic(?:ked)?\b|\bFATAL\b|^\s*fatal:|^\s*[Ee]rror(?:\[\w+\])?:|\bERROR\b)"
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


#: How a defect introduces what the product's server printed while a probe's request failed.
THE_SERVER_PRINTED = "the server printed:"
#: Characters of what the server printed that a defect carries for one request.
MOST_PRINTED = 400
#: How a suite runner marks what the product's server printed: Playwright's `webServer` prefix.
_A_RUNNER_PREFIX = re.compile(r"^\[WebServer\] ?")
#: The time and process stamps a server puts before each line: `[2026-11-20 05:05:43 +0000] [8]`.
_STAMPS = re.compile(r"^(?:\s*\[[^\]]*\d[^\]]*\])+\s*")
#: A line naming a request: an access line (`"DELETE /items/7 HTTP/1.1" 500`) or a framework's own
#: (`Exception on /items/7 [DELETE]`).
_A_REQUEST = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(/\S*)|\bon\s+(/\S*)\s+\[([A-Z]+)\]")
#: A frame in a runtime's or a library's own files, never the product's.
_NOT_THE_PRODUCT_S = re.compile(r"site-packages|dist-packages|/lib/python\d|<frozen|node_modules|node:internal")
#: A frame, in the shapes a Python or a JavaScript runtime prints.
_A_PLACE = re.compile(r"^\s*(?:File\s+\"[^\"]+\",\s+line\s+\d+.*|at\s+\S.*)$")
#: Lines around a line naming the request that may hold its error; the lines of a stack trace are not counted.
_NEAR = 60
#: Lines after a line naming the request read at most, its stack traces' lines included.
_MOST_READ = 2_000
#: An HTML page, where a JSON answer or plain text was expected.
_MARKUP = re.compile(r"<\s*(?:!doctype|html|head|body|title|h1)\b", re.I)


def the_page_in_words(said: str) -> str:
    """`said` - the start of a body a product answered - with an HTML page cut to its title (or heading, or its first
    words): a framework's error page is markup that crowds out what the server printed."""
    text = str(said or "")
    if not _MARKUP.search(text):
        return text
    named = re.search(r"<title[^>]*>(.*?)(?:<|$)", text, re.I | re.S) or re.search(r"<h1[^>]*>(.*?)(?:<|$)", text,
                                                                                    re.I | re.S)
    words = " ".join(re.sub(r"<[^>]*>?", " ", named.group(1) if named and named.group(1).strip() else text).split())
    return f'an HTML page, "{words[:120]}"' if words else "an HTML page"


@dataclass(frozen=True)
class _TraceShape:
    """How one family of runtimes prints an exception with its stack trace."""

    #: A line its frames start at.
    opens: re.Pattern[str]
    #: Where the exception's own line stands: "after" its frames (it ends the trace) or "before" them (just above).
    stated: str
    #: A line naming an exception's cause, printed just above that cause's own frames.
    cause: re.Pattern[str] | None = None


#: The stack traces of the runtimes the harness recognises. The line naming what failed is the exception's own, and a
#: cause's where the trace names one; a framework's header line above a trace ("Exception in ASGI application") says
#: only that something failed. Measured on one run: a 500 at a huge id was shown as uvicorn's header alone, the
#: traceback's last line - `OverflowError: Python int too large to convert to SQLite INTEGER` - left out.
_TRACE_SHAPES = (
    # Python: "Traceback (most recent call last):", indented frames, then the unindented "SomeError: message"; in a
    # chain each exception ends its own traceback, the first printed the earliest.
    _TraceShape(re.compile(r"^Traceback \(most recent call last\):"), "after"),
    # JavaScript runtimes, the JVM and .NET: "TypeError: message", 'Exception in thread "main" java.lang.X: message' or
    # "Unhandled exception. System.X: message" just above "    at ..." frames; a cause as "[cause]: Error: ...",
    # "Caused by: ..." (the last the root) or an inner exception's " ---> System.Y: ...".
    _TraceShape(re.compile(r"^\s+at\s+\S"), "before", re.compile(r"^\s*(?:Caused by:|-+>|\[cause\]:)\s*\S")),
    # Go: "panic: message", then "goroutine 1 [running]:" and its frames.
    _TraceShape(re.compile(r"^goroutine\s+\d+\s+\["), "before"),
)
#: A line naming an exception: `Name: message` (dotted, or a runtime's prefix before it) or a bare `NameError`.
_NAMES_AN_EXCEPTION = re.compile(r"^\s*\S[^:]{0,200}:\s*\S|^\s*[\w.$]+(?:Error|Exception)\s*$")
#: A line of a stack trace other than the exception's own: blank, indented, a frame, a chain's marker.
_IN_A_TRACE = re.compile(r"^\s*$|^\s|^Traceback \(most recent call last\):|^During handling of the above exception"
                         r"|^The above exception was the direct cause")


def _the_lines_traced(lines: list[str]) -> list[str]:
    """The exceptions `lines` print with a stack trace - each one's own line and its causes' - in the order printed,
    each once; [] when they hold no trace."""
    found: dict[int, str] = {}
    for shape in _TRACE_SHAPES:
        for at, line in enumerate(lines):
            if not shape.opens.search(line):
                continue
            if shape.stated == "after":
                end = at + 1
                while end < len(lines) and _IN_A_TRACE.search(lines[end]):
                    end += 1
                if end < len(lines) and not _A_REQUEST.search(lines[end]):
                    found[end] = lines[end]
                continue
            if at and shape.opens.search(lines[at - 1]):
                continue
            above = at - 1
            while above >= 0 and not lines[above].strip():
                above -= 1
            while above >= 0 and shape.cause is not None and shape.cause.search(lines[above]):
                found[above] = lines[above]
                above -= 1
            if above >= 0 and not shape.opens.search(lines[above]) and (
                    _AN_ERROR.search(lines[above]) or _NAMES_AN_EXCEPTION.search(lines[above])):
                found[above] = lines[above]
    said = [" ".join(found[at].split())[:300] for at in sorted(found)]
    return list(reversed(list(dict.fromkeys(reversed(said)))))


def _the_lines(output: str) -> list[str]:
    return [_STAMPS.sub("", _A_RUNNER_PREFIX.sub("", line.rstrip())) for line in str(output or "").splitlines()]


def _in_words(lines: list[str]) -> str:
    """The errors `lines` state - the exceptions of their stack traces where they hold one - and the last place in the
    product's own files, within `MOST_PRINTED`; "" for none."""
    stated = _the_lines_traced(lines) or the_errors_stated("\n".join(lines))
    if not stated:
        return ""
    places = [" ".join(line.split()) for line in lines if _A_PLACE.match(line) and not _NOT_THE_PRODUCT_S.search(line)]
    # The frame nearest the error: Python prints it last, a JavaScript runtime first.
    nearest = next((place for place in reversed(places) if place.startswith("File ")), places[0] if places else "")
    if nearest:
        stated[-1] = f"{stated[-1]} ({nearest[:160]})"
    kept: list[str] = []
    for line in reversed(stated):
        if kept and sum(len(each) + 3 for each in kept) + len(line) > MOST_PRINTED:
            break
        kept.insert(0, line[:MOST_PRINTED])
    return " / ".join(kept)


def what_the_server_printed_for(output: str, path: str, method: str = "") -> str:
    """The error the server printed for its `method` request to `path`, in `output` (what it printed while a probe
    ran); "".

    Measured on one run: `DELETE /items/99999999999999999999` answered 500 with the framework's HTML error page, the
    defect showed only that page, and five fixes in a row missed the cause the service had printed with its
    traceback - `OverflowError: Python int too large to convert to SQLite INTEGER`. The error is the one printed near
    a line naming the request (a framework's `Exception on <path>` or an access line), before the next request's.
    """
    lines = _the_lines(output)
    path, method = str(path or "").split("?")[0], str(method or "").upper()
    if not path or not lines:
        return ""

    def names(line: str) -> tuple[str, str] | None:
        found = _A_REQUEST.search(line)
        if found is None:
            return None
        named = (found.group(2) or found.group(3)).split("?")[0].rstrip("\"'")
        return found.group(1) or found.group(4), named

    def ours(request: tuple[str, str] | None) -> bool:
        return request is not None and request[1] == path and (not method or request[0] == method)

    for at in reversed([i for i, line in enumerate(lines) if ours(names(line))]):
        after, before, counted = [], [], 0
        for line in lines[at:at + _MOST_READ]:
            if (named := names(line)) is not None and not ours(named):
                break
            after.append(line)
            counted += not _IN_A_TRACE.search(line)
            if counted >= _NEAR:
                break
        for line in reversed(lines[max(at - _NEAR, 0):at]):
            if (named := names(line)) is not None and not ours(named):
                break
            before.insert(0, line)
        found = _in_words(after) or _in_words(before)
        if found:
            return found
    return ""


def what_the_server_printed(output: str) -> str:
    """The last errors the server printed in `output`, tied to no request, within `MOST_PRINTED`; "" for none."""
    return _in_words(_the_lines(output))


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


# --- what a server logged: its errors and their frames in the product's own files (LF.1410) ------------------------

#: An access line: a request with the status it was answered (`"POST /api/x HTTP/1.1" 500 Internal Server Error`,
#: `POST /api/x 500 12ms`). It says a request failed, never why: measured on two runs, five such lines filled what a
#: failing criterion's defect carried of the log, the traceback behind them was dropped, and the note that the
#: handler hid the cause was silenced because the log was "not empty".
_AN_ACCESS_LINE = re.compile(r"\b(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+/\S*(?:\s+HTTP/[\d.]+)?\"?\s+[1-5]\d\d\b")
#: Lines stating an error in the shapes servers log them beyond `_AN_ERROR`: PHP's `Fatal error:`, .NET's `fail:`,
#: `level=error`, an unhandled exception's header.
_LOGGED_AN_ERROR = re.compile(r"\bFatal error:|^\s*fail:|\blevel=(?:error|fatal)\b|\bUnhandled exception\b|\bpanicked at\b",
                              re.I)
#: A frame of a stack trace, in the shapes the common runtimes log: Python's `File "...", line N`, `at ...` (JavaScript,
#: Java, .NET, Rust's backtrace), PHP's `#0 /path(12): ...`, Rust's numbered `12: name`.
_A_LOGGED_FRAME = re.compile(r"^\s*(?:File\s+\"[^\"]+\",\s+line\s+\d+|at\s+\S|#\d+\s+\S|\d+:\s+\S)")
#: A frame in a runtime's, a framework's or a library's own code, never the product's.
_A_LIBRARY_FRAME = re.compile(
    r"site-packages|dist-packages|/lib/python\d|<frozen|node_modules|node:internal|/vendor/|\.cargo/registry|/rustc/"
    r"|\bat\s+(?:java|javax|jdk|sun|kotlin|org\.springframework|org\.apache|org\.hibernate|System|Microsoft)\.")
#: The opening of a Python traceback, whose frames come before the error they lead to.
_A_TRACEBACK = re.compile(r"^\s*Traceback \(most recent call last\):")
#: What differs between two loggings of one error: times, numbers, addresses.
_VARYING_IN_A_LOG = re.compile(r"0x[0-9a-fA-F]+|\d+")
#: Product frames kept with one error, at most.
MOST_FRAMES_PER_ERROR = 3


def is_an_access_line(line: str) -> bool:
    """Whether `line` is a server's access line: a request and the status it was answered."""
    return bool(_AN_ACCESS_LINE.search(str(line or "")))


def _states_a_logged_error(line: str) -> bool:
    return bool(_AN_ERROR.search(line) or _LOGGED_AN_ERROR.search(line))


def the_errors_logged(lines: list[str], *, most_lines: int, most_characters: int) -> list[str]:
    """The errors a server logged in `lines` - no access line among them - each with up to `MOST_FRAMES_PER_ERROR` of
    its frames in the product's own files, each error once (compared without its numbers), the latest last; within
    `most_lines` and `most_characters`, taken from the end, so a chain's root cause is the one kept."""
    entries: dict[str, list[str]] = {}
    current: list[str] | None = None
    waiting: list[str] = []  # a Python traceback's product frames, before the error they lead to
    in_a_traceback = False
    for raw in lines:
        line = _STAMPS.sub("", str(raw or "").rstrip())
        if not line.strip() or is_an_access_line(line):
            continue
        if _A_TRACEBACK.match(line):
            in_a_traceback, waiting, current = True, [], None
            continue
        if _A_LOGGED_FRAME.match(line):
            if _A_LIBRARY_FRAME.search(line):
                continue
            if in_a_traceback:
                waiting.append(line)
            elif current is not None and len(current) <= MOST_FRAMES_PER_ERROR:
                current.append(line)
            continue
        if not line.startswith((" ", "\t")) and _states_a_logged_error(line):
            said = " ".join(line.split())[:300]
            key = _VARYING_IN_A_LOG.sub("#", said)
            entries.pop(key, None)
            current = [said, *waiting[-MOST_FRAMES_PER_ERROR:]]
            entries[key] = current
            waiting, in_a_traceback = [], False
            continue
        if in_a_traceback and not line.startswith((" ", "\t")):
            in_a_traceback = False
    kept: list[str] = []
    for entry in reversed(list(entries.values())):
        if kept and (len(kept) + len(entry) > most_lines
                     or sum(len(k) + 1 for k in kept) + sum(len(e) + 1 for e in entry) > most_characters):
            break
        kept[:0] = entry
    return kept


def states_a_cause(logged: str) -> bool:
    """Whether a server's log states an error, not only requests answered with an error status."""
    return bool(the_errors_logged(str(logged or "").splitlines(), most_lines=1_000, most_characters=1_000_000))
