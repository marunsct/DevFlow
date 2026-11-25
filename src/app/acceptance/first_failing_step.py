"""Where failing acceptance tests first fail, and the answer they got there: one step behind many tests is one cause.

Measured on one run: 80 locked tests failed - 37 answered 429 where they expected 201, 18 threw "Login rate limited"
at one line of the suite's shared helper, 8 threw "Login failed with status 401" at the same helper, 13 were answered
404 on every route under one prefix, 4 failed otherwise. The rule for one refusal behind the failures read only the
statuses a test asserted, saw 37 of 80 answered 429 and never fired; each criterion got a defect and a fixer of its own
for hours, and the one cause behind every 404 (a prefix given twice) was raised as eight symptom defects.

Two readings of a failed test's message, both runner-agnostic:

- its **answer**: the status it got where it expected another (`assert 401 == 201`, `Expected: 201 / Received: 429`, a
  failed `toBeOK()` on `<- 500`), or the status or refusal an error it threw names ("Login failed with status 401",
  "rate limited"), or - for a status-less error thrown at a shared step - the one answer the step's other tests name;
- its **first failing step**: the frame it threw at when several tests throw at that same file and line (a shared
  helper), else the request it made: its method and the leading resource of its path.

Pure functions; nothing raises.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence

#: A test's assertion on the status it got: `assert 401 == 201`, `assert 422 in (200, 201)`.
_A_REFUSAL = re.compile(r"assert (4\d\d|5\d\d) (?:==|in) \(?\s*(2\d\d|4\d\d)")
#: A browser or request runner's failed "answered well" check and the status it got (`toBeOK()` ... `<- 500 ...`).
_NOT_OK = re.compile(r"toBeOK\(\) failed.*?←\s*([45]\d\d)\b", re.S)
#: A JavaScript runner's `toBe` on a status (`Expected: 201` then `Received: 500`). Measured on a Rust run: 14 of 19
#: failing Playwright tests answered 500 on every route, none was read as one cause, and nine fixers each chased it.
_EXPECTED_RECEIVED = re.compile(r"Expected:\s*(2\d\d|4\d\d)\s*\n\s*Received:\s*(4\d\d|5\d\d)\b")
#: A `toContain` on a status, `expect([400, 422]).toContain(res.status())`: the runner names the status it got
#: "Expected value" and the statuses allowed "Received array". Measured: 6 such failures were read as no answer.
_NOT_IN_THE_LIST = re.compile(r"Expected value:\s*([45]\d\d)\s*\n\s*Received array:\s*\[([\d,\s]+)\]")
#: Any status a test asserted on, whatever it expected.
ANY_STATUS = re.compile(r"assert ([1-5]\d\d) (?:==|in|!=)")

#: An error a test or its helper threw on purpose, naming the status it was answered: "Login failed with status 401",
#: "register answered 429", "HTTP 500".
_A_STATUS_THROWN = re.compile(
    r"(?:\bstatus(?:\s+code)?|\bcode|\banswered|\bresponded|\breturned|\bgot|\bfailed|\bHTTP)\W{0,3}(?:with\W{0,2})?([45]\d\d)\b"
    r"|\b([45]\d\d)\s+(?:Not Found|Unauthori[sz]ed|Forbidden|Too Many Requests|Internal Server Error|Bad Request"
    r"|Unprocessable|Conflict|Method Not Allowed|Service Unavailable|Bad Gateway)\b",
    re.I,
)
#: An error a test or its helper threw naming a rate limit, whatever its status.
_A_LIMIT_THROWN = re.compile(r"\brate[\s_-]?limit|\btoo many (?:requests|attempts)\b|\bthrottl", re.I)
#: The first line of an assertion's own failure, not an error thrown on purpose.
_AN_ASSERTION = re.compile(r"expect\(|\bAssertionError\b|^\s*(?:E\s+)?assert\b|\bExpected:|\btoBe\w*\(", re.I)
#: The status a rate limit answers.
RATE_LIMITED = "429"

#: A JavaScript stack frame: `at login (/w/tests/test-utils.js:75:11)`, `at /w/tests/a.spec.ts:12:5`.
_A_SCRIPT_FRAME = re.compile(r"^\s*at\s+(?:[^\n(]*?\()?(?:file://)?([^\s()]+?\.(?:[cm]?[jt]sx?)):(\d+)(?::\d+)?\)?\s*$", re.M)
#: A Python frame: pytest's `tests/helpers.py:75: in login` / `tests/helpers.py:75: RuntimeError`, or a traceback's
#: `File "tests/helpers.py", line 75`.
_A_PYTHON_FRAME = re.compile(r'^([^\s:"]+\.py):(\d+):\s|^\s*File "([^"]+\.py)", line (\d+)', re.M)
#: A frame in a library the suite or the product uses, not in their own code.
_A_LIBRARY = re.compile(r"node_modules|site-packages|dist-packages|/lib/python\d|<frozen|node:internal")
#: Where a code frame marks the failing line: `> 75 |`.
_THE_MARKED_LINE = re.compile(r"^\s*>\s*\d+\s*\|", re.M)

#: A request in a runner's call log or a server's line: `-> POST http://localhost:3000/api/items`, `GET /api/items/3`.
_A_LOGGED_REQUEST = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(?:https?://[^/\s\"'`]+)?(/[^\s\"'`)]*)")
#: A request in a test's code: `request.post('/api/items', ...)`, `client.get(f"/api/items/{id}")`, `fetch(\`${B}/x\`)`.
_A_REQUEST_CALL = re.compile(r"\.(get|post|put|patch|delete)\(\s*f?([`'\"])(.*?)\2", re.I)
#: A placeholder in a path a test builds: `${id}`, `{id}`, `:id`.
_A_PLACEHOLDER = re.compile(r"\$\{[^}]*\}|\{[^}]*\}")
#: A path segment that names one record, not a resource: a number, an id, a placeholder.
_AN_ID = re.compile(r"^(?::\w+|\d+|[0-9a-f]{8,}(?:-[0-9a-f]{4,})*|\*|<[^>]*>)$", re.I)
#: Leading path segments every route of a service may share, read past to the resource: `/api`, `/v1`.
_A_SHARED_LEAD = re.compile(r"^(?:api|v\d+)$", re.I)
#: Source lines read back from a failing line to find the request it checks.
_LINES_BACK = 15

#: Tests at least, criteria at least, and the share of the failed tests (one in this many) one step must stop.
LEAST_TESTS = 3
LEAST_CRITERIA = 2
ONE_IN = 10


def _plain(message: Any) -> str:
    return str(message or "")


def the_wrong_answer(message: Any) -> str:
    """The status a failed test got where it expected another, as its assertion states it; or ""."""
    message = _plain(message)
    if (m := _A_REFUSAL.search(message)) and m.group(1) != m.group(2):
        return m.group(1)
    if m := _NOT_OK.search(message):
        return m.group(1)
    if (m := _EXPECTED_RECEIVED.search(message)) and m.group(1) != m.group(2):
        return m.group(2)
    if (m := _NOT_IN_THE_LIST.search(message)) and m.group(1) not in re.findall(r"\d+", m.group(2)):
        return m.group(1)
    return ""


def what_it_threw(message: Any) -> str:
    """The first line of an error a test or its helper threw on purpose; "" for an assertion's own failure.

    Read past the runner's heading for the test (LF.1461): measured on 466 saved failures, 412 opened with it, and in
    all 79 where a test threw on purpose this answered the heading, never `Error: Login rate limited`.
    """
    from app.acceptance.failure_said import is_a_heading

    for line in _plain(message).splitlines():
        line = re.sub(r"^\s*E\s{2,}", "", line).strip()
        if not line or is_a_heading(line):
            continue
        return "" if _AN_ASSERTION.search(line) else line[:300]
    return ""


def _the_status_thrown(thrown: str) -> str:
    """The status an error thrown on purpose names, a rate limit as 429; ""."""
    unlinked = re.sub(r"https?://\S+", "", thrown)
    if m := _A_STATUS_THROWN.search(unlinked):
        return m.group(1) or m.group(2)
    return RATE_LIMITED if _A_LIMIT_THROWN.search(unlinked) else ""


def where_it_threw(message: Any) -> str:
    """`file:line` of the frame a failure was raised at - a script runtime's first frame, Python's last, a library's
    frames passed over; or ""."""
    message = _plain(message)
    for m in _A_SCRIPT_FRAME.finditer(message):
        if not _A_LIBRARY.search(m.group(1)):
            return f"{PurePosixPath(m.group(1)).name}:{m.group(2)}"
    frames = [(m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
              for m in _A_PYTHON_FRAME.finditer(message)]
    frames = [(file, line) for file, line in frames if not _A_LIBRARY.search(file)]
    if frames:
        file, line = frames[-1]
        return f"{PurePosixPath(file).name}:{line}"
    return ""


def where_the_test_was(message: Any) -> str:
    """`file:line` of the outermost frame of the test's own code a failure passed through - the line of the test that
    took the failing step - libraries passed over; or "".

    A script runtime lists the innermost frame first, so its last; Python's traceback the outermost first, so its first.
    Two failures of one test at different lines of one file failed at different steps of it.
    """
    message = _plain(message)
    script = [m for m in _A_SCRIPT_FRAME.finditer(message) if not _A_LIBRARY.search(m.group(1))]
    if script:
        return f"{PurePosixPath(script[-1].group(1)).name}:{script[-1].group(2)}"
    frames = [(m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
              for m in _A_PYTHON_FRAME.finditer(message)]
    frames = [(file, line) for file, line in frames if not _A_LIBRARY.search(file)]
    if frames:
        return f"{PurePosixPath(frames[0][0]).name}:{frames[0][1]}"
    return ""


def _scrubbed(text: str) -> str:
    """`text` without what varies from one test to the next: numbers, quoted values."""
    text = re.sub(r"([`'\"]).*?\1", "#", text)
    return " ".join(re.sub(r"\d+", "#", text).split())[:160]


@dataclass(frozen=True)
class Failure:
    """One failed test as read here: its criterion, the test as the suite's result keeps it, its answer and its step."""

    criterion: str
    test: dict
    answer: str
    #: `file:line` of a step several tests throw at, else "".
    frame: str
    #: `METHOD /resource` of the request it checked, else "".
    request: str
    thrown: str


