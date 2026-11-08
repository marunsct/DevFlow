"""The architect's interface contract, locked with the suite and checked at release (plan items C and J.3).

Owner decision 2026-10-18. The release trusted one artifact, the locked suite,
and a suite's repairs can weaken it. These checks are compiled from a
contract the architect writes in the specification - one strict line per
route, page control or command, each naming its criterion - so they need no
model and cannot be loosened by repairing the suite:

    AC-3 GET /api/notes -> 200
    AC-1 page /login textbox "Email"
    AC-5 command notes add milk -> exit 0

Compiled from the contract, never from the brief's prose: a check made up from
a criterion's words would probe a route nobody specified. The contract is
recorded when the suite is locked. At release, a check that fails is a
completion gap for the first runs, not a block - a page control behind a
sign-in, say, is not shown at a bare visit, and the record says so.

Routes and page controls run through the pack's probe runner (Playwright,
which starts the product the same way for every web pack). Commands run as
themselves, through the sandbox, on every pack. A line nothing can check - a
route on a pack with no probe runner, a route with a parameter in it - is said
to be unchecked at release, never left out in silence (Initiative AU).
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: The criterion a line serves; a line naming several serves the first. One
#: specification wrote "AC-1 AC-2 AC-3 POST /auth/register -> 201".
_CRITERION = r"((?:AC|CR)-\d+)(?:[\s,]+(?:AC|CR)-\d+)*"
#: One or more statuses: `-> 200`, `-> 200 or 404`, `-> 200 or 400/422 or 404`.
_HTTP = re.compile(_CRITERION + r"\s+(GET|POST|PUT|PATCH|DELETE)\s+(/\S*)\s*->\s*(\d{3}(?:\s*(?:or|/|,|\|)\s*\d{3})*)\s*$")
#: A page control: the role and its name last, with any words naming where on
#: the page it sits between the path and the role - one specification wrote 26
#: of its page lines as `page /dashboard form textbox "Title"`, and every one
#: was set aside as following no form.
#: An HTTP line naming several methods or saying what it is for between its path and its arrow:
#: `AC-3, AC-4 GET/PUT/DELETE /notes/{id} for non-existent -> 404`. Measured on one run: six of eight lines were
#: written so, none was read, and none was checked at release.
_HTTP_SEVERAL = re.compile(
    _CRITERION + r"\s+((?:GET|POST|PUT|PATCH|DELETE)(?:\s*/\s*(?:GET|POST|PUT|PATCH|DELETE))*)\s+(/\S*)"
    r"((?:\s+(?!->)\S+)*?)\s*->\s*(\d{3}(?:\s*(?:or|/|,|\|)\s*\d{3})*)\s*$"
)
#: An HTTP line with no criterion before it: `GET /health -> 200`.
_HTTP_WITHOUT_ITS_CRITERION = re.compile(
    r"((?:GET|POST|PUT|PATCH|DELETE)(?:\s*/\s*(?:GET|POST|PUT|PATCH|DELETE))*)\s+(/\S*)"
    r"((?:\s+(?!->)\S+)*?)\s*->\s*(\d{3}(?:\s*(?:or|/|,|\|)\s*\d{3})*)\s*$"
)
#: Ids before a route that are no criterion's: `AC-health GET /health -> 200`.
_IDS_THAT_ARE_NOT_NUMBERS = re.compile(
    r"^(?:(?:AC|CR)-[A-Za-z][\w-]*[\s,]+)+(?=(?:GET|POST|PUT|PATCH|DELETE)\b)"
)
_PAGE = re.compile(_CRITERION + r"\s+page\s+(/\S*)\s+(?:[\w-]+\s+)*?([a-z]+)\s+\"([^\"]+)\"\s*$")
_COMMAND = re.compile(_CRITERION + r"\s+command\s+(.+?)\s*->\s*exit\s+(\d+)\s*$")

#: A control named by its element where the contract asks for its ARIA role.
_ROLE_OF_THE_ELEMENT = {"textarea": "textbox", "select": "combobox"}

#: A parenthesised note after the arrow with a status before it: "-> 201 (with Note object) or 400".
_A_NOTE_AMONG_THE_STATUSES = re.compile(r"(->\s*\d{3}(?:\s*(?:or|/|,|\|)\s*\d{3})*)\s*\([^()]*\)")
#: A parenthesised note at the end of a line: "-> 200 (updates the field)".
_A_TRAILING_NOTE = re.compile(r"\s+\([^()]*\)\s*$")

#: Where the compiled checks are written, inside the project, for one release run.
CHECK_DIR = "harness-contract"
CONFIG_FILE = "playwright.contract.config.mjs"
REPORT_FILE = "test-results/contract.xml"

#: Checks run at most, so a long contract stays a seconds-long release step.
MOST_CHECKS = 40

#: A route with a parameter in it, `/api/notes/{id}` or `/notes/:id`: probed as
#: written it asks for a record called "{id}", so it is unchecked rather than failed.
_A_TEMPLATE = re.compile(r"\{[^}]*\}|/:[A-Za-z_]")


#: What a route's parameter is probed with: a record no product has, which a product that keeps its contract answers
#: with the 4xx the line allows. Measured on several runs: every `/notes/:id` line went unchecked at release.
A_RECORD_THAT_DOES_NOT_EXIST = "999999999"


def _allowed(check: "Check") -> tuple[int, ...]:
    return tuple(check.statuses or ()) or ((check.status,) if check.status else ())


def _a_refusal_is_allowed(check: "Check") -> bool:
    return any(400 <= code < 500 for code in _allowed(check))


def checkable(checks: list["Check"]) -> list["Check"]:
    """The HTTP and page checks a bare probe can settle, a route's parameters filled with a record that does not exist.

    A route with a parameter, or a write that succeeds only with a body, is checkable when the line allows the 4xx a
    product answers such a probe with; otherwise it stays unchecked, as before.
    """
    from dataclasses import replace as _with

    kept: list[Check] = []
    for check in checks:
        if check.kind not in ("http", "page"):
            continue
        templated = bool(_A_TEMPLATE.search(check.path))
        if (templated or _a_write_that_needs_a_body(check)) and not (check.kind == "http" and _a_refusal_is_allowed(check)):
            continue
        path = re.sub(r"\{[^}]*\}|:[A-Za-z_]\w*", A_RECORD_THAT_DOES_NOT_EXIST, check.path) if templated else check.path
        kept.append(_with(check, path=path))
    return kept


#: A route's parameter, for reading its name.
_A_PARAMETER_NAMED = re.compile(r"\{([^}]*)\}|:([A-Za-z_]\w*)")


def with_a_record_made_first(checks: list["Check"], bodies: list[Any]) -> list["Check"]:
    """The route lines with one parameter that allow only a success, each set to make its record through the contract's write line.

    Measured on recent runs: `AC-3 GET /notes/{id} -> 200` is never probed at release, because no record called
    `999999999` exists and the line allows no 404. The record comes from the contract's own `POST` on the path before
    the parameter, with the specification's example bodies tried in turn; a line with no such write stays unchecked.
    """
    from dataclasses import replace as _with

    writes = {c.path.rstrip("/") for c in checks if c.kind == "http" and c.method == "POST" and _a_write_that_needs_a_body(c)
              and not _A_TEMPLATE.search(c.path)}
    made: list[Check] = []
    for check in checks:
        if check.kind != "http" or check.note or _a_refusal_is_allowed(check) or len(_A_PARAMETER_NAMED.findall(check.path)) != 1:
            continue
        before = _A_PARAMETER_NAMED.split(check.path, maxsplit=1)[0].rstrip("/")
        if before in writes:
            made.append(_with(check, made_through=before, bodies=json.dumps(bodies)))
    return made


def _a_made_record_test(title: str, check: "Check") -> str:
    """The test of `check` on a record made through its write line; skipped, and so unchecked, when none could be made."""
    found = _A_PARAMETER_NAMED.search(check.path)
    name = (found.group(1) or found.group(2)) if found else "id"
    before, after = check.path[:found.start()], check.path[found.end():]
    sent = ", data: bodies[0] ?? {}" if check.method in ("PUT", "PATCH") else ""
    return (
        f"test({title}, async ({{ request }}) => {{\n"
        f"  const bodies = {check.bodies or '[]'};\n"
        "  let made;\n"
        "  for (const data of [...bodies, {}]) {\n"
        f"    made = await request.fetch({_js(check.made_through)}, {{ method: 'POST', data, failOnStatusCode: false }});\n"
        "    if (made.ok()) break;\n"
        "  }\n"
        f"  test.skip(!made.ok(), {_js(MADE_NO_RECORD)});\n"
        "  const record = await made.json().catch(() => ({}));\n"
        f"  const id = record[{_js(name)}] ?? record.id ?? record.data?.id;\n"
        f"  test.skip(id === undefined, {_js(MADE_NO_RECORD)});\n"
        f"  const answer = await request.fetch({_js(before)} + encodeURIComponent(id) + {_js(after)}, "
        f"{{ method: {_js(check.method)}{sent}, failOnStatusCode: false }});\n"
        f"  expect({_js(list(_allowed(check)))}).toContain(answer.status());\n"
        "});\n"
    )


#: Why an emptied-field test was skipped: the write refused its example body whole, so that body is not one it takes.
#: Measured on one run: an emptied `title` was sent to `/signup`, which takes no title, and passed for it.
NOT_THIS_WRITE_S_BODY = "the write refused the example body as it is, so it does not take that body"
#: Why a test of a line on a made record was skipped.
MADE_NO_RECORD = "the contract's write line made no record to probe with"


def example_bodies(specification: Any) -> list[dict[str, Any]]:
    """The literal JSON examples the specification's request and data shapes give, those about a request first; [] if none."""
    decoder = json.JSONDecoder()
    about_a_request: list[dict[str, Any]] = []
    others: list[dict[str, Any]] = []
    for field in ("data_contracts", "api_and_event_contracts"):
        for entry in getattr(specification, field, None) or ():
            text, at = str(entry), 0
            while (at := text.find("{", at)) >= 0:
                try:
                    value, length = decoder.raw_decode(text[at:])
                except ValueError:
                    at += 1
                    continue
                at += length
                if isinstance(value, dict) and value:
                    kept = about_a_request if re.search(r"request|body|input|create", text, re.I) else others
                    if value not in kept:
                        kept.append(value)
    return [*about_a_request, *others][:MOST_EXAMPLE_BODIES]


