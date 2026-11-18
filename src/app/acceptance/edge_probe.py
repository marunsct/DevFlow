"""Requests at the edges of the interface contract, generated from its routes and example bodies (behind `EDGE_PROBE`).

Deep review 2026-11-18, item B1: the hidden quality tests most often lose on requests no locked test sends - a field
missing, null, empty, only spaces, of the wrong type, very long or in another script; an id that is not a number,
negative, huge or already deleted; a delete sent twice. Three hand-built probes covered part of this. This one is
compiled from the locked contract without a model: for each write line, each field of the example body it takes in
each of those forms; for each route with one parameter, each of those ids. Its invariants are narrow, so a brief's
leniency cannot make it red:

- the product never answers 5xx (or nothing);
- a refused create stores nothing: the contract's list route counts the same records after it as before;
- a refused update changes nothing: the record read back is the same as before it;
- a create read back by its id holds each text field as it was sent, a very long one or one in several scripts too.

Whether a form is refused or accepted is the product's own choice; it is never judged. When a test round finds the
locked suite green, a finding is raised as one defect with each request and what the product said; the release asks
again (`probes_at_release`). A probe that sends many requests a round, so a switch until measured.
"""
from __future__ import annotations

import json
import logging
import re
from functools import partial
from pathlib import Path
from typing import Any

from app.switches import is_on

logger = logging.getLogger(__name__)

#: Off in code like every switch; the compose file says whether it is on.
ON_BY_DEFAULT = False

#: How the defect's description begins; the audit's switch-firing check and `still_raised` read it.
EDGE_CASES_FAILED = "Requests at the edges of the interface contract are not handled:"

#: What a failed test of the probe throws before its finding, as JSON.
MARKER = "EDGE CASE:"

#: Requests compiled at most, so the probe stays a seconds-long step.
MOST_CASES = 90

#: A very long text, and one in several scripts: the forms a product truncates or fails to store.
A_LONG_TEXT = "x" * 5000
TEXT_IN_SEVERAL_SCRIPTS = "Zürich – 日本語 – Ελληνικά – ✓ 🚀"
#: Ids no record has that a route must answer under 500: not a number, negative, past any integer column.
IDS = ("not-a-number", "-1", "99999999999999999999")

#: Which case a test of the probe is: `edge 3:` in its title.
_CASE_NUMBER = re.compile(r"\bedge (\d+):")


def enabled() -> bool:
    return is_on("EDGE_PROBE", ON_BY_DEFAULT)


def _forms(value: Any) -> list[tuple[str, str, Any]]:
    """(the form's name, how a defect says it, the value sent; `_MISSING` for no field) for one field's example value."""
    forms: list[tuple[str, str, Any]] = [("missing", "missing", _MISSING), ("null", "null", None)]
    if isinstance(value, str):
        forms += [("empty", "empty", ""), ("blank", "only spaces", "   "), ("wrong type", "a number (12345)", 12345),
                  ("long", f"{len(A_LONG_TEXT)} characters long", A_LONG_TEXT),
                  ("scripts", "in several scripts", TEXT_IN_SEVERAL_SCRIPTS)]
    elif isinstance(value, bool):
        forms.append(("wrong type", 'the text "yes"', "yes"))
    elif isinstance(value, (int, float)):
        forms.append(("wrong type", 'the text "not-a-number"', "not-a-number"))
    else:
        forms.append(("wrong type", 'the text "text"', "text"))
    return forms


_MISSING = object()


def _one_parameter(path: str) -> tuple[str, str, str] | None:
    """(the path before its parameter, after it, the parameter's name) for a route with exactly one; None otherwise."""
    from app.acceptance import interface_contract as ic

    found = list(ic._A_PARAMETER_NAMED.finditer(path))  # noqa: SLF001 - one reading of a route's parameter
    if len(found) != 1:
        return None
    return path[:found[0].start()], path[found[0].end():], found[0].group(1) or found[0].group(2)


def _a_case(number: int, check: Any, what: str, **fields: Any) -> dict[str, Any]:
    return {
        "id": f"edge {number}: {check.method} {check.path} {what}", "method": check.method, "shown": check.path,
        "path": check.path, "what": what, "made_through": "", "id_value": "", "before": "", "after": "",
        "parameter": "id", "bodies": [], "example": None, "send": None, "has_body": False, "list": "", "read": False,
        "round_trip": {}, "get_before": "", "get_after": "", **fields,
    }


