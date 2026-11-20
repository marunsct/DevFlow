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
#: A line that states an error: an exception or error type with its message (a JavaScript runtime's bare `Error:` too),
#: a root cause, a panic, a fatal line.
_AN_ERROR = re.compile(
    r"(?:\b[A-Z]\w*(?:Exception|Error)\b\s*[:(]|^\s*Caused by:|\bpanic(?:ked)?\b|\bFATAL\b|^\s*fatal:|^\s*[Ee]rror(?:\[\w+\])?:"
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
#: Lines around a line naming the request that may hold its error.
_NEAR = 60
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


def _the_lines(output: str) -> list[str]:
    return [_STAMPS.sub("", _A_RUNNER_PREFIX.sub("", line.rstrip())) for line in str(output or "").splitlines()]


def _in_words(lines: list[str]) -> str:
    """The errors `lines` state and the last place in the product's own files, within `MOST_PRINTED`; "" for none."""
    stated = the_errors_stated("\n".join(lines))
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
        after, before = [], []
        for line in lines[at:at + _NEAR]:
            if (named := names(line)) is not None and not ours(named):
                break
            after.append(line)
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
