"""A record deleted twice answers not-found the second time, and a long text written is read back whole.

Measured: a notes service passed every hidden acceptance test and lost two hidden quality tests no locked test and no
harness probe asked - a record deleted a second time was answered 204 where the contract gives 404, and a long body
of many lines was not read back as it was written. Earlier runs of other families lost similar round trips: what was
stored was not what was read back. The edge probe sends a deleted id only to see it answered under 500, and a long
value of one line. This probe holds the product to two round trips compiled from the locked contract, with no model:

- deleted twice: for each `DELETE` route on one record whose lines give a success and a not-found status (404 or
  410), a record is made through the contract's create line, deleted, and deleted again. The second answer must not
  be a success nor a server error; the contract's `GET` of that record, when it has one, must not read it back.
- kept whole: for the create line and the example body it takes, each free-text field (not an id, a secret, an
  address or a date) is sent `A_LONG_TEXT` - many lines of ordinary text, under common body-size limits - and the
  record is read back through the contract's `GET` of one record, else its list. A refusal is the product's choice
  and never judged; only a value accepted and read back otherwise, or a read that fails, is.

Anything it cannot settle is skipped with its reason: no create line, no id in the answer, a sign-in answered first,
nothing read back. A quality check, so always on: asked at a green round (`workflow`) and again at release
(`probes_at_release`); each run's coverage is in `.harness/contract-probe.json` as `round_trip`.
"""
from __future__ import annotations

import json
import logging
import re
from functools import partial
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: How the defect's description begins; `still_raised`, the release and the fix order read it back.
ROUND_TRIPS_FAILED = "A record does not read back as it was written or deleted:"

#: What a failed test of the probe throws before its finding, as JSON.
MARKER = "ROUND TRIP:"

#: Not-found statuses a `DELETE` line may give for a record no longer there.
NOT_FOUND = (404, 410)

#: A long text of ordinary lines: 400 lines, about 20,000 characters, under the common body-size limits (100 kB and above) and
#: past the lengths a column or a line-based store cuts at. Lines are numbered so a reordering shows too; it starts and
#: ends on a letter, so a product trimming the spaces around a value is not taken for one cutting it.
A_LONG_TEXT = "\n".join(f"Line {n:03d} of an ordinary text that is kept whole." for n in range(1, 401))

#: The fields of a long value at most per create line.
MOST_FIELDS = 6
#: Tests compiled at most, so the probe stays a seconds-long step.
MOST_CASES = 12

#: Words of a field's name that say it is not free text: an id, a secret, an address, a date, a fixed set of values.
_NOT_FREE_TEXT = frozenset({
    "id", "ids", "uuid", "guid", "key", "password", "passcode", "secret", "token", "hash", "email", "mail", "url",
    "uri", "link", "href", "website", "site", "homepage", "domain", "host", "ip", "phone", "tel", "mobile", "slug",
    "date", "time", "at", "on", "timestamp", "color", "colour", "status", "state", "type", "kind", "role", "lang",
    "language", "locale", "code", "currency", "country", "zip", "postal", "path", "file", "image", "avatar", "icon",
    "version", "priority", "format", "mime", "username", "login",
})
_WORDS = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])")

#: Why a test was skipped, as the coverage records it.
TOOK_NO_EXAMPLE_BODY = "the create line took none of the example bodies"
NO_FREE_TEXT = "the example body the create line took has no free-text field"
NOTHING_READ_BACK = "no long value was both accepted and read back with its field"
FIRST_DELETE_REFUSED = "the first delete of the record made was not answered with a success"

#: Which test of the probe a report's test is: `round trip 3:` in its title.
_CASE_NUMBER = re.compile(r"\bround trip (\d+):")


def free_text_fields(body: Any) -> list[str]:
    """The fields of `body` holding text a person writes - not an id, a secret, an address, a date or a fixed value."""
    if not isinstance(body, dict):
        return []
    return [name for name, value in body.items() if isinstance(value, str)
            and not any(word.lower() in _NOT_FREE_TEXT for word in _WORDS.findall(str(name)))][:MOST_FIELDS]