def edge_cases(lines: list[Any], bodies: list[Any]) -> list[dict[str, Any]]:
    """The requests the probe sends, compiled from the contract's HTTP lines and example bodies; [] when none apply."""
    from app.acceptance import interface_contract as ic

    lines = [ic._a_literal_id_as_a_parameter(c) for c in lines if getattr(c, "kind", "") == "http"]  # noqa: SLF001
    # A body carrying a secret is a sign-in's, sent by the sign-in plan, not one whose fields the probe varies.
    examples = [b for b in bodies or [] if isinstance(b, dict) and b and not any(k in b for k in ic._SECRETS)]  # noqa: SLF001

    def signs_in(path: str) -> bool:
        return bool(ic._SIGNS_IN.search(path) or ic._SIGNS_UP.search(path))  # noqa: SLF001

    templated = ic._A_TEMPLATE  # noqa: SLF001
    creates = {c.path.rstrip("/") for c in lines if c.method == "POST" and not templated.search(c.path)
               and ic._a_write_that_needs_a_body(c) and not signs_in(c.path)}  # noqa: SLF001
    lists = {c.path.rstrip("/") for c in lines if c.method == "GET" and not templated.search(c.path)}
    routes = {(c.method, c.path) for c in lines}
    reads = {(p[0].rstrip("/"), p) for c in lines if c.method == "GET" and (p := _one_parameter(c.path))}
    read_at = {before: (b, a) for before, (b, a, _) in reads}
    cases: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for check in lines:
        if check.method not in ("POST", "PUT", "PATCH") or (check.method, check.path) in seen or signs_in(check.path):
            continue
        seen.add((check.method, check.path))
        at = {}
        if templated.search(check.path):
            parameter = _one_parameter(check.path)
            if parameter is None or parameter[0].rstrip("/") not in creates:
                continue
            at = {"made_through": parameter[0].rstrip("/"), "before": parameter[0], "after": parameter[1],
                  "parameter": parameter[2], "bodies": examples, "read": ("GET", check.path) in routes}
        a_create = not at and check.path.rstrip("/") in creates
        got = read_at.get(check.path.rstrip("/")) if a_create else None
        back = {"get_before": got[0], "get_after": got[1]} if got else {}
        if a_create and got and examples:
            texts = {k: v for k, v in examples[0].items() if isinstance(v, str)}
            cases.append(_a_case(len(cases) + 1, check, "with its example body", send=examples[0], has_body=True,
                                 round_trip=texts, **back))
        fields: dict[str, dict[str, Any]] = {}
        for example in examples:
            for name in example:
                fields.setdefault(name, example)
        for name, example in fields.items():
            for form, said, value in _forms(example[name]):
                sent = {k: v for k, v in example.items() if k != name}
                if value is not _MISSING:
                    sent[name] = value
                kept = {name: value} if a_create and got and form in ("long", "scripts") else {}
                cases.append(_a_case(len(cases) + 1, check, f"with `{name}` {said}", example=example, send=sent,
                                     has_body=True, list=check.path.rstrip("/") if a_create and check.path.rstrip("/")
                                     in lists else "", round_trip=kept, **(back if kept else {}), **at))
    for check in lines:
        parameter = _one_parameter(check.path)
        if check.method not in ("GET", "PUT", "PATCH", "DELETE") or parameter is None or (check.method, check.path) in seen:
            continue
        seen.add((check.method, check.path))
        before, after, name = parameter
        body = {"send": examples[0] if examples else {}, "has_body": True} if check.method in ("PUT", "PATCH") else {}
        for value in IDS:
            cases.append(_a_case(len(cases) + 1, check, f"at id `{value}`", path=before + value + after, **body))
        if ("DELETE", check.path) in routes and before.rstrip("/") in creates and examples:
            cases.append(_a_case(len(cases) + 1, check, "at an id already deleted", made_through=before.rstrip("/"),
                                 id_value="deleted", before=before, after=after, parameter=name, bodies=examples, **body))
    return cases[:MOST_CASES]