#: Tried in turn for one record: each refused try is one more request at a check that takes seconds.
MOST_EXAMPLE_BODIES = 4


def _a_write_that_needs_a_body(check: "Check") -> bool:
    """A `POST`/`PUT`/`PATCH` line that says it succeeds: the probe sends a bare request, which a product that checks
    its input rightly refuses. Measured on one run: `AC-1 POST /notes -> 201` was failed at release for the 422 the
    product gave a request with no title, on a product that passed every hidden test."""
    return check.kind == "http" and check.method in ("POST", "PUT", "PATCH") and 200 <= check.status < 300


@dataclass(frozen=True)
class Check:
    """One line of the contract, parsed."""

    criterion: str
    kind: str  # "http", "page" or "command"
    line: str
    method: str = ""
    path: str = ""
    status: int = 0
    #: Every status the line allows; `status` is the first of them.
    statuses: tuple[int, ...] = ()
    role: str = ""
    name: str = ""
    command: str = ""
    exit_code: int = 0
    #: What the line says it is for, between its path and its arrow ("for non-existent", "with invalid title").
    note: str = ""
    #: The write line's path a record is made through before this check; "" for a check on no record.
    made_through: str = ""
    #: The bodies that write is tried with, as JSON.
    bodies: str = ""
    #: The field the emptied-field probe sends empty; "" for every other check.
    emptied: str = ""


def parse(lines: list[str] | tuple[str, ...]) -> tuple[list[Check], list[str]]:
    """The checks the lines declare, and the lines that follow no form."""
    checks: list[Check] = []
    unreadable: list[str] = []
    for raw in lines or []:
        line = " ".join(str(raw).split()).strip(" -*`")
        # A line the specification quoted whole, `"AC-1 POST /notes -> 201"`: measured on one run, every line of the
        # contract was written so and none was read. Only a quote at both ends goes, so a page line's `"Email"` stays.
        while len(line) > 1 and line[0] == line[-1] and line[0] in "\"'" and line.count(line[0]) % 2 == 0 and not _PAGE.match(line):
            line = line[1:-1].strip(" -*`")
        if not line:
            continue
        # A note after the form says what the line is for, and is no part of
        # the check: one specification wrote "AC-11 PUT /tasks/{id} -> 200
        # (updates reminder_at field)", and the line was dropped at the lock.
        line = _A_TRAILING_NOTE.sub("", line)
        # And one among the statuses: "AC-1 POST /notes -> 201 (with Note object) or 400/422". Measured on one run:
        # four of six lines were written so and none was checked at release.
        while (between := _A_NOTE_AMONG_THE_STATUSES.sub(r"\1", line)) != line:
            line = between
        # Measured on recent runs: `AC-health GET /health -> 200` followed no form, for an id that is no number. It
        # names no criterion of this product, so it is read like a line with none.
        if named_ids_switch.enabled():
            line = _IDS_THAT_ARE_NOT_NUMBERS.sub("", line)
        if match := _HTTP.match(line):
            statuses = tuple(int(code) for code in re.findall(r"\d{3}", match[4]))
            checks.append(Check(match[1], "http", line, method=match[2], path=match[3], status=statuses[0],
                                statuses=statuses))
        elif match := _HTTP_WITHOUT_ITS_CRITERION.match(line):
            # Measured on the held-out family: `GET /health -> 200`, with no criterion before it, was set aside as
            # following no form and never probed. Checked all the same; it charges no criterion.
            statuses = tuple(int(code) for code in re.findall(r"\d{3}", match[4]))
            for method in dict.fromkeys(m.strip() for m in match[1].split("/")):
                checks.append(Check("", "http", line, method=method, path=match[2], status=statuses[0],
                                    statuses=statuses, note=match[3].strip()))
        elif match := _HTTP_SEVERAL.match(line):
            statuses = tuple(int(code) for code in re.findall(r"\d{3}", match[5]))
            for method in dict.fromkeys(m.strip() for m in match[2].split("/")):
                checks.append(Check(match[1], "http", line, method=method, path=match[3], status=statuses[0],
                                    statuses=statuses, note=match[4].strip()))
        elif match := _PAGE.match(line):
            role = _ROLE_OF_THE_ELEMENT.get(match[3], match[3])
            checks.append(Check(match[1], "page", line, path=match[2], role=role, name=match[4]))
        elif match := _COMMAND.match(line):
            checks.append(Check(match[1], "command", line, command=match[2], exit_code=int(match[3])))
        else:
            unreadable.append(line)
    return checks, unreadable


def record_at_lock(repo_root: str | Path, lines: list[str] | tuple[str, ...], *, specification: Any = None) -> list[Check]:
    """Keep the contract beside the locked suite, with the example bodies its write lines can make a record from; what was kept."""
    from app.acceptance import suite

    checks, unreadable = parse(lines)
    state = suite._state(repo_root)  # noqa: SLF001 - one state file for the suite and its contract
    state["interface_contract"] = [asdict(check) for check in checks]
    state["interface_contract_bodies"] = example_bodies(specification)
    # Kept too, so the release names them rather than losing them at the lock.
    state["interface_contract_unreadable"] = list(unreadable)
    suite._save_state(repo_root, state)  # noqa: SLF001
    return checks


def the_unreadable_lines(repo_root: str | Path) -> list[str]:
    """The contract's lines that followed none of its forms at the last lock, or []."""
    from app.acceptance import suite

    return [str(line) for line in suite._state(repo_root).get("interface_contract_unreadable") or []]  # noqa: SLF001


def the_locked_contract(repo_root: str | Path) -> list[Check]:
    """The contract recorded at the last lock, or []."""
    from app.acceptance import suite

    kept = suite._state(repo_root).get("interface_contract") or []  # noqa: SLF001
    return [Check(**item) for item in kept if isinstance(item, dict)]


def _js(text: str) -> str:
    return json.dumps(text)