def _the_examples(bodies: list[Any]) -> list[dict[str, Any]]:
    from app.acceptance import interface_contract as ic

    # A body carrying a secret is a sign-in's, sent by the sign-in plan.
    return [b for b in bodies or [] if isinstance(b, dict) and b and not any(k in b for k in ic._SECRETS)]  # noqa: SLF001


def round_trip_cases(lines: list[Any], bodies: list[Any]) -> tuple[list[dict[str, Any]], list[Any], list[tuple[str, str]]]:
    """(the tests the probe runs, the contract lines they ask, each other line it considered and why it left it)."""
    from app.acceptance import concurrent_write_probe, edge_probe
    from app.acceptance import interface_contract as ic

    lines = [ic._a_literal_id_as_a_parameter(c) for c in lines if getattr(c, "kind", "") == "http"]  # noqa: SLF001
    examples = _the_examples(bodies)
    templated = ic._A_TEMPLATE  # noqa: SLF001

    def signs_in(path: str) -> bool:
        return bool(ic._SIGNS_IN.search(path) or ic._SIGNS_UP.search(path))  # noqa: SLF001

    creates = {c.path.rstrip("/"): c for c in reversed(lines) if c.method == "POST" and not templated.search(c.path)
               and 200 <= c.status < 300 and not signs_in(c.path)}
    lists = {c.path.rstrip("/"): c.path for c in lines if c.method == "GET" and not templated.search(c.path)}
    # A route on one record, by method: the path before its parameter, after it, the parameter's name, every status.
    on_one: dict[tuple[str, str], dict[str, Any]] = {}
    for check in lines:
        parameter = edge_probe._one_parameter(check.path)  # noqa: SLF001 - one reading of a route's parameter
        if parameter is None or parameter[1].strip("/"):
            continue
        at = on_one.setdefault((check.method, parameter[0].rstrip("/")), {
            "check": check, "path": check.path, "before": parameter[0], "after": parameter[1],
            "parameter": parameter[2], "statuses": set()})
        at["statuses"].update(ic._allowed(check))  # noqa: SLF001
    cases: list[dict[str, Any]] = []
    asked: list[Any] = []
    left: list[tuple[str, str]] = []

    def add(check: Any, case: dict[str, Any]) -> None:
        number = len(cases) + 1
        cases.append({**case, "id": f"round trip {number}: {check.method} {check.path} {case['what']}",
                      "number": len(asked)})
        asked.append(check)

    for (method, made_at), route in on_one.items():
        if method != "DELETE":
            continue
        check, statuses = route["check"], route["statuses"]
        not_found = sorted(s for s in statuses if s in NOT_FOUND)
        if not not_found or not any(200 <= s < 300 for s in statuses):
            left.append((check.line, "its lines give no success and not-found status to hold a second delete to"))
            continue
        if made_at not in creates:
            left.append((check.line, "no create line on its path makes a record to delete"))
            continue
        read = on_one.get(("GET", made_at))
        add(check, {"kind": "deleted_twice", "what": "sent twice to one record", "method": "DELETE",
                    "shown": check.path, "create": made_at, "bodies": [*examples, {}], "before": route["before"],
                    "after": route["after"], "parameter": route["parameter"], "not_found": not_found,
                    "read": read["path"] if read else "", "read_before": read["before"] if read else "",
                    "read_after": read["after"] if read else ""})
    for made_at, check in creates.items():
        read = on_one.get(("GET", made_at))
        listed = lists.get(made_at, "")
        given = [{"body": b, "fields": fields} for b in examples if (fields := free_text_fields(b))]
        if not read and not listed:
            left.append((check.line, "no read of one record nor list on its path to read a long value back"))
            continue
        if not given:
            left.append((check.line, "no example body with a free-text field to send a long value in"))
            continue
        add(check, {"kind": "kept_whole", "what": "with a long text in each free-text field", "method": "POST",
                    "shown": check.path, "create": made_at, "given": given, "value": A_LONG_TEXT,
                    "parameter": read["parameter"] if read else concurrent_write_probe._the_id_name(check, lines),  # noqa: SLF001
                    "read": read["path"] if read else "", "read_before": read["before"] if read else "",
                    "read_after": read["after"] if read else "", "list": "" if read else listed})
    return cases[:MOST_CASES], asked[:MOST_CASES], left