_PYTEST_TAIL = '''

EDGE_CASES = json.loads(%r)
MARKER = %r


def _ask(base_url, method, path, body, extra, has_body):
    try:
        return _call(base_url, method, path, body if has_body else None, extra)
    except Exception:
        return 0, b""


def _json(raw):
    try:
        return json.loads(raw or b"null")
    except ValueError:
        return None


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


def _count(base_url, path, extra):
    status, raw = _ask(base_url, "GET", path, None, extra, False)
    if not 200 <= status < 300:
        return None
    found = _json(raw)
    if isinstance(found, list):
        return len(found)
    if isinstance(found, dict):
        return next((len(v) for v in found.values() if isinstance(v, list)), None)
    return None


def _at(before, after, value):
    return before + urllib.parse.quote(str(value), safe="") + after


@pytest.mark.parametrize("case", EDGE_CASES, ids=[case["id"] for case in EDGE_CASES])
def test_edge(case, base_url):
    extra = _signed_in(base_url)
    path = case["path"]
    if case["made_through"]:
        made = None
        for data in [*case["bodies"], {}]:
            status, raw = _ask(base_url, "POST", case["made_through"], data, extra, True)
            if 200 <= status < 300:
                made = _id_of(_json(raw), case["parameter"])
                break
        if made is None:
            pytest.skip(%r)
        path = _at(case["before"], case["after"], made)
        if case["id_value"] == "deleted":
            _ask(base_url, "DELETE", path, None, extra, False)
    if case["example"] is not None:
        plain, _ = _ask(base_url, case["method"], path, case["example"], extra, True)
        if plain in (401, 403):
            pytest.skip(%r)
        if plain >= 400 or plain == 0:
            pytest.skip(%r)
    before = _count(base_url, case["list"], extra) if case["list"] else None
    held = _ask(base_url, "GET", path, None, extra, False) if case["read"] else None
    status, raw = _ask(base_url, case["method"], path, case["send"], extra, case["has_body"])
    if status in (401, 403):
        pytest.skip(%r)
    found = {"status": status, "said": " ".join((raw or b"").decode("utf-8", "replace")[:200].split())}
    if status == 0 or status >= 500:
        found["kind"] = "server_error"
    elif 400 <= status < 500 and before is not None and (after := _count(base_url, case["list"], extra)) is not None \\
            and after != before:
        found.update(kind="stored_on_refusal", before=before, after=after)
    elif 400 <= status < 500 and held is not None and 200 <= held[0] < 300 \\
            and _json(_ask(base_url, "GET", path, None, extra, False)[1]) != _json(held[1]):
        found["kind"] = "changed_on_refusal"
    elif 200 <= status < 300 and case["round_trip"]:
        made = _id_of(_json(raw), case["parameter"])
        got = _ask(base_url, "GET", _at(case["get_before"], case["get_after"], made), None, extra, False) if made else None
        record = _record_of(_json(got[1])) if got and 200 <= got[0] < 300 else None
        for name, value in case["round_trip"].items():
            if isinstance(record, dict) and name in record and record[name] != value:
                found.update(kind="not_kept", field=name, sent=len(value), kept=str(record[name])[:60],
                             kept_length=len(str(record[name])))
                break
    assert "kind" not in found, MARKER + " " + json.dumps(found)
'''


def pytest_edge_checks(cases: list[dict[str, Any]], plan: dict[str, Any] | None = None) -> str:
    """A pytest module with one test per case, using the contract probe's own calls and sign-in."""
    from app.acceptance import interface_contract as ic

    head = ic._PYTEST_PROBE.split("@pytest.mark.parametrize", 1)[0]  # noqa: SLF001 - its calls and its sign-in
    head = head % (json.dumps([]), json.dumps(plan), json.dumps(list(ic._TOKEN_KEYS)))  # noqa: SLF001
    return head + _PYTEST_TAIL % (json.dumps(cases), MARKER, ic.MADE_NO_RECORD, ic.SIGN_IN_ANSWERED_FIRST,
                                  ic.NOT_THIS_WRITE_S_BODY, ic.SIGN_IN_ANSWERED_FIRST)


_JS_HELPERS = """
const EDGE_CASE = %s;
function parsed(text) { try { return JSON.parse(text); } catch { return null; } }
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
async function ask(request, method, path, body, headers, hasBody) {
  const options = { method, headers: { ...headers }, failOnStatusCode: false };
  if (hasBody) {
    options.headers['content-type'] = 'application/json';
    options.data = Buffer.from(JSON.stringify(body));
  }
  const answer = await request.fetch(path, options).catch(() => null);
  if (!answer) return { status: 0, text: '' };
  return { status: answer.status(), text: await answer.text().catch(() => '') };
}
async function count(request, path, headers) {
  const got = await ask(request, 'GET', path, null, headers, false);
  if (got.status < 200 || got.status >= 300) return null;
  const found = parsed(got.text);
  if (Array.isArray(found)) return found.length;
  const list = found && typeof found === 'object' ? Object.values(found).find(Array.isArray) : undefined;
  return list ? list.length : null;
}
function at(before, after, value) { return before + encodeURIComponent(String(value)) + after; }
"""