def playwright_checks(checks: list[Check], bodies: list[Any] | None = None) -> str:
    """A Playwright spec with one test per HTTP or page check; signed in as `pytest_checks` says."""
    tests = []
    for number, check in enumerate(checks, start=1):
        title = _js(f"{f'[{check.criterion}] ' if check.criterion else ''}contract {number}: {check.line}")
        if check.made_through:
            tests.append(_a_made_record_test(title, check))
        elif check.kind == "http":
            signed = "" if any(code in (401, 403) for code in _allowed(check)) else "headers: await signedIn(request), "
            tests.append(
                f"test({title}, async ({{ request }}) => {{\n"
                f"  const answer = await request.fetch({_js(check.path)}, {{ method: {_js(check.method)}, {signed}failOnStatusCode: false }});\n"
                + (f"  expect(answer.status()).toBe({_allowed(check)[0]});\n" if len(_allowed(check)) == 1
                   else f"  expect({_js(list(_allowed(check)))}).toContain(answer.status());\n")
                + "});\n"
            )
        elif check.kind == "page":
            tests.append(
                f"test({title}, async ({{ page }}) => {{\n"
                f"  await page.goto({_js(check.path)});\n"
                f"  await expect(page.getByRole({_js(check.role)}, {{ name: {_js(check.name)}, exact: true }})).toBeVisible();\n"
                "});\n"
            )
    plan = sign_in_plan(checks, bodies)
    source = "import { test, expect } from '@playwright/test';\n\n" + "\n".join(tests)
    if plan is None:
        return source.replace("headers: await signedIn(request), ", "")
    return _with_sign_in_js(source, plan)


#: What the bad-body probe sends with a JSON content type: JSON that stops halfway, so no parser can read it.
A_BODY_NOTHING_CAN_PARSE = '{"unparsable": '
#: Why a bad-body test was skipped when no record was needed: the sign-in refused it, whatever its body.
SIGN_IN_ANSWERED_FIRST = "sign-in answered first, so the product never read the body"
#: How a server-error defect's text says a call was asked with a bad body; `still_raised` reads it back.
SENT_WITH_A_BAD_BODY = "sent with a JSON body that cannot be parsed"


def bad_body_checks(checks: list[Check], bodies: list[Any]) -> tuple[list[Check], list[str]]:
    """(what the bad-body probe asks, the lines it cannot ask and why), one each per `POST`/`PUT`/`PATCH` call of the contract.

    A write on a route with one parameter must reach a real record, or a 404 answers before the body is read: the record
    is made through the contract's write line on the path before the parameter, as `with_a_record_made_first` does, and
    any status the line allows. No such write, or more than one parameter, and the line stays unchecked.
    """
    from dataclasses import replace as _with

    made_by = {c.path.rstrip("/") for c in checks if c.kind == "http" and c.method == "POST" and _a_write_that_needs_a_body(c)
               and not _A_TEMPLATE.search(c.path)}
    asked: list[Check] = []
    unchecked: list[str] = []
    seen: set[tuple[str, str]] = set()
    for check in checks:
        if check.kind != "http" or check.method not in ("POST", "PUT", "PATCH") or (check.method, check.path) in seen:
            continue
        seen.add((check.method, check.path))
        if not _A_TEMPLATE.search(check.path):
            asked.append(check)
            continue
        before = _A_PARAMETER_NAMED.split(check.path, maxsplit=1)[0].rstrip("/")
        if len(_A_PARAMETER_NAMED.findall(check.path)) == 1 and before in made_by:
            asked.append(_with(check, made_through=before, bodies=json.dumps(bodies)))
        else:
            unchecked.append(f"{check.line} (a route with a parameter, and no write line of the contract makes its record)")
    return asked, unchecked


def _a_bad_body_test(title: str, check: Check) -> str:
    """The test sending `check`'s call a body nothing can parse; any answer under 500 passes, the refusal being the product's to choose."""
    target = _js(check.path)
    made = ""
    if check.made_through:
        found = _A_PARAMETER_NAMED.search(check.path)
        name = (found.group(1) or found.group(2)) if found else "id"
        target = f"{_js(check.path[:found.start()])} + encodeURIComponent(id) + {_js(check.path[found.end():])}"
        made = (
            f"  const bodies = {check.bodies or '[]'};\n"
            "  let made;\n"
            "  for (const data of [...bodies, {}]) {\n"
            f"    made = await request.fetch({_js(check.made_through)}, {{ method: 'POST', data, failOnStatusCode: false }});\n"
            "    if (made.ok()) break;\n"
            "  }\n"
            f"  test.skip(!made.ok(), {_js(MADE_NO_RECORD)});\n"
            "  const record = await made.json().catch(() => ({}));\n"
            f"  const id = record[{_js(name)}] ?? record.id ?? record.data?.id;\n"
            f"  test.skip(id === undefined, {_js(MADE_NO_RECORD)});\n"
        )
    return (
        f"test({title}, async ({{ request }}) => {{\n{made}"
        f"  const answer = await request.fetch({target}, {{ method: {_js(check.method)}, "
        "headers: { 'content-type': 'application/json' }, "
        f"data: {_js(A_BODY_NOTHING_CAN_PARSE)}, failOnStatusCode: false }});\n"
        f"  test.skip([401, 403].includes(answer.status()), {_js(SIGN_IN_ANSWERED_FIRST)});\n"
        "  expect(answer.status()).toBeLessThan(500);\n"
        "});\n"
    )


def playwright_bad_body_checks(checks: list[Check]) -> str:
    """A Playwright spec with one bad-body test per check; numbered as `playwright_checks` numbers its own."""
    tests = [
        _a_bad_body_test(_js(f"{f'[{c.criterion}] ' if c.criterion else ''}contract {number}: {c.line}"), c)
        for number, c in enumerate(checks, start=1)
    ]
    return _with_sign_in_js("import { test, expect } from '@playwright/test';\n\n" + "\n".join(tests), sign_in_plan(checks))


#: A rule refusing a field when it is empty, as briefs and criteria say it: "A title that is missing or empty is
#: refused", "An empty or missing `name` is rejected", "The email must not be empty".
_REFUSED_WHEN_EMPTY = (
    re.compile(r"\b(?:a|an|the)\s+`?(\w+)`?\s+(?:field\s+)?(?:that|which)\s+is\s+(?:missing\s+or\s+)?(?:empty|blank)"
               r"\b[^.]*\b(?:refused|rejected)", re.I),
    re.compile(r"\b(?:an?\s+)?(?:empty|blank)\s+(?:or\s+missing\s+)?`?(\w+)`?\s+(?:is|are)\s+(?:refused|rejected)", re.I),
    re.compile(r"\b(?:the\s+)?`?(\w+)`?\s+(?:must|may)\s+not\s+be\s+(?:empty|blank)", re.I),
)


def fields_refused_when_empty(texts: Any) -> list[str]:
    """The fields the specification's rules refuse when empty, in the order first named."""
    found: list[str] = []
    for text in texts or ():
        for rule in _REFUSED_WHEN_EMPTY:
            for match in rule.finditer(str(text)):
                name = match.group(1)
                if name.lower() not in {"it", "that", "this", "one", "request", "value"} and name not in found:
                    found.append(name)
    return found


def emptied_field_checks(checks: list[Check], bodies: list[Any], fields: list[str]) -> tuple[list[Check], list[str]]:
    """(what the emptied-field probe asks, the lines it cannot ask): each write of the contract, once per field the
    specification refuses empty that the example body carries.

    A rule stated once holds for every write: measured on one run, the suite asked it of create only and the product
    accepted an update that emptied the title. The writes are the bad-body probe's, a record made first where needed.
    """
    from dataclasses import replace as _with

    carried = [f for f in fields if any(isinstance(b, dict) and f in b for b in bodies)]
    if not carried:
        return [], []
    writes, unchecked = bad_body_checks(checks, bodies)
    asked = [_with(check, emptied=field, bodies=json.dumps(bodies)) for check in writes for field in carried]
    return asked, unchecked


def _an_emptied_field_test(title: str, check: Check, bodies: list[Any]) -> str:
    """The test sending `check`'s call the example body with `check.emptied` set to "": it must be refused."""
    example = next(b for b in bodies if isinstance(b, dict) and check.emptied in b)
    sent = {**example, check.emptied: ""}
    plain = _with_the_bad_body(check)
    marker = f"data: {_js(A_BODY_NOTHING_CAN_PARSE)}, "
    assert marker in plain
    asked = plain.replace(marker, f"data: {json.dumps(sent)}, ")
    line = next(l for l in asked.splitlines(keepends=True) if l.startswith("  const answer = await request.fetch("))
    first = (line.replace("const answer", "const plain", 1).replace(f"data: {json.dumps(sent)}, ", f"data: {json.dumps(example)}, ")
             + f"  test.skip([401, 403].includes(plain.status()), {_js(SIGN_IN_ANSWERED_FIRST)});\n"
             + f"  test.skip(plain.status() >= 400, {_js(NOT_THIS_WRITE_S_BODY)});\n")
    return asked.replace(line, first + line, 1).replace(
        "  expect(answer.status()).toBeLessThan(500);\n",
        "  expect(answer.status()).toBeGreaterThanOrEqual(400);\n  expect(answer.status()).toBeLessThan(500);\n",
    )