_PYTEST_TAIL = '''

ROUND_TRIPS = json.loads(%r)
MARKER = %r
SKIPPED = json.loads(%r)


def _ask(base_url, method, path, body, extra):
    try:
        return _call(base_url, method, path, body, extra)
    except Exception:
        return 0, b""


def _json(raw):
    try:
        return json.loads(raw or b"null")
    except ValueError:
        return None


def _said(raw):
    return " ".join((raw or b"").decode("utf-8", "replace")[:200].split())


def _record_of(found):
    if isinstance(found, dict) and "id" not in found and isinstance(found.get("data"), dict):
        return found["data"]
    return found


def _id_of(found, name):
    record = _record_of(found)
    if not isinstance(record, dict):
        return None
    value = record.get(name, record.get("id"))
    return None if value is None else str(value)


def _at(before, after, value):
    return before + urllib.parse.quote(str(value), safe="") + after


def _read_back(base_url, case, made, extra):
    """(the read's status, the record read back or None)."""
    if case["read"]:
        status, raw = _ask(base_url, "GET", _at(case["read_before"], case["read_after"], made), None, extra)
        return status, (_record_of(_json(raw)) if 200 <= status < 300 else None)
    status, raw = _ask(base_url, "GET", case["list"], None, extra)
    found = _json(raw) if 200 <= status < 300 else None
    if isinstance(found, dict):
        found = next((v for v in found.values() if isinstance(v, list)), None)
    items = found if isinstance(found, list) else []
    return status, next((r for r in items if isinstance(r, dict) and _id_of(r, case["parameter"]) == made), None)


def _deleted_twice(base_url, case, extra):
    made = None
    for data in case["bodies"]:
        status, raw = _ask(base_url, "POST", case["create"], data, extra)
        if status in (401, 403):
            pytest.skip(SKIPPED["signed"])
        if 200 <= status < 300:
            made = _id_of(_json(raw), case["parameter"])
            break
    if made is None:
        pytest.skip(SKIPPED["made"])
    path = _at(case["before"], case["after"], made)
    first, _ = _ask(base_url, "DELETE", path, None, extra)
    if not 200 <= first < 300:
        pytest.skip(SKIPPED["first"])
    second, raw = _ask(base_url, "DELETE", path, None, extra)
    found = {"kind": "deleted_twice", "first": first, "second": second, "said": _said(raw),
             "not_found": case["not_found"]}
    bad = second == 0 or second >= 500 or 200 <= second < 300
    if case["read"]:
        read, raw = _ask(base_url, "GET", _at(case["read_before"], case["read_after"], made), None, extra)
        if read == 0 or read >= 500 or 200 <= read < 300:
            found.update(read=read, read_said=_said(raw))
            bad = True
    return found if bad else None


def _kept_whole(base_url, case, extra):
    body = None
    for given in case["given"]:
        status, _ = _ask(base_url, "POST", case["create"], given["body"], extra)
        if status in (401, 403):
            pytest.skip(SKIPPED["signed"])
        if 200 <= status < 300:
            body = given
            break
    if body is None:
        pytest.skip(SKIPPED["took"])
    value, lost, read_back = case["value"], [], 0
    for name in body["fields"]:
        status, raw = _ask(base_url, "POST", case["create"], {**body["body"], name: value}, extra)
        made = _id_of(_json(raw), case["parameter"]) if 200 <= status < 300 else None
        if made is None:
            continue
        read, record = _read_back(base_url, case, made, extra)
        if read == 0 or read >= 500:
            lost.append({"field": name, "created": status, "read": read})
        elif isinstance(record, dict) and name in record:
            read_back += 1
            kept = record[name]
            if kept != value:
                text = kept if isinstance(kept, str) else json.dumps(kept)
                at = next((i for i, (a, b) in enumerate(zip(text, value)) if a != b), min(len(text), len(value)))
                lost.append({"field": name, "created": status, "read": read, "kept_length": len(text),
                             "kept_lines": text.count("\\n") + 1, "differs_at": at,
                             "kept_there": text[max(0, at - 20):at + 40]})
    if lost:
        return {"kind": "kept_whole", "sent_length": len(value), "sent_lines": value.count("\\n") + 1, "lost": lost}
    if not read_back:
        pytest.skip(SKIPPED["nothing"])
    return None


@pytest.mark.parametrize("case", ROUND_TRIPS, ids=[case["id"] for case in ROUND_TRIPS])
def test_round_trip(case, base_url):
    extra = _signed_in(base_url)
    found = (_deleted_twice if case["kind"] == "deleted_twice" else _kept_whole)(base_url, case, extra)
    assert found is None, MARKER + " " + json.dumps(found)
'''