_JS_TEST = """test(%s, async ({ request }) => {
  const c = %s;
  const headers = typeof signedIn === 'function' ? await signedIn(request) : {};
  let path = c.path;
  if (c.made_through) {
    let made = null;
    for (const data of [...c.bodies, {}]) {
      const tried = await ask(request, 'POST', c.made_through, data, headers, true);
      if (tried.status >= 200 && tried.status < 300) { made = idOf(parsed(tried.text), c.parameter); break; }
    }
    test.skip(made === null, %s);
    path = at(c.before, c.after, made);
    if (c.id_value === 'deleted') await ask(request, 'DELETE', path, null, headers, false);
  }
  if (c.example !== null) {
    const plain = await ask(request, c.method, path, c.example, headers, true);
    test.skip([401, 403].includes(plain.status), %s);
    test.skip(plain.status >= 400 || plain.status === 0, %s);
  }
  const before = c.list ? await count(request, c.list, headers) : null;
  const held = c.read ? await ask(request, 'GET', path, null, headers, false) : null;
  const got = await ask(request, c.method, path, c.send, headers, c.has_body);
  test.skip([401, 403].includes(got.status), %s);
  const found = { status: got.status, said: got.text.slice(0, 200).replace(/\\s+/g, ' ') };
  if (got.status === 0 || got.status >= 500) {
    found.kind = 'server_error';
  } else if (got.status >= 400 && got.status < 500 && before !== null) {
    const after = await count(request, c.list, headers);
    if (after !== null && after !== before) Object.assign(found, { kind: 'stored_on_refusal', before, after });
  } else if (got.status >= 400 && got.status < 500 && held && held.status >= 200 && held.status < 300) {
    const now = await ask(request, 'GET', path, null, headers, false);
    if (JSON.stringify(parsed(now.text)) !== JSON.stringify(parsed(held.text))) found.kind = 'changed_on_refusal';
  } else if (got.status >= 200 && got.status < 300 && Object.keys(c.round_trip).length) {
    const made = idOf(parsed(got.text), c.parameter);
    const back = made === null ? null : await ask(request, 'GET', at(c.get_before, c.get_after, made), null, headers, false);
    const record = back && back.status >= 200 && back.status < 300 ? recordOf(parsed(back.text)) : null;
    for (const [name, value] of Object.entries(c.round_trip)) {
      if (record && typeof record === 'object' && name in record && record[name] !== value) {
        Object.assign(found, { kind: 'not_kept', field: name, sent: value.length, kept: String(record[name]).slice(0, 60),
                               kept_length: String(record[name]).length });
        break;
      }
    }
  }
  if (found.kind) throw new Error(EDGE_CASE + ' ' + JSON.stringify(found));
});
"""


def playwright_edge_checks(cases: list[dict[str, Any]], plan: dict[str, Any] | None = None) -> str:
    """A Playwright spec with one test per case, signed in as the contract's other body probes are."""
    from app.acceptance import interface_contract as ic

    js = ic._js  # noqa: SLF001
    head = "import { test, expect } from '@playwright/test';\n"
    tests = [_JS_TEST % (js(case["id"]), json.dumps(case), js(ic.MADE_NO_RECORD), js(ic.SIGN_IN_ANSWERED_FIRST),
                         js(ic.NOT_THIS_WRITE_S_BODY), js(ic.SIGN_IN_ANSWERED_FIRST)) for case in cases]
    return ic._with_sign_in_js(head + _JS_HELPERS % js(MARKER) + "\n" + "\n".join(tests), plan)  # noqa: SLF001


#: The spec or module each probe runner compiles the cases into.
RUNNERS = {"playwright": playwright_edge_checks, "pytest": pytest_edge_checks}


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


def _the_case_of(test: Any, cases: list[dict[str, Any]]) -> dict[str, Any] | None:
    number = _CASE_NUMBER.search(str(getattr(test, "name", "") or ""))
    return cases[int(number.group(1)) - 1] if number and 0 < int(number.group(1)) <= len(cases) else None