def _with_the_bad_body(check: Check) -> str:
    return _a_bad_body_test("__TITLE__", check)


def playwright_emptied_field_checks(checks: list[Check], bodies: list[Any] | None = None) -> str:
    """A Playwright spec with one emptied-field test per check; numbered as `playwright_checks` numbers its own."""
    tests = []
    for number, c in enumerate(checks, start=1):
        given = bodies if bodies is not None else json.loads(c.bodies or "[]")
        title = _js(f"{f'[{c.criterion}] ' if c.criterion else ''}contract {number}: {c.line} with an empty {c.emptied}")
        tests.append(_an_emptied_field_test("__TITLE__", c, given).replace("__TITLE__", title, 1))
    return _with_sign_in_js("import { test, expect } from '@playwright/test';\n\n" + "\n".join(tests),
                            sign_in_plan(checks, bodies))


def playwright_config(suite_config: str) -> str:
    """A configuration that is the suite's own, pointed at the compiled checks and their own report."""
    return (
        f"import base from './{suite_config}';\n\n"
        "// Written by the harness for one release check, then removed.\n"
        "export default {\n"
        "  ...base,\n"
        f"  testDir: './{CHECK_DIR}',\n"
        "  testMatch: '*.spec.js',\n"
        "  globalSetup: undefined,\n"
        f"  reporter: [['junit', {{ outputFile: '{REPORT_FILE}' }}]],\n"
        "};\n"
    )


#: A write that signs in, and one that makes an account, by their paths.
_SIGNS_IN = re.compile(r"sign[-_]?in|log[-_]?in|sessions?\b|tokens?\b", re.I)
_SIGNS_UP = re.compile(r"sign[-_]?up|register", re.I)
#: A body carrying a secret is a body for signing in.
_SECRETS = ("password", "passcode", "secret")
#: Where a token is found in a sign-in's answer.
_TOKEN_KEYS = ("token", "access_token", "accessToken", "jwt", "id_token")


def sign_in_plan(checks: list[Check], bodies: list[Any] | None = None) -> dict[str, Any] | None:
    """How a body probe signs in first: the contract's own sign-up and sign-in writes and an example body with a secret.

    None when the contract has no sign-in write or no such body. Measured on one run: on an API behind sign-in, the
    emptied-field probe of `POST /items` was answered 401 before the body was read and `PATCH /items/{id}` made no
    record - the writes the probe exists for were never asked. Only the body probes sign in: a bare line of the
    contract ("-> 401") is about the call without one.
    """
    writes = [c for c in checks if c.kind == "http" and c.method == "POST"]
    signin = next((c.path for c in writes if _SIGNS_IN.search(c.path)), "")
    if not signin:
        return None
    signup = next((c.path for c in writes if _SIGNS_UP.search(c.path)), "")
    given: list[Any] = list(bodies or [])
    for check in checks:
        try:
            given += json.loads(check.bodies or "[]")
        except ValueError:
            pass
    body = next((b for b in given if isinstance(b, dict) and any(k in b for k in _SECRETS)), None)
    return {"signup": signup, "signin": signin, "body": body} if body is not None else None


_SIGN_IN_JS = """
const SIGN_IN = %s;
let token;
async function signedIn(request) {
  if (!SIGN_IN) return {};
  if (token === undefined) {
    token = null;
    const suffix = Math.random().toString(36).slice(2, 10);
    const body = { ...SIGN_IN.body };
    for (const key of ['username', 'email', 'name', 'login', 'user']) {
      if (typeof body[key] === 'string') body[key] = body[key].includes('@') ? `probe${suffix}@example.com` : `probe${suffix}`;
    }
    if (SIGN_IN.signup) await request.fetch(SIGN_IN.signup, { method: 'POST', data: body, failOnStatusCode: false });
    const answer = await request.fetch(SIGN_IN.signin, { method: 'POST', data: body, failOnStatusCode: false });
    const found = await answer.json().catch(() => ({}));
    for (const key of %s) {
      const value = found?.[key] ?? found?.data?.[key];
      if (typeof value === 'string') { token = value; break; }
    }
  }
  return token ? { authorization: `Bearer ${token}` } : {};
}
"""


def _with_sign_in_js(source: str, plan: dict[str, Any] | None) -> str:
    """A Playwright body probe whose calls carry a signed-in token when the contract has a sign-in; unchanged otherwise."""
    if plan is None:
        return source
    head = "import { test, expect } from '@playwright/test';\n"
    return source.replace(head, head + _SIGN_IN_JS % (json.dumps(plan), json.dumps(list(_TOKEN_KEYS))), 1).replace(
        "headers: { 'content-type': 'application/json' }",
        "headers: { 'content-type': 'application/json', ...(await signedIn(request)) }",
    ).replace(
        "{ method: 'POST', data, failOnStatusCode: false }",
        "{ method: 'POST', data, headers: await signedIn(request), failOnStatusCode: false }",
    )


#: Where the pytest probe's compiled checks are written: inside the suite's folder, so its kept `conftest.py` starts the
#: service and gives `base_url`, exactly as for the suite. Removed after the run.
PYTEST_PROBE_FILE = "acceptance/test_zz_harness_contract_probe.py"
#: Why a page line is skipped by the pytest probe: it has no browser.
NO_BROWSER = "a page line: this probe sends HTTP requests only"

_PYTEST_PROBE = '''"""Written by the harness for one interface-contract check, then removed."""
import json
import urllib.error
import urllib.parse
import urllib.request
import uuid

import pytest

CASES = json.loads(%r)
SIGN_IN = json.loads(%r)
TOKEN_KEYS = json.loads(%r)
_TOKEN = {}


def _signed_in(base_url):
    if not SIGN_IN:
        return {}
    if "value" not in _TOKEN:
        _TOKEN["value"] = None
        suffix = uuid.uuid4().hex[:8]
        body = dict(SIGN_IN["body"])
        for key in ("username", "email", "name", "login", "user"):
            if isinstance(body.get(key), str):
                body[key] = f"probe{suffix}@example.com" if "@" in body[key] else f"probe{suffix}"
        if SIGN_IN["signup"]:
            _call(base_url, "POST", SIGN_IN["signup"], body)
        _, raw = _call(base_url, "POST", SIGN_IN["signin"], body)
        try:
            found = json.loads(raw or b"{}")
        except ValueError:
            found = {}
        for key in TOKEN_KEYS:
            value = found.get(key) if isinstance(found, dict) else None
            if value is None and isinstance(found, dict) and isinstance(found.get("data"), dict):
                value = found["data"].get(key)
            if isinstance(value, str):
                _TOKEN["value"] = value
                break
    return {"Authorization": "Bearer " + _TOKEN["value"]} if _TOKEN["value"] else {}


def _call(base_url, method, path, body, extra=None):
    data, headers = None, dict(extra or {})
    if body is not None:
        data = (body if isinstance(body, str) else json.dumps(body)).encode()
        headers["content-type"] = "application/json"
    request = urllib.request.Request(base_url.rstrip("/") + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as answer:
            return answer.status, answer.read()
    except urllib.error.HTTPError as answer:
        return answer.code, answer.read()


def _a_record(base_url, case, extra):
    for data in [*case["bodies"], {}]:
        status, raw = _call(base_url, "POST", case["made_through"], data, extra)
        if 200 <= status < 300:
            try:
                record = json.loads(raw or b"{}")
            except ValueError:
                return None
            if not isinstance(record, dict):
                return None
            found = record.get(case["parameter"], record.get("id"))
            if found is None and isinstance(record.get("data"), dict):
                found = record["data"].get("id")
            return found
    return None


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_contract(case, base_url):
    if case["rule"] == "page":
        pytest.skip(%r)
    path = case["path"]
    unsigned = case["rule"] == "allowed" and any(code in (401, 403) for code in case["allowed"])
    extra = {} if unsigned else _signed_in(base_url)
    if case["made_through"]:
        found = _a_record(base_url, case, extra)
        if found is None:
            pytest.skip(%r)
        path = case["before"] + urllib.parse.quote(str(found), safe="") + case["after"]
    if case["rule"] == "refused":
        plain, _ = _call(base_url, case["method"], path, case["example"], extra)
        if plain in (401, 403):
            pytest.skip(%r)
        if plain >= 400:
            pytest.skip(%r)
    status, _ = _call(base_url, case["method"], path, case["send"], extra)
    if case["rule"] == "allowed":
        assert status in case["allowed"], f"Received: {status}"
        return
    if status in (401, 403):
        pytest.skip(%r)
    assert status < 500, f"Received: {status}"
    if case["rule"] == "refused":
        assert status >= 400, f"Received: {status}"
'''