def _skipped() -> dict[str, str]:
    from app.acceptance import interface_contract as ic

    return {"signed": ic.SIGN_IN_ANSWERED_FIRST, "made": ic.MADE_NO_RECORD, "first": FIRST_DELETE_REFUSED,
            "took": TOOK_NO_EXAMPLE_BODY, "nothing": NOTHING_READ_BACK}


def pytest_round_trip_checks(cases: list[dict[str, Any]], plan: dict[str, Any] | None = None) -> str:
    """A pytest module with one test per case, using the contract probe's own calls and sign-in."""
    from app.acceptance import interface_contract as ic

    head = ic._PYTEST_PROBE.split("@pytest.mark.parametrize", 1)[0]  # noqa: SLF001 - its calls and its sign-in
    head = head % (json.dumps([]), json.dumps(plan), json.dumps(list(ic._TOKEN_KEYS)))  # noqa: SLF001
    return head + _PYTEST_TAIL % (json.dumps(cases), MARKER, json.dumps(_skipped()))


_JS_HELPERS = """
const ROUND_TRIP = %s;
const SKIPPED = %s;
function parsed(text) { try { return JSON.parse(text); } catch { return null; } }
function said(text) { return String(text || '').slice(0, 200).replace(/\\s+/g, ' ').trim(); }
function recordOf(found) {
  return found && typeof found === 'object' && !Array.isArray(found) && !('id' in found) && found.data
    && typeof found.data === 'object' ? found.data : found;
}
function idOf(found, name) {
  const record = recordOf(found);
  if (!record || typeof record !== 'object') return null;
  const value = record[name] ?? record.id;
  return value === undefined || value === null ? null : String(value);
}
async function ask(request, method, path, body, headers) {
  const options = { method, headers: { ...headers }, failOnStatusCode: false };
  if (body !== null) {
    options.headers['content-type'] = 'application/json';
    options.data = Buffer.from(JSON.stringify(body));
  }
  const answer = await request.fetch(path, options).catch(() => null);
  if (!answer) return { status: 0, text: '' };
  return { status: answer.status(), text: await answer.text().catch(() => '') };
}
function at(before, after, value) { return before + encodeURIComponent(String(value)) + after; }
function failed(status) { return status === 0 || status >= 500; }
function ok(status) { return status >= 200 && status < 300; }
async function readBack(request, c, made, headers) {
  if (c.read) {
    const got = await ask(request, 'GET', at(c.read_before, c.read_after, made), null, headers);
    return { status: got.status, record: ok(got.status) ? recordOf(parsed(got.text)) : null };
  }
  const got = await ask(request, 'GET', c.list, null, headers);
  let found = ok(got.status) ? parsed(got.text) : null;
  if (found && typeof found === 'object' && !Array.isArray(found)) found = Object.values(found).find(Array.isArray) ?? null;
  const items = Array.isArray(found) ? found : [];
  return { status: got.status,
           record: items.find((r) => r && typeof r === 'object' && idOf(r, c.parameter) === made) ?? null };
}
async function deletedTwice(request, c, headers) {
  let made = null;
  for (const data of c.bodies) {
    const tried = await ask(request, 'POST', c.create, data, headers);
    test.skip([401, 403].includes(tried.status), SKIPPED.signed);
    if (ok(tried.status)) { made = idOf(parsed(tried.text), c.parameter); break; }
  }
  test.skip(made === null, SKIPPED.made);
  const path = at(c.before, c.after, made);
  const first = await ask(request, 'DELETE', path, null, headers);
  test.skip(!ok(first.status), SKIPPED.first);
  const second = await ask(request, 'DELETE', path, null, headers);
  const found = { kind: 'deleted_twice', first: first.status, second: second.status, said: said(second.text),
                  not_found: c.not_found };
  let bad = failed(second.status) || ok(second.status);
  if (c.read) {
    const read = await ask(request, 'GET', at(c.read_before, c.read_after, made), null, headers);
    if (failed(read.status) || ok(read.status)) { Object.assign(found, { read: read.status, read_said: said(read.text) }); bad = true; }
  }
  return bad ? found : null;
}
async function keptWhole(request, c, headers) {
  let body = null;
  for (const given of c.given) {
    const tried = await ask(request, 'POST', c.create, given.body, headers);
    test.skip([401, 403].includes(tried.status), SKIPPED.signed);
    if (ok(tried.status)) { body = given; break; }
  }
  test.skip(body === null, SKIPPED.took);
  const value = c.value;
  const lost = [];
  let readBackCount = 0;
  for (const name of body.fields) {
    const made = await ask(request, 'POST', c.create, { ...body.body, [name]: value }, headers);
    const id = ok(made.status) ? idOf(parsed(made.text), c.parameter) : null;
    if (id === null) continue;
    const back = await readBack(request, c, id, headers);
    if (failed(back.status)) {
      lost.push({ field: name, created: made.status, read: back.status });
    } else if (back.record && typeof back.record === 'object' && name in back.record) {
      readBackCount += 1;
      const kept = back.record[name];
      if (kept !== value) {
        const text = typeof kept === 'string' ? kept : JSON.stringify(kept);
        let i = 0;
        while (i < text.length && i < value.length && text[i] === value[i]) i += 1;
        lost.push({ field: name, created: made.status, read: back.status, kept_length: text.length,
                    kept_lines: text.split('\\n').length, differs_at: i, kept_there: text.slice(Math.max(0, i - 20), i + 40) });
      }
    }
  }
  if (lost.length) return { kind: 'kept_whole', sent_length: value.length, sent_lines: value.split('\\n').length, lost };
  test.skip(readBackCount === 0, SKIPPED.nothing);
  return null;
}
"""