def answers(tests: Sequence[dict]) -> list[str]:
    """Each failed test's answer, in order: the status its assertion got where it expected another; else the status or
    rate limit an error it threw names; else, for a status-less error thrown at a frame several tests throw at, the
    one status the others at that frame name; else ""."""
    return [failure.answer for failure in read([("", t) for t in tests])]


def read(tests: Iterable[tuple[str, dict]], root: str | Path | None = None) -> list[Failure]:
    """Each (criterion, failed test) read for its answer and its first failing step. Never raises."""
    pairs = [(str(c or ""), t) for c, t in tests if isinstance(t, dict)]
    messages = [_plain(t.get("message")) for _, t in pairs]
    frames = [where_it_threw(m) for m in messages]
    names_at: dict[str, set[str]] = {}
    for (_, t), frame in zip(pairs, frames):
        if frame:
            names_at.setdefault(frame, set()).add(str(t.get("name") or id(t)))
    shared = {frame for frame, names in names_at.items() if len(names) >= LEAST_TESTS}
    thrown = [what_it_threw(m) for m in messages]
    stated = [the_wrong_answer(m) or (_the_status_thrown(th) if th else "") for m, th in zip(messages, thrown)]
    # A status-less error at a shared step follows the refusal the step's other tests name, when they name only one.
    named_at: dict[str, set[str]] = {}
    for frame, answer in zip(frames, stated):
        if frame in shared and answer:
            named_at.setdefault(frame, set()).add(answer)
    found: list[Failure] = []
    for (criterion, test), message, frame, threw, answer in zip(pairs, messages, frames, thrown, stated):
        if not answer and frame in shared and len(named_at.get(frame, ())) == 1:
            answer = next(iter(named_at[frame]))
        found.append(Failure(
            criterion=criterion, test=test, answer=answer, frame=frame if frame in shared else "",
            request=_the_request(message, test, root) if answer[:1] in "45" and answer[:3].isdigit() else "",
            thrown=threw,
        ))
    return found