def _pytest_case(number: int, check: Check, title_tail: str = "", rule: str = "allowed", send: Any = None) -> dict:
    found = _A_PARAMETER_NAMED.search(check.path) if check.made_through else None
    bodies = json.loads(check.bodies or "[]") if check.bodies else []
    if rule == "allowed" and check.made_through and check.method in ("PUT", "PATCH"):
        send = (bodies or [{}])[0]
    return {
        "id": f"{f'[{check.criterion}] ' if check.criterion else ''}contract {number}: {check.line}{title_tail}",
        "rule": "page" if check.kind == "page" else rule,
        "method": check.method, "path": check.path, "allowed": list(_allowed(check)), "send": send,
        "made_through": check.made_through if found else "", "bodies": bodies,
        "parameter": (found.group(1) or found.group(2)) if found else "id",
        "before": check.path[:found.start()] if found else "", "after": check.path[found.end():] if found else "",
    }


def _pytest_module(cases: list[dict], plan: dict[str, Any] | None = None) -> str:
    return _PYTEST_PROBE % (json.dumps(cases), json.dumps(plan), json.dumps(list(_TOKEN_KEYS)), NO_BROWSER, MADE_NO_RECORD, SIGN_IN_ANSWERED_FIRST,
                            NOT_THIS_WRITE_S_BODY, SIGN_IN_ANSWERED_FIRST)


def pytest_checks(checks: list[Check], bodies: list[Any] | None = None) -> str:
    """A pytest module with one case per HTTP or page check, numbered as `playwright_checks` numbers its own.

    A line is asked signed in when the contract has a sign-in, unless the statuses it allows are a sign-in refusal:
    measured on one run, `GET /items -> 200` behind sign-in was asked unsigned, answered 401, and was reported at
    release as a contract the product does not keep.
    """
    return _pytest_module([_pytest_case(n, c) for n, c in enumerate(checks, start=1)], sign_in_plan(checks, bodies))


def pytest_bad_body_checks(checks: list[Check]) -> str:
    """A pytest module sending each check's call a body nothing can parse; any answer under 500 passes."""
    return _pytest_module([_pytest_case(n, c, rule="under_500", send=A_BODY_NOTHING_CAN_PARSE)
                           for n, c in enumerate(checks, start=1)], sign_in_plan(checks))


def pytest_emptied_field_checks(checks: list[Check], bodies: list[Any] | None = None) -> str:
    """A pytest module sending each check's call its example body with `emptied` set to ""; it must be refused."""
    cases = []
    for number, check in enumerate(checks, start=1):
        given = bodies if bodies is not None else json.loads(check.bodies or "[]")
        example = next(b for b in given if isinstance(b, dict) and check.emptied in b)
        case = _pytest_case(number, check, f" with an empty {check.emptied}", rule="refused",
                            send={**example, check.emptied: ""})
        cases.append({**case, "example": example})
    return _pytest_module(cases, sign_in_plan(checks, bodies))


#: The probe runners a pack can declare (`StackPack.probe_runner`): what compiles
#: the contract's lines into checks, and the command that runs them. Everything
#: specific to one tool is here and in its two functions above.
PROBE_RUNNERS: dict[str, dict[str, Any]] = {
    "playwright": {
        "checks": playwright_checks,
        "bad_body_checks": playwright_bad_body_checks,
        "emptied_field_checks": playwright_emptied_field_checks,
        "config": playwright_config,
        "command": ("npx", "playwright", "test", "--config", CONFIG_FILE),
        "base_config": "playwright.config.js",
    },
    # A suite run by pytest with the kept conftest's `base_url` (the Python service packs): the checks go in the
    # suite's own folder and its setup starts the service.
    "pytest": {
        "checks": pytest_checks,
        "bad_body_checks": pytest_bad_body_checks,
        "emptied_field_checks": pytest_emptied_field_checks,
        "file": PYTEST_PROBE_FILE,
        "command": (".venv/bin/python", "-m", "pytest", PYTEST_PROBE_FILE, "-q", "-p", "no:cacheprovider",
                    f"--junitxml={REPORT_FILE}"),
    },
}


def _what_git_sees_changed(root: Path) -> dict[str, str]:
    """Path -> its `git status` code, for every file that differs from the last commit; {} when unknown."""
    from app.tools.version_control import _git

    done = _git(root, "status", "--porcelain", "--untracked-files=all")
    if done is None or done.returncode != 0:
        return {}
    return {line[3:].strip(): line[:2] for line in done.stdout.splitlines() if len(line) > 3}


def _put_back_what_the_commands_wrote(root: Path, before: dict[str, str]) -> None:
    """Remove the files the contract's commands created and restore the ones they changed. Never raises.

    A command line runs the product itself - `notes add milk` adds a note - and
    the release must not ship what its own check wrote.
    """
    from app.tools.version_control import _git

    try:
        for path, code in _what_git_sees_changed(root).items():
            if path in before:
                continue
            if code == "??":
                (root / path).unlink(missing_ok=True)
            else:
                _git(root, "checkout", "--", path)
    except Exception:  # noqa: BLE001 - a file left behind is better than a release that fails
        logger.debug("Could not put back what the contract's commands wrote", exc_info=True)


def _the_commands_kept(checks: list[Check], root: Path, project: str, runner: Any) -> tuple[list[str], list[str]]:
    """(failures, unchecked) for the contract's command lines, each run as itself in the project."""
    failed: list[str] = []
    unchecked: list[str] = []
    before = _what_git_sees_changed(root) if checks else {}
    try:
        _run_each_command(checks, project, runner, failed, unchecked)
    finally:
        if checks:
            _put_back_what_the_commands_wrote(root, before)
    return failed, unchecked


def _run_each_command(checks: list[Check], project: str, runner: Any, failed: list[str], unchecked: list[str]) -> None:
    import shlex

    for check in checks:
        try:
            argv = shlex.split(check.command)
        except ValueError:
            unchecked.append(f"{check.line} (the command does not parse)")
            continue
        outcome = runner(argv, "test", project) or {}
        if outcome.get("error") and "returncode" not in outcome:
            unchecked.append(f"{check.line} ({str(outcome['error'])[:120]})")
            continue
        try:
            code = int(str(outcome.get("returncode")))
        except ValueError:
            unchecked.append(f"{check.line} (no exit code came back)")
            continue
        if code != check.exit_code:
            failed.append(f"[{check.criterion}] {check.line} - it exited {code}")