_JS_TEST = """test(%s, async ({ request }) => {
  const c = %s;
  const headers = typeof signedIn === 'function' ? await signedIn(request) : {};
  const found = c.kind === 'deleted_twice' ? await deletedTwice(request, c, headers) : await keptWhole(request, c, headers);
  if (found) throw new Error(ROUND_TRIP + ' ' + JSON.stringify(found));
});
"""


def playwright_round_trip_checks(cases: list[dict[str, Any]], plan: dict[str, Any] | None = None) -> str:
    """A Playwright spec with one test per case, signed in as the contract's other body probes are."""
    from app.acceptance import interface_contract as ic

    js = ic._js  # noqa: SLF001
    head = "import { test, expect } from '@playwright/test';\n"
    tests = [_JS_TEST % (js(case["id"]), json.dumps(case)) for case in cases]
    return ic._with_sign_in_js(head + _JS_HELPERS % (js(MARKER), json.dumps(_skipped())) + "\n" + "\n".join(tests),  # noqa: SLF001
                               plan)


#: The spec or module each probe runner compiles the cases into.
RUNNERS = {"playwright": playwright_round_trip_checks, "pytest": pytest_round_trip_checks}


def what_the_test_found(test: Any) -> dict[str, Any] | None:
    """The finding a failed test of the probe threw after `MARKER`, or None when it threw none."""
    text = str(getattr(test, "message", "") or "")
    at = text.find(MARKER)
    if at < 0:
        return None
    try:
        found, _ = json.JSONDecoder().raw_decode(text[at + len(MARKER):].lstrip())
    except ValueError:
        return None
    return found if isinstance(found, dict) and found.get("kind") else None