def edge_errors(repo_root: str | Path, *, runner: Any = None) -> list[tuple[dict[str, Any], dict[str, Any]]] | None:
    """Each case the product failed, with what the probe found; None when off or when the probe cannot run."""
    if not enabled():
        return None
    try:
        from app.acceptance import interface_contract as ic
        from app.acceptance import suite
        from app.stacks import contract

        root = Path(repo_root)
        bodies = list(suite._state(root).get("interface_contract_bodies") or [])  # noqa: SLF001
        lines = ic.the_locked_contract(root)[:ic.MOST_CHECKS]
        cases = edge_cases(lines, bodies)
        found = contract.the_pack(root)
        name = found[0].probe_runner if found else ""
        probe = ic.PROBE_RUNNERS.get(name)
        if not cases or probe is None or name not in RUNNERS:
            return None
        project_name = str((found[1] or {}).get("project") or "")
        run = runner or suite._sandbox_runner(root)  # noqa: SLF001 - the suite's own runner
        compiled = {**probe, "edge_checks": partial(RUNNERS[name], plan=ic.sign_in_plan(lines, bodies))}
        report = ic._the_probe_s_report(root / project_name, project_name, compiled, cases, run,  # noqa: SLF001
                                        "edge_checks")
        if report is None or not report.found:
            return None
        errors: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for test in report.tests:
            case = _the_case_of(test, cases)
            if case is not None and getattr(test, "outcome", "") == "failed" \
                    and (finding := what_the_test_found(test)) is not None:
                errors.append((case, finding))
        return errors
    except Exception:  # noqa: BLE001 - a check that cannot run says nothing
        logger.debug("Could not probe the contract at its edges", exc_info=True)
        return None


def _the_request(case: dict[str, Any]) -> str:
    """`POST /notes` with `title` missing - as the defect names it, and as `still_raised` reads it back."""
    return f"`{case['method']} {case['shown']}` {case['what']}"


def what_came_back(case: dict[str, Any], found: dict[str, Any]) -> str:
    """What the product did with one edge request, in words."""
    status = int(found.get("status") or 0)
    answered = "got no answer" if status == 0 else f"answered {status}"
    said = f" (it said: {found['said']})" if found.get("said") else ""
    kind = found.get("kind")
    if kind == "stored_on_refusal":
        return (f"was refused with {status}, yet `GET {case['list']}` then listed {found.get('after')} records where it "
                f"listed {found.get('before')}")
    if kind == "changed_on_refusal":
        return f"was refused with {status}, yet the record read back afterwards had changed"
    if kind == "not_kept":
        return (f"{answered}, and the record read back holds `{found.get('field')}` as "
                f"{json.dumps(found.get('kept'))} ({found.get('kept_length')} characters) where "
                f"{found.get('sent')} characters were sent")
    return answered + said


def edge_description(found: list[tuple[dict[str, Any], dict[str, Any]]]) -> str:
    """The defect's description: each request, what came back, and what a product does with such a request."""
    each = "; ".join(f"{_the_request(case)} {what_came_back(case, f)}" for case, f in found[:8])
    more = f"; and {len(found) - 8} more" if len(found) > 8 else ""
    return (
        f"{EDGE_CASES_FAILED} {each}{more}. A request at the edge of what the contract describes - a field missing, "
        "null, empty, only spaces, of the wrong type, very long or in another script; an id that is not a number, "
        "negative, huge or already deleted - is answered with a status under 500, accepted or refused as the "
        "specification says; a refused write stores and changes nothing; and a record created is read back with "
        "each text exactly as it was sent."
    )


def still_raised(repo_root: str | Path, description: str, *, runner: Any = None) -> bool | None:
    """Whether a defect with this description would be raised again now; None when it is not this probe's or it cannot run."""
    text = str(description or "")
    if not text.startswith(EDGE_CASES_FAILED):
        return None
    if not enabled():
        # Switched off in mid-run: nothing can settle it, and an open defect would never close.
        return False
    errors = edge_errors(repo_root, runner=runner)
    if errors is None:
        return None
    return any(_the_request(case) in text for case, _ in errors)


__all__ = [
    "EDGE_CASES_FAILED", "MARKER", "MOST_CASES", "ON_BY_DEFAULT", "RUNNERS", "edge_cases", "edge_description",
    "edge_errors", "enabled", "playwright_edge_checks", "pytest_edge_checks", "still_raised", "what_came_back",
    "what_the_test_found",
]