def _the_probe_s_report(project: Path, project_name: str, probe: dict[str, Any], web: list[Check], run: Any,
                        compiled_by: str = "checks", bodies: list[Any] | None = None) -> Any:
    """The runner's report of `web` checked against the product, the probe's own files removed after."""
    from app.acceptance import junit

    if probe.get("file"):
        # A runner whose checks sit in the suite's own folder and need no configuration of their own.
        target = project / probe["file"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((probe[compiled_by](web, bodies) if compiled_by == "checks" else probe[compiled_by](web)), encoding="utf-8")
    else:
        target = None
        (project / CHECK_DIR).mkdir(parents=True, exist_ok=True)
        (project / CHECK_DIR / "contract.spec.js").write_text((probe[compiled_by](web, bodies) if compiled_by == "checks" else probe[compiled_by](web)), encoding="utf-8")
        (project / CONFIG_FILE).write_text(probe["config"](probe["base_config"]), encoding="utf-8")
    report_file = project / REPORT_FILE
    junit.clear(report_file)
    try:
        run(list(probe["command"]), "test", project_name)
        return junit.read(report_file)
    finally:
        if target is not None:
            target.unlink(missing_ok=True)
        else:
            shutil.rmtree(project / CHECK_DIR, ignore_errors=True)
            (project / CONFIG_FILE).unlink(missing_ok=True)


#: What a failed status check reports it was given: `Received: 500`.
#: The status a failed probe received: `Received: 415`, or with `toContain` `Expected value: 415` against the array
#: of allowed statuses, which is how Playwright words the probe's own `expect([200, 404]).toContain(status)`.
_RECEIVED = re.compile(r"(?:Received|Expected value):\s*(?:\x1b\[[0-9;]*m)*\s*(\d{3})\b")
#: Which check a test of the probe is: `contract 4:` in its title.
_CHECK_NUMBER = re.compile(r"\bcontract (\d+):")
#: How a defect raised for a server error at the contract's checks begins; `still_raised` reads it back.
SERVER_FAILED = "The server fails on a request it should answer or refuse:"


def server_errors(repo_root: str | Path, *, runner: Any = None) -> list[tuple[Check, int]] | None:
    """Each HTTP line of the locked contract a bare request makes the product answer with a 5xx, with that status.

    None when the checks cannot run (no locked contract, no probe runner on the pack, no report). Measured on one
    run: a bare `POST /notes` and `PUT /notes/:id` - no body - answered 500 where the contract gives 400 and 404;
    the checks ran only at release, so the crash shipped as a gap no fixer was ever given. Only a 5xx is named: a
    4xx other than the line's may be a refusal the product makes first (a body checked before the record), but no
    line of any contract is a server failing.
    """
    try:
        from app.acceptance import suite
        from app.stacks import contract

        from app.acceptance import probe_coverage

        root = Path(repo_root)
        lines = the_locked_contract(root)[:MOST_CHECKS]
        web = [c for c in checkable(lines) if c.kind == "http"]
        asked_lines = {c.line for c in web}
        not_asked = [(c.line, probe_coverage.reason_a_line_is_not_probed(c)) for c in lines if c.line not in asked_lines]
        found = contract.the_pack(root)
        probe = PROBE_RUNNERS.get(found[0].probe_runner) if found else None
        if not web or probe is None:
            if lines:
                probe_coverage.write(root, "server_error", probe_coverage.coverage(
                    considered=len(lines), asked=[],
                    not_asked=not_asked + [(c.line, "no runner on this stack probes it") for c in web],
                ))
            return None
        project_name = str((found[1] or {}).get("project") or "")
        run = runner or suite._sandbox_runner(root)  # noqa: SLF001 - the suite's own runner
        report = _the_probe_s_report(root / project_name, project_name, probe, web, run,
                                     bodies=list(suite._state(root).get("interface_contract_bodies") or []))  # noqa: SLF001
        probe_coverage.write(root, "server_error", probe_coverage.coverage(
            considered=len(lines), asked=web, report=report if report is not None and report.found else None,
            not_asked=not_asked, check_of=lambda test: _the_check_of(test, web),
        ))
        if report is None or not report.found:
            return None
        errors: list[tuple[Check, int]] = []
        for test in report.tests:
            check, status = _the_check_of(test, web), _a_server_error(test)
            if getattr(test, "outcome", "") == "failed" and check is not None and status:
                errors.append((check, status))
        return errors
    except Exception:  # noqa: BLE001 - a check that cannot run says nothing
        logger.debug("Could not probe the interface contract for server errors", exc_info=True)
        return None


def bad_body_errors(repo_root: str | Path, *, runner: Any = None) -> list[tuple[Check, int]] | None:
    """Each write call of the locked contract that answers a 5xx to a JSON body nothing can parse, with that status.

    None when off or when the checks cannot run. What could not be asked is kept for the release to name. Measured on
    one product: a write route answered 500 to unparsable JSON, the locked suite did not ask, and a hidden quality test
    found it. Any answer under 500 passes.
    """
    if not bad_body_switch.enabled():
        return None
    try:
        from app.acceptance import suite
        from app.stacks import contract

        root = Path(repo_root)
        state = suite._state(root)  # noqa: SLF001 - one state file for the suite and its contract
        asked, unchecked = bad_body_checks(the_locked_contract(root)[:MOST_CHECKS],
                                           list(state.get("interface_contract_bodies") or []))
        found = contract.the_pack(root)
        probe = PROBE_RUNNERS.get(found[0].probe_runner) if found else None
        if probe is None:
            unchecked += [f"{c.line} (no runner on this stack probes it)" for c in asked]
            asked = []
        errors: list[tuple[Check, int]] | None = []
        if asked:
            project_name = str((found[1] or {}).get("project") or "")
            run = runner or suite._sandbox_runner(root)  # noqa: SLF001 - the suite's own runner
            report = _the_probe_s_report(root / project_name, project_name, probe, asked, run, "bad_body_checks")
            if report is None or not report.found:
                errors = None
                unchecked += [f"{c.line} (the probe's runner wrote no report)" for c in asked]
            else:
                for test in report.tests:
                    check, status = _the_check_of(test, asked), _a_server_error(test)
                    if check is None:
                        continue
                    outcome = getattr(test, "outcome", "")
                    if outcome == "skipped":
                        unchecked.append(f"{check.line} ({MADE_NO_RECORD}, or {SIGN_IN_ANSWERED_FIRST})" if check.made_through
                                         else f"{check.line} ({SIGN_IN_ANSWERED_FIRST})")
                    elif outcome == "failed" and status:
                        errors.append((check, status))
                    elif outcome == "failed":
                        unchecked.append(f"{check.line} (the probe got no status back)")
        else:
            errors = None
        state = suite._state(root)  # noqa: SLF001 - read again: the runner's suite calls may have saved it
        state["interface_contract_bad_body_unchecked"] = list(dict.fromkeys(unchecked))
        suite._save_state(root, state)  # noqa: SLF001
        from app.acceptance import probe_coverage

        # The skipped and unasked lines are already in `unchecked`, each with its reason; the count probed is what
        # was asked less those.
        probe_coverage.write(root, "bad_body", {
            "considered": len(the_locked_contract(root)[:MOST_CHECKS]),
            "asked": len(asked),
            "probed": max(0, len(asked) - sum(1 for u in unchecked if any(u.startswith(c.line) for c in asked))),
            "skipped": [{"line": u.rsplit(" (", 1)[0], "reason": u.rsplit(" (", 1)[-1].rstrip(")")} for u in dict.fromkeys(unchecked)],
        })
        return errors
    except Exception:  # noqa: BLE001 - a check that cannot run says nothing
        logger.debug("Could not probe the contract with a bad body", exc_info=True)
        return None


#: What a failed refusal check reports it was given: `Received: 200`.
_RECEIVED_ANY = re.compile(r"Received:\s*(?:\x1b\[[0-9;]*m)*\s*(\d{3})\b")


def emptied_field_errors(repo_root: str | Path, *, runner: Any = None) -> list[tuple[Check, int]] | None:
    """Each write call of the locked contract that accepts a field the criteria refuse empty, with the status it gave.

    None when the checks cannot run. Measured on one run: a missing or empty title was refused on create only, the
    product accepted an update that emptied it, and a hidden test failed while the locked suite passed. Any 4xx passes.
    """
    try:
        from app.acceptance import suite
        from app.stacks import contract

        root = Path(repo_root)
        fields = fields_refused_when_empty([c.text for c in suite.criteria(root)])
        state = suite._state(root)  # noqa: SLF001 - one state file for the suite and its contract
        bodies = list(state.get("interface_contract_bodies") or [])
        from app.acceptance import probe_coverage

        lines = the_locked_contract(root)[:MOST_CHECKS]
        asked, unasked = emptied_field_checks(lines, bodies, fields)
        not_asked = [(u.rsplit(" (", 1)[0], u.rsplit(" (", 1)[-1].rstrip(")")) for u in unasked]
        if not fields:
            not_asked.append(("(every write)", "no criterion refuses a field empty"))
        elif not asked:
            not_asked.append(("(every write)", "no example body carries a field the criteria refuse empty"))
        found = contract.the_pack(root)
        probe = PROBE_RUNNERS.get(found[0].probe_runner) if found else None
        if not asked or probe is None or "emptied_field_checks" not in probe:
            if lines:
                probe_coverage.write(root, "emptied_field", probe_coverage.coverage(
                    considered=len(lines), asked=[],
                    not_asked=not_asked + [(c.line, "no runner on this stack probes it") for c in asked],
                ))
            return None
        project_name = str((found[1] or {}).get("project") or "")
        run = runner or suite._sandbox_runner(root)  # noqa: SLF001 - the suite's own runner
        report = _the_probe_s_report(root / project_name, project_name, probe, asked, run, "emptied_field_checks")
        probe_coverage.write(root, "emptied_field", probe_coverage.coverage(
            considered=len(lines), asked=asked, report=report if report is not None and report.found else None,
            not_asked=not_asked, check_of=lambda test: _the_check_of(test, asked),
        ))
        if report is None or not report.found:
            return None
        accepted: list[tuple[Check, int]] = []
        for test in report.tests:
            check = _the_check_of(test, asked)
            received = _RECEIVED_ANY.search(str(getattr(test, "message", "") or ""))
            if check is not None and getattr(test, "outcome", "") == "failed" and received \
                    and 200 <= int(received.group(1)) < 300:
                accepted.append((check, int(received.group(1))))
        return accepted
    except Exception:  # noqa: BLE001 - a check that cannot run says nothing
        logger.debug("Could not probe the contract with an emptied field", exc_info=True)
        return None


def emptied_field_description(accepted: list[tuple[Check, int]]) -> str:
    """The defect's description for writes that accepted a field the criteria refuse empty."""
    calls = "; ".join(f"`{c.method} {c.path}` with an empty `{c.emptied}` answered {status}" for c, status in accepted[:6])
    criteria = ", ".join(sorted({c.criterion for c, _ in accepted if c.criterion}))
    return (f"{EMPTIED_FIELD_ACCEPTED} {calls}. The criteria refuse that field empty on every write"
            f"{f' ({criteria})' if criteria else ''}, not only where the suite tried it.")


#: How the emptied-field defect's text starts; the round reads it to raise it once.
EMPTIED_FIELD_ACCEPTED = "A write accepts a field the specification refuses empty:"


def what_the_bad_body_probe_did_not_ask(repo_root: str | Path) -> list[str]:
    """A completion gap naming the write lines the last bad-body probe could not ask; [] when none or it is off. Never raises."""
    try:
        from app.acceptance import suite

        if not bad_body_switch.enabled():
            return []
        lines = [str(line) for line in suite._state(repo_root).get("interface_contract_bad_body_unchecked") or []]  # noqa: SLF001
        if not lines:
            return []
        return [(f"{len(lines)} write line(s) of the interface contract were not asked with an unparsable body: "
                 + "; ".join(lines[:5]) + ("; ..." if len(lines) > 5 else ""))[:800]]
    except Exception:  # noqa: BLE001 - the release says nothing it cannot measure
        logger.debug("Could not read what the bad-body probe left unasked", exc_info=True)
        return []


#: Statuses only a particular request draws: a conflict with what is stored, a body too large, a body of the wrong
#: type, too many requests. Measured on one run: `AC-18 POST /notes -> 413` was failed at release for the 400 the
#: product rightly gave the probe's empty body. 401 and 403 are not here: a bare request is what draws them.
_DRAWN_BY_A_PARTICULAR_REQUEST = frozenset({409, 413, 415, 429})


def _only_what_a_bare_request_cannot_draw(check: Check) -> bool:
    return bool(_allowed(check)) and set(_allowed(check)) <= _DRAWN_BY_A_PARTICULAR_REQUEST


#: What a product rightly answers a write that has no body, before it looks anything up.
#: 415 too: a product that checks the content type before the body refuses the probe's bare request with it. Measured
#: on one run: `AC-4 PUT /notes/:id -> 200 | 404` was failed at release for a 415, at full hidden marks.
_A_REFUSED_BODY = frozenset({400, 415, 422})


def _a_bodiless_write_refused_first(check: Check, test: Any) -> bool:
    """Whether the probe's bodiless write was refused for its body before the record was looked up.

    Measured on one run: `AC-11 PUT /notes/999 -> 404` was failed at release for the 400 a product that checks the
    body first gives the probe's empty request; either order keeps the contract. Nor does it matter which refusal:
    `AC-7 POST /notes -> 400` was failed for the 422 given to a body that was not there, on a brief allowing either.
    """
    received = _RECEIVED.search(str(getattr(test, "message", "") or ""))
    return (check.method in ("POST", "PUT", "PATCH") and received is not None
            and int(received.group(1)) in _A_REFUSED_BODY)


def _the_check_of(test: Any, web: list[Check]) -> Check | None:
    """The check a test of the probe is, by `contract N:` in its title; None when it names none."""
    number = _CHECK_NUMBER.search(str(getattr(test, "name", "") or ""))
    return web[int(number.group(1)) - 1] if number and 0 < int(number.group(1)) <= len(web) else None


def _a_server_error(test: Any) -> int:
    """The 5xx a failed test of the probe received, or 0."""
    received = _RECEIVED.search(str(getattr(test, "message", "") or ""))
    return int(received.group(1)) if received and int(received.group(1)) >= 500 else 0


def _the_call(check: Check) -> str:
    """`POST /notes`, as the line names it, with no criterion: a defect naming one is judged by that criterion's tests."""
    return f"{check.method} {check.path}"


def server_error_description(errors: list[tuple[Check, int]], bad_body: list[tuple[Check, int]] | None = None) -> str:
    """The defect's description for `errors`: each call, the status it gave and what the contract gives; and for each of
    `bad_body`, the call that failed on a body it could not parse."""
    each = "; ".join([
        *(f"`{_the_call(check)}` sent with no body answered {status} where the contract gives "
          f"{' or '.join(map(str, _allowed(check)))}"
          for check, status in errors[:6]),
        *(f"`{_the_call(check)}` {SENT_WITH_A_BAD_BODY} answered {status} where a refusal under 500 was due"
          for check, status in (bad_body or [])[:6]),
    ])
    return (
        f"{SERVER_FAILED} {each}. A request the product cannot use - no body, a body that is not JSON, a record "
        "that does not exist - is answered with the status the contract gives for it, never by the server failing."
    )


def still_raised(repo_root: str | Path, description: str, *, runner: Any = None) -> bool | None:
    """Whether a server-error defect with this description would be raised again now; None when it is not one or the checks cannot run."""
    text = str(description or "")
    if not text.startswith(SERVER_FAILED):
        return None
    # A call may be named for either request; each kind is settled by asking the same request again.
    answers: list[bool] = []
    if "sent with no body" in text:
        errors = server_errors(repo_root, runner=runner)
        if errors is not None:
            answers.append(any(f"`{_the_call(check)}` sent with no body" in text for check, _ in errors))
    if SENT_WITH_A_BAD_BODY in text:
        if not bad_body_switch.enabled():
            # Switched off in mid-run: nothing can settle it, and an open defect would never close.
            answers.append(False)
        else:
            errors = bad_body_errors(repo_root, runner=runner)
            if errors is not None:
                answers.append(any(f"`{_the_call(check)}` {SENT_WITH_A_BAD_BODY}" in text for check, _ in errors))
    return any(answers) if answers else None


def what_the_contract_checks_find(repo_root: str | Path, *, runner: Any = None) -> list[str]:
    """A completion gap for each contract check the product fails at release, and one for what went unchecked; [] when none."""
    try:
        from app.acceptance import junit, suite
        from app.stacks import contract

        root = Path(repo_root)
        # Read again with the forms as they are now: a line set aside at the
        # lock may be one a later reading takes.
        read_now, still_unread = parse(the_unreadable_lines(root))
        locked = [*the_locked_contract(root), *read_now][:MOST_CHECKS]
        # Lines no check can be compiled from: said at release, never dropped
        # in silence. Measured on one run: 32 of 58 lines at the lock.
        unreadable = [f"{line} (follows none of the contract's three forms)" for line in still_unread]
        if not locked:
            return (
                [f"{len(unreadable)} line(s) of the interface contract were not checked at release: "
                 + "; ".join(unreadable[:5]) + ("; ..." if len(unreadable) > 5 else "")]
                if unreadable else []
            )
        found = contract.the_pack(root)
        record = found[1] if found else (contract.read(root) or {})
        project_name = str(record.get("project") or "")
        project = root / project_name
        run = runner or suite._sandbox_runner(root)  # noqa: SLF001 - the suite's own runner
        probe = PROBE_RUNNERS.get(found[0].probe_runner) if found else None
        web = checkable(locked)
        if record_first_switch.enabled():
            state = suite._state(root)  # noqa: SLF001 - one state file for the suite and its contract
            web += with_a_record_made_first(locked, list(state.get("interface_contract_bodies") or []))
        settled = {c.line for c in web}
        templated = [c for c in locked if c.kind in ("http", "page") and _A_TEMPLATE.search(c.path) and c.line not in settled]
        writes = [c for c in locked if _a_write_that_needs_a_body(c) and c not in templated and c.line not in settled]
        unchecked = [
            *unreadable,
            *(f"{c.line} (a route with a parameter in it)" for c in templated),
            *(f"{c.line} (a write that succeeds only with a body; the probe sends none)" for c in writes),
        ]
        if probe is None:
            unchecked += [f"{c.line} (no runner on this stack probes a {c.kind} line)" for c in web]
            web = []
        report = _the_probe_s_report(
            project, project_name, probe, web, run,
            bodies=list(suite._state(Path(repo_root)).get("interface_contract_bodies") or []),  # noqa: SLF001
        ) if web else None
        failures, not_run = _the_commands_kept([c for c in locked if c.kind == "command"], root, project_name, run)
        unchecked += not_run
    except Exception:  # noqa: BLE001 - the release says nothing it cannot measure
        logger.debug("Could not run the interface contract's checks", exc_info=True)
        return []
    gaps: list[str] = what_the_bad_body_probe_did_not_ask(repo_root)
    if report is not None and not report.found:
        gaps.append("The interface contract's checks could not run at release: their runner wrote no report.")
    elif report is not None:
        failed = [t for t in report.tests if getattr(t, "outcome", "") not in ("passed", "skipped")]
        # A line that says what it is about ("(duplicate) -> 409", "with an invalid title -> 400") is about a request
        # the probe does not send: its bare request proves only that the server does not fail on it.
        about_another_request = [t for t in failed if (check := _the_check_of(t, web)) is not None
                                 and (check.note or _only_what_a_bare_request_cannot_draw(check)
                                      or _a_bodiless_write_refused_first(check, t))
                                 and not _a_server_error(t)]
        failed = [t for t in failed if t not in about_another_request]
        unchecked += list(dict.fromkeys(
            f"{c.line} ({MADE_NO_RECORD})"
            for t in report.tests if getattr(t, "outcome", "") == "skipped"
            and (c := _the_check_of(t, web)) is not None and c.made_through))
        unchecked += list(dict.fromkeys(
            f"{c.line} (the probe sends a bare request; the line is about {c.note or 'a request it does not send'})"
            for c in (_the_check_of(t, web) for t in about_another_request) if c is not None))
        logger.info("Interface contract at release: %d of %d check(s) failed", len(failed), len(report.tests))
        gaps += [
            (
                f"At release the product does not keep its interface contract: {t.name}"
                + (" - at a bare visit; the control may be shown only to a signed-in user" if " page /" in t.name else "")
            )[:400]
            for t in failed[:10]
        ]
    gaps += [f"At release the product does not keep its interface contract: {failure}"[:400] for failure in failures[:10]]
    if unchecked:
        gaps.append(
            f"{len(unchecked)} line(s) of the interface contract were not checked at release: "
            + "; ".join(unchecked[:5]) + ("; ..." if len(unchecked) > 5 else "")
        )
    return gaps


class _ServerErrorsAtARound:
    """`CONTRACT_SERVER_ERRORS_AT_A_ROUND` as the switch registry reads one: off in code, the compose file turns it on."""

    ON_BY_DEFAULT = False
    #: What the admin page says this switch does.
    explanation = ("When a test round finds the locked suite green, the interface contract's checks are run against "
                   "the product, and a 5xx any of them gets is raised as a defect. Measured on one run: a bare POST "
                   "and PUT answered 500, found only at release, and shipped as a gap.")

    @staticmethod
    def enabled() -> bool:
        from app.switches import is_on

        return is_on("CONTRACT_SERVER_ERRORS_AT_A_ROUND", _ServerErrorsAtARound.ON_BY_DEFAULT)


server_errors_at_a_round_switch = _ServerErrorsAtARound()


class _Experiment:
    """One of plan item 17's switches, as the switch registry reads one: off until measured."""

    ON_BY_DEFAULT = False

    def __init__(self, name: str, explanation: str) -> None:
        self.name, self.explanation = name, explanation

    def enabled(self) -> bool:
        from app.switches import is_on

        return is_on(self.name, self.ON_BY_DEFAULT)


named_ids_switch = _Experiment(
    "CONTRACT_NON_NUMERIC_IDS",
    "A contract line whose id is no number (`AC-health GET /health -> 200`) is read and checked, charging no criterion.",
)
record_first_switch = _Experiment(
    "CONTRACT_PROBE_WITH_A_RECORD",
    "At release, a route line with a parameter that allows only a success is probed on a record made through the "
    "contract's own write line, instead of being left unchecked.",
)
probe_at_lock_switch = _Experiment(
    "CONTRACT_PROBE_AT_LOCK",
    "When the suite is locked and a product exists, the contract's checks run; a 5xx is raised as a defect in the next "
    "test round, green or not.",
)
unread_at_review_switch = _Experiment(
    "CONTRACT_UNREAD_LINES_AT_REVIEW",
    "The architect's review is given the contract lines the harness cannot read, instead of the release reporting them.",
)
bad_body_switch = _Experiment(
    "CONTRACT_PROBE_WITH_A_BAD_BODY",
    "When a test round finds the locked suite green, each POST, PUT and PATCH line of the contract is sent a JSON body "
    "nothing can parse; a 5xx is raised as a defect, and any other answer passes.",
)


def probe_at_the_lock(repo_root: str | Path, *, runner: Any = None) -> list[tuple[Check, int]]:
    """Run the contract's checks as the suite is locked, where a product exists, and keep any 5xx for the next round; what was found.

    Measured on one run: a bare POST and PUT answered 500, and the round's probe asks only when the suite is green, so
    a product that a re-locked suite found red kept its crash until the suite was green. The scaffold's stub is no
    product: at a first lock, nothing has been built for a request to reach. Never raises.
    """
    try:
        from app.acceptance import suite
        from app.stacks.scaffold import entrypoint_is_still_the_stub

        if not probe_at_lock_switch.enabled() or entrypoint_is_still_the_stub(repo_root):
            return []
        errors = server_errors(repo_root, runner=runner) or []
        state = suite._state(repo_root)  # noqa: SLF001 - one state file for the suite and its contract
        state["interface_contract_errors_at_lock"] = [[asdict(check), status] for check, status in errors]
        suite._save_state(repo_root, state)  # noqa: SLF001
        return errors
    except Exception:  # noqa: BLE001 - a check that cannot run says nothing
        logger.debug("Could not probe the contract at the lock", exc_info=True)
        return []


def errors_found_at_the_lock(repo_root: str | Path) -> list[tuple[Check, int]]:
    """What `probe_at_the_lock` kept, taken: the next round raises it once, and the checks settle it. Never raises."""
    try:
        from app.acceptance import suite

        state = suite._state(repo_root)  # noqa: SLF001 - one state file for the suite and its contract
        kept = state.pop("interface_contract_errors_at_lock", None)
        if kept is None:
            return []
        suite._save_state(repo_root, state)  # noqa: SLF001
        return [(Check(**{**item, "statuses": tuple(item.get("statuses") or ())}), int(status)) for item, status in kept]
    except Exception:  # noqa: BLE001 - nothing kept is nothing to raise
        logger.debug("Could not read what the lock's probe found", exc_info=True)
        return []


def unread_lines_finding(lines: list[str] | tuple[str, ...]) -> str:
    """What the architect's review is told about contract lines that follow none of the forms; "" when all are read."""
    unread = parse(lines)[1]
    if not unread:
        return ""
    return (
        f"{len(unread)} line(s) of the interface contract follow none of its forms, so nothing can check them: "
        + "; ".join(f"`{line}`" for line in unread[:8])
        + (f"; and {len(unread) - 8} more" if len(unread) > 8 else "")
        + "."
    )