def _resource(path: str) -> str:
    """The leading resource of a path, its shared lead kept: `/api/items/3/notes` -> `/api/items`; or ""."""
    path = re.sub(r"^https?://[^/]+", "", path.strip())
    # A base a test puts first (`${BASE}/items`) is the service's address, not a segment.
    path = re.sub(r"^(?:\$\{[^}]*\}|\{[^}]*\})+", "", path)
    path = _A_PLACEHOLDER.sub(":id", path.split("?", 1)[0].split("#", 1)[0])
    kept: list[str] = []
    for segment in (s for s in path.split("/") if s):
        if _AN_ID.match(segment):
            break
        kept.append(segment)
        if not _A_SHARED_LEAD.match(segment):
            break
    if not kept or _A_SHARED_LEAD.match(kept[-1]):
        return ""
    return "/" + "/".join(kept)


def _a_request_in(text: str) -> tuple[str, str]:
    """(METHOD, path) of the last request `text` makes before its marked failing line; ("", "")."""
    marked = _THE_MARKED_LINE.search(text)
    before = text[:marked.end() + 200] if marked else text
    calls = [(m.group(1).upper(), m.group(3)) for m in _A_REQUEST_CALL.finditer(before)]
    calls += [(m.group(1).upper(), m.group(2)) for m in _A_LOGGED_REQUEST.finditer(text)]
    return calls[-1] if calls else ("", "")