def the_case_of(test: Any, cases: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The case a report's test is, by `round trip N:` in its title; None when it names none."""
    number = _CASE_NUMBER.search(str(getattr(test, "name", "") or ""))
    return cases[int(number.group(1)) - 1] if number and 0 < int(number.group(1)) <= len(cases) else None


def round_trip_errors(repo_root: str | Path, *, runner: Any = None) -> list[tuple[dict[str, Any], dict[str, Any]]] | None:
    """Each case the product failed, with what the probe found; None when the probe cannot run. Never raises."""
    try:
        from app.acceptance import interface_contract as ic
        from app.acceptance import probe_coverage, suite
        from app.stacks import contract

        root = Path(repo_root)
        bodies = ic.bodies_for_the_probes(root)
        lines = ic.the_locked_contract(root)[:ic.MOST_CHECKS]
        cases, asked, left = round_trip_cases(lines, bodies)
        found = contract.the_pack(root)
        name = found[0].probe_runner if found else ""
        probe = ic.PROBE_RUNNERS.get(name)
        if not cases or probe is None or name not in RUNNERS:
            if lines:
                probe_coverage.write(root, "round_trip", probe_coverage.coverage(
                    considered=len(lines), asked=[],
                    not_asked=left + [(c.line, "no runner on this stack probes it") for c in asked]))
            return None
        project_name = str((found[1] or {}).get("project") or "")
        run = runner or suite._sandbox_runner(root)  # noqa: SLF001 - the suite's own runner
        compiled = {**probe, "round_trip_checks": partial(RUNNERS[name], plan=ic.sign_in_plan(lines, bodies))}
        report = ic._the_probe_s_report(root / project_name, project_name, compiled, cases, run,  # noqa: SLF001
                                        "round_trip_checks")
        found_report = report if report is not None and report.found else None

        def check_of(test: Any) -> Any:
            case = the_case_of(test, cases)
            return asked[case["number"]] if case is not None else None

        probe_coverage.write(root, "round_trip", probe_coverage.coverage(
            considered=len(lines), asked=asked, report=found_report, not_asked=left, check_of=check_of))
        if found_report is None:
            return None
        errors: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for test in found_report.tests:
            case = the_case_of(test, cases)
            if case is not None and getattr(test, "outcome", "") == "failed" \
                    and (finding := what_the_test_found(test)) is not None:
                errors.append((case, finding))
        return errors
    except Exception:  # noqa: BLE001 - a check that cannot run says nothing
        logger.debug("Could not probe the contract's round trips", exc_info=True)
        return None


def _the_request(case: dict[str, Any]) -> str:
    """`DELETE /notes/{id}` sent twice to one record - as the defect names it, and as `still_raised` reads it back."""
    return f"`{case['method']} {case['shown']}` {case['what']}"


def _answered(status: Any) -> str:
    return "got no answer" if not status else f"answered {status}"


def what_came_back(case: dict[str, Any], found: dict[str, Any]) -> str:
    """What the product did with one round trip, in words."""
    from app.acceptance import what_went_wrong

    if found.get("kind") == "deleted_twice":
        expected = " or ".join(str(s) for s in found.get("not_found") or NOT_FOUND)
        second = int(found.get("second") or 0)
        parts = [f"the first delete answered {found.get('first')}"]
        if second == 0 or second >= 500 or 200 <= second < 300:
            said = f" (it said: {what_went_wrong.the_page_in_words(found['said'])})" if found.get("said") else ""
            parts.append(f"deleting the record that was already deleted {_answered(second)}{said}; "
                         f"the contract says {expected}")
        if "read" in found:
            parts.append(f"`GET {case.get('read')}` of the deleted record then {_answered(found['read'])}, "
                         f"where the contract says {expected}")
        return "; ".join(parts)
    sent = f"{found.get('sent_length')} characters over {found.get('sent_lines')} lines"
    each = []
    for lost in (found.get("lost") or [])[:MOST_FIELDS]:
        made = f"`{lost.get('field')}` sent as {sent} was accepted with {lost.get('created')}"
        read = f"`GET {case.get('read') or case.get('list')}`"
        if "kept_length" not in lost:
            each.append(f"{made}, and {read} then {_answered(lost.get('read'))}")
        else:
            each.append(f"{made}, and {read} read it back as {lost.get('kept_length')} characters over "
                        f"{lost.get('kept_lines')} lines, first differing at character {lost.get('differs_at')} "
                        f"({json.dumps(lost.get('kept_there'))})")
    return "; ".join(each)


def round_trip_description(found: list[tuple[dict[str, Any], dict[str, Any]]]) -> str:
    """The defect's description: each round trip, what came back, and what a product does instead."""
    each = "; ".join(f"{_the_request(case)}: {what_came_back(case, f)}" for case, f in found[:6])
    return (
        f"{ROUND_TRIPS_FAILED} {each}. Deleting a record that is no longer there answers the contract's not-found "
        "status, and a deleted record is no longer read back. A text field is stored whole - every character and line "
        "break as it was sent, with no length cut the specification does not state - and read back exactly; a limit "
        "the specification states is a refusal (400, 413 or 422), never a value cut short."
    )


def still_raised(repo_root: str | Path, description: str, *, runner: Any = None) -> bool | None:
    """Whether a defect with this description would be raised again now; None when it is not this probe's or it cannot run."""
    text = str(description or "")
    if not text.startswith(ROUND_TRIPS_FAILED):
        return None
    errors = round_trip_errors(repo_root, runner=runner)
    if errors is None:
        return None
    return any(_the_request(case) in text for case, _ in errors)


def a_defect(found: list[tuple[dict[str, Any], dict[str, Any]]], owner: str) -> Any:
    """The defect a green round raises for what the probe found."""
    from app.agents.specialists import ReportedDefect
    from app.sprint import cause

    return ReportedDefect(
        description=round_trip_description(found),
        severity="major",
        reproduction_steps="; ".join(
            ("make a record through `POST " + case["create"] + "`, then send `DELETE " + case["shown"] + "` to it twice"
             if case["kind"] == "deleted_twice" else
             "send `POST " + case["shown"] + "` with a text of many lines in a field, then read the record back")
            for case, _ in found[:6]),
        expected_behavior=("the second delete answers the contract's not-found status and the record is no longer "
                           "read; a text accepted is read back exactly as it was sent"),
        actual_behavior="; ".join(f"{_the_request(case)}: {what_came_back(case, f)}" for case, f in found[:6]),
        affected_files=[],
        owner=owner,
        kind=cause.PROBE_FINDING,
        evidence=[cause.a_probe_request("round trips", f"{case['method']} {case['shown']} {case['what']}")
                  for case, _ in found][:cause.MOST_EVIDENCE],
    )


__all__ = [
    "A_LONG_TEXT", "MARKER", "NOT_FOUND", "ROUND_TRIPS_FAILED", "RUNNERS", "a_defect", "free_text_fields",
    "playwright_round_trip_checks", "pytest_round_trip_checks", "round_trip_cases", "round_trip_description",
    "round_trip_errors", "still_raised", "the_case_of", "what_came_back", "what_the_test_found",
]