def _the_source_line(test: dict, message: str, root: str | Path | None) -> tuple[Path, int] | None:
    """The test's own file under `root` and the line of it the failure names; None."""
    if root is None:
        return None
    own = PurePosixPath(str(test.get("file") or "")).name
    for m in _A_SCRIPT_FRAME.finditer(message):
        if not own or PurePosixPath(m.group(1)).name == own:
            for candidate in _under(Path(root), m.group(1), str(test.get("file") or "")):
                return candidate, int(m.group(2))
    return None


def _under(root: Path, *paths: str) -> Iterable[Path]:
    """Each of `paths` as a file under `root`, trying it as given, then by its trailing parts."""
    for path in paths:
        parts = PurePosixPath(path.replace("file://", "")).parts if path else ()
        for start in range(len(parts)):
            candidate = root.joinpath(*[p for p in parts[start:] if p != "/"])
            try:
                if candidate.is_file() and root.resolve() in candidate.resolve().parents:
                    yield candidate
                    return
            except OSError:
                continue


def _the_request(message: str, test: dict, root: str | Path | None) -> str:
    """`METHOD /resource` of the request a failed test checked: from its message, else from the lines of its own file
    above the failing line; ""."""
    method, path = _a_request_in(message)
    if not path and (at := _the_source_line(test, message, root)):
        try:
            lines = at[0].read_text(encoding="utf-8", errors="replace").splitlines()
            method, path = _a_request_in("\n".join(lines[max(0, at[1] - _LINES_BACK):at[1]]))
        except OSError:
            method, path = "", ""
    resource = _resource(path) if path else ""
    return f"{method} {resource}" if resource and method else ""


@dataclass(frozen=True)
class Cluster:
    """Failed tests that stop at one step with one answer."""

    #: `test-utils.js:75` for a shared frame; `/api/items` for a path nobody serves (any method); `POST /api/items`.
    step: str
    #: The status, or what the step threw (numbers and quoted values taken out).
    answer: str
    helper: bool
    failures: tuple[Failure, ...]

    @property
    def criteria(self) -> list[str]:
        return list(dict.fromkeys(f.criterion for f in self.failures if f.criterion))

    @property
    def status(self) -> str:
        return self.answer if re.fullmatch(r"[1-5]\d\d", self.answer) else ""


def clusters(failing: Sequence[dict], root: str | Path | None = None, *, total: int | None = None) -> list[Cluster]:
    """The steps at which at least `LEAST_TESTS` failed tests of `LEAST_CRITERIA` criteria or more, and one in `ONE_IN`
    of all failed tests, stop with one answer; largest first. Different answers or steps are never one cluster. A path
    nobody serves answers 404 whatever the method, so a 404's step is its resource alone. Never raises."""
    try:
        pairs = [(str(entry.get("id") or ""), t) for entry in failing for t in (entry.get("tests") or [])
                 if isinstance(t, dict) and t.get("outcome") == "failed"]
        failures = read(pairs, root)
        whole = total if total is not None else len(failures)
        groups: dict[tuple[str, str, bool], list[Failure]] = {}
        for failure in failures:
            if failure.frame:
                answer = failure.answer or (_scrubbed(failure.thrown) if failure.thrown else "")
                if answer:
                    groups.setdefault((failure.frame, answer, True), []).append(failure)
                continue
            if failure.request and failure.answer:
                method, resource = failure.request.split(" ", 1)
                step = resource if failure.answer == "404" else f"{method} {resource}"
                groups.setdefault((step, failure.answer, False), []).append(failure)
        found = [
            Cluster(step=step, answer=answer, helper=helper, failures=tuple(members))
            for (step, answer, helper), members in groups.items()
            if len(members) >= LEAST_TESTS and len({m.criterion for m in members}) >= LEAST_CRITERIA
            and len(members) * ONE_IN >= whole
        ]
        return sorted(found, key=lambda c: -len(c.failures))
    except Exception:  # noqa: BLE001 - each criterion keeps its own defect
        return []


__all__ = [
    "ANY_STATUS", "Cluster", "Failure", "LEAST_CRITERIA", "LEAST_TESTS", "ONE_IN", "RATE_LIMITED", "answers",
    "clusters", "read", "the_wrong_answer", "what_it_threw", "where_it_threw", "where_the_test_was",
]
