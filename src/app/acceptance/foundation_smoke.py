"""A short smoke of the product's foundation, asked at each test round before the suite's failures are fixed (LF.1268).

Measured on a medium run: sign-up answered 500 for hours (its tables were never created), then every route answered
404 under a doubled prefix, and all 24 per-criterion fixers of a sprint worked on a product where no account could be
made - each was judged by the suite's pass count, which could not move while the foundation stood broken.

The smoke is compiled from the locked interface contract with no model, and run against the started product the way
the contract's probes are (`round_trip_probe`): the product answers; when the contract has a sign-up and a sign-in that
are due, a fresh account is made and signed in; one create of the main resource (the first due create line) with the
contract's example bodies, and one read of it back - the record by its id, else the list. Only a clear fault fails a
step: no answer, a server error, a route that is not there (404, 405), a fresh account that cannot sign in, a token
from the sign-in refused, a record just made not read back. Any other answer - a body refused, a rate limit, a sign-in
whose answer carries no token the smoke can read - leaves the smoke unsettled, and an unsettled smoke changes nothing.

A failed smoke is one blocking defect for its first failing step, with the request, the answer and the server's log;
while it is open the fix round sends a fixer to it alone (`start_first.held_back`: the next tier after a product that
does not start). A product with no HTTP contract (a command line, a library), a stack whose pack names no probe
runner, or a contract with nothing due beyond the start is not smoked. Each result is kept in `RECORD_FILE` and the
run's transcript.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

logger = logging.getLogger(__name__)

#: Where the latest smoke's result is kept, beside the contract probes' coverage.
RECORD_FILE = ".harness/foundation-smoke.json"
#: The first sentence of the smoke's defect: the same each time it is raised, so a round raising it again refreshes it.
FOUNDATION_FAILS = "The product's foundation does not hold, so the acceptance tests built on it cannot pass."
#: What a test of the smoke throws (or skips with) before its result, as JSON.
MARKER = "FOUNDATION SMOKE:"
#: The transcript record's kind.
RECORD_KIND = "foundation_smoke"

#: Answers that say a step is broken, whatever the body sent: no answer, a route that is not there, a server error.
_NOT_THERE = (404, 405)

#: The steps, in their order, and how a defect names each.
STEPS = {
    "start": "the product answers a request",
    "sign_up": "a fresh account is made",
    "sign_in": "the fresh account signs in",
    "create": "one record of the main resource is made",
    "read": "the record made is read back",
}


@dataclass
class Result:
    """One smoke: whether the foundation held (None: the smoke could not settle it), and the first step that failed."""

    held: bool | None
    step: str = ""
    method: str = ""
    path: str = ""
    status: int = 0
    said: str = ""
    why: str = ""
    passed: list[str] = field(default_factory=list)
    server_log: str = ""


def _is_due(check: Any, due: Sequence[str] | None) -> bool:
    return due is None or not getattr(check, "criterion", "") or check.criterion in due


def the_smoke(lines: list[Any], bodies: list[Any], due: Sequence[str] | None = None) -> tuple[dict[str, Any] | None, str]:
    """(what the smoke asks, compiled from the contract; or None and why it asks nothing). Pure.

    `due` is the criteria the sprint answers for (None: all of them); a step whose line belongs to a later sprint is
    not asked.
    """
    from app.acceptance import edge_probe
    from app.acceptance import interface_contract as ic

    http = [ic._a_literal_id_as_a_parameter(c) for c in lines if getattr(c, "kind", "") == "http"]  # noqa: SLF001
    if not http:
        return None, "the contract has no HTTP line"
    templated = ic._A_TEMPLATE  # noqa: SLF001

    def signs_in(path: str) -> bool:
        return bool(ic._SIGNS_IN.search(path) or ic._SIGNS_UP.search(path))  # noqa: SLF001

    plan = ic.sign_in_plan(http, bodies)
    sign_in: dict[str, Any] | None = None
    if plan is not None and any(c.method == "POST" and c.path == plan["signin"] and _is_due(c, due) for c in http):
        signup = plan["signup"] if any(
            c.method == "POST" and c.path == plan["signup"] and _is_due(c, due) for c in http) else ""
        sign_in = {"signup": signup, "signin": plan["signin"], "body": plan["body"],
                   # A bearer token is what the smoke reads; a contract naming another kind of sign-in is not held to it.
                   "bearer": not any(ic._ANOTHER_KIND_OF_SIGN_IN.search(c.line) for c in http)}  # noqa: SLF001
    create = next((c for c in http if c.method == "POST" and not templated.search(c.path) and 200 <= c.status < 300
                   and not signs_in(c.path) and _is_due(c, due)), None)
    made: dict[str, Any] | None = None
    if create is not None:
        at = create.path.rstrip("/")
        read = next((c for c in http if c.method == "GET" and _is_due(c, due)
                     and (one := edge_probe._one_parameter(c.path)) is not None  # noqa: SLF001
                     and one[0].rstrip("/") == at and not one[1].strip("/")), None)
        listed = next((c for c in http if c.method == "GET" and c.path.rstrip("/") == at and _is_due(c, due)), None)
        one = edge_probe._one_parameter(read.path) if read is not None else None  # noqa: SLF001
        examples = [b for b in bodies or [] if isinstance(b, dict) and b and not any(k in b for k in ic._SECRETS)]  # noqa: SLF001
        made = {"path": create.path, "bodies": [*examples[:ic.MOST_EXAMPLE_BODIES], {}],
                "parameter": one[2] if one else "id",
                "read": read.path if read is not None else "", "before": one[0] if one else "",
                "after": one[1] if one else "", "list": listed.path if listed is not None else ""}
    if sign_in is None and made is None:
        return None, "nothing due beyond the start: no sign-up, sign-in or create line of this sprint's criteria"
    start = (made or {}).get("list") or "/"
    return {"start": start, "sign_in": sign_in, "create": made, "token_keys": list(ic._TOKEN_KEYS)}, ""  # noqa: SLF001


_PYTEST_MODULE = '''"""Written by the harness for one smoke of the product's foundation, then removed."""
import json
import urllib.error
import urllib.parse
import urllib.request
import uuid

import pytest

SMOKE = json.loads(__SMOKE__)
MARKER = __MARKER__
NOT_THERE = (404, 405)


def _call(base_url, method, path, body, extra=None):
    data, headers = None, dict(extra or {})
    if body is not None:
        data = json.dumps(body).encode()
        headers["content-type"] = "application/json"
    request = urllib.request.Request(base_url.rstrip("/") + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as answer:
            return answer.status, answer.read()
    except urllib.error.HTTPError as answer:
        return answer.code, answer.read()
    except Exception:
        return 0, b""


def _said(raw):
    return " ".join((raw or b"").decode("utf-8", "replace")[:400].split())


def _json(raw):
    try:
        return json.loads(raw or b"null")
    except ValueError:
        return None


def _ok(status):
    return 200 <= status < 300


def _broken(status):
    return status == 0 or status >= 500 or status in NOT_THERE


def _a_token(found):
    if not isinstance(found, dict):
        return None
    for key in SMOKE["token_keys"]:
        value = found.get(key)
        if isinstance(value, str) and value:
            return value
    for value in found.values():
        if isinstance(value, dict) and (token := _a_token(value)):
            return token
    return None


def _id_of(found, name):
    if isinstance(found, dict) and "id" not in found and name not in found and isinstance(found.get("data"), dict):
        found = found["data"]
    if not isinstance(found, dict):
        return None
    value = found.get(name, found.get("id"))
    return None if value is None else str(value)


def _smoke(base_url):
    passed = []

    def failed(step, method, path, status, raw, why):
        return {"held": False, "step": step, "method": method, "path": path, "status": status, "said": _said(raw),
                "why": why, "passed": passed}

    def unsettled(step, method, path, status, raw, why):
        return {"held": None, "step": step, "method": method, "path": path, "status": status, "said": _said(raw),
                "why": why, "passed": passed}

    status, raw = _call(base_url, "GET", SMOKE["start"], None)
    if status == 0:
        return failed("start", "GET", SMOKE["start"], 0, raw, "no answer")
    passed.append("start")
    extra, signed_up = {}, False
    plan = SMOKE["sign_in"]
    if plan:
        body = dict(plan["body"])
        if plan["signup"]:
            suffix = uuid.uuid4().hex[:8]
            for key in ("username", "email", "name", "login", "user"):
                if isinstance(body.get(key), str):
                    body[key] = f"smoke{suffix}@example.com" if "@" in body[key] else f"smoke{suffix}"
            status, raw = _call(base_url, "POST", plan["signup"], body)
            if _broken(status):
                return failed("sign_up", "POST", plan["signup"], status, raw, "broken")
            if not _ok(status):
                return unsettled("sign_up", "POST", plan["signup"], status, raw, "the sign-up refused the body")
            passed.append("sign_up")
            signed_up = True
        status, raw = _call(base_url, "POST", plan["signin"], body)
        if _broken(status):
            return failed("sign_in", "POST", plan["signin"], status, raw, "broken")
        if status in (401, 403) and signed_up:
            return failed("sign_in", "POST", plan["signin"], status, raw, "refused a fresh account")
        if not _ok(status):
            return unsettled("sign_in", "POST", plan["signin"], status, raw, "the sign-in refused the body")
        token = _a_token(_json(raw))
        if token is None and plan["bearer"]:
            return unsettled("sign_in", "POST", plan["signin"], status, raw, "no token the smoke can read")
        extra = {"Authorization": "Bearer " + token} if token else {}
        passed.append("sign_in")
    made = SMOKE["create"]
    if not made:
        return {"held": True, "passed": passed}
    record, status, raw = None, 0, b""
    for data in made["bodies"]:
        status, raw = _call(base_url, "POST", made["path"], data, extra)
        if _broken(status):
            return failed("create", "POST", made["path"], status, raw, "broken")
        if status in (401, 403):
            if extra:
                return failed("create", "POST", made["path"], status, raw, "refused the token the sign-in gave")
            return unsettled("create", "POST", made["path"], status, raw, "a sign-in answered first")
        if _ok(status):
            record = _id_of(_json(raw), made["parameter"])
            break
    else:
        return unsettled("create", "POST", made["path"], status, raw, "the create refused every example body")
    passed.append("create")
    if made["read"] and record is not None:
        method, path = "GET", made["before"] + urllib.parse.quote(record, safe="") + made["after"]
    elif made["list"]:
        method, path = "GET", made["list"]
    else:
        return {"held": True, "passed": passed}
    status, raw = _call(base_url, method, path, None, extra)
    if _broken(status):
        return failed("read", method, path, status, raw, "broken")
    if status in (401, 403) and extra:
        return failed("read", method, path, status, raw, "refused the token the sign-in gave")
    if not _ok(status):
        return unsettled("read", method, path, status, raw, "the read was refused")
    passed.append("read")
    return {"held": True, "passed": passed}


def test_foundation_smoke(base_url):
    found = _smoke(base_url)
    if found["held"] is None:
        pytest.skip(MARKER + " " + json.dumps(found))
    assert found["held"], MARKER + " " + json.dumps(found)
'''


def pytest_smoke(plans: list[dict[str, Any]]) -> str:
    """A pytest module running the smoke as one test, with the suite's own `base_url`."""
    return (_PYTEST_MODULE.replace("__SMOKE__", repr(json.dumps(plans[0])))
            .replace("__MARKER__", repr(MARKER)))


_PLAYWRIGHT_SPEC = """import { test } from '@playwright/test';

const SMOKE = __SMOKE__;
const MARKER = __MARKER__;
const NOT_THERE = [404, 405];

async function call(request, method, path, body, headers) {
  const options = { method, headers: { ...(headers || {}) }, failOnStatusCode: false };
  if (body !== null) {
    options.headers['content-type'] = 'application/json';
    options.data = Buffer.from(JSON.stringify(body));
  }
  const answer = await request.fetch(path, options).catch(() => null);
  if (!answer) return { status: 0, text: '' };
  return { status: answer.status(), text: await answer.text().catch(() => '') };
}
function said(text) { return String(text || '').slice(0, 400).replace(/\\s+/g, ' ').trim(); }
function parsed(text) { try { return JSON.parse(text); } catch { return null; } }
function ok(status) { return status >= 200 && status < 300; }
function broken(status) { return status === 0 || status >= 500 || NOT_THERE.includes(status); }
function aToken(found) {
  if (!found || typeof found !== 'object') return null;
  for (const key of SMOKE.token_keys) {
    if (typeof found[key] === 'string' && found[key]) return found[key];
  }
  for (const value of Object.values(found)) {
    if (value && typeof value === 'object') { const token = aToken(value); if (token) return token; }
  }
  return null;
}
function idOf(found, name) {
  if (found && typeof found === 'object' && !('id' in found) && !(name in found) && found.data
      && typeof found.data === 'object') found = found.data;
  if (!found || typeof found !== 'object') return null;
  const value = found[name] ?? found.id;
  return value === undefined || value === null ? null : String(value);
}

async function smoke(request) {
  const passed = [];
  const failed = (step, method, path, got, why) => ({ held: false, step, method, path, status: got.status,
                                                       said: said(got.text), why, passed });
  const unsettled = (step, method, path, got, why) => ({ held: null, step, method, path, status: got.status,
                                                          said: said(got.text), why, passed });
  let got = await call(request, 'GET', SMOKE.start, null, {});
  if (got.status === 0) return failed('start', 'GET', SMOKE.start, got, 'no answer');
  passed.push('start');
  let headers = {};
  let signedUp = false;
  const plan = SMOKE.sign_in;
  if (plan) {
    const body = { ...plan.body };
    if (plan.signup) {
      const suffix = Math.random().toString(36).slice(2, 10);
      for (const key of ['username', 'email', 'name', 'login', 'user']) {
        if (typeof body[key] === 'string') body[key] = body[key].includes('@') ? `smoke${suffix}@example.com` : `smoke${suffix}`;
      }
      got = await call(request, 'POST', plan.signup, body, {});
      if (broken(got.status)) return failed('sign_up', 'POST', plan.signup, got, 'broken');
      if (!ok(got.status)) return unsettled('sign_up', 'POST', plan.signup, got, 'the sign-up refused the body');
      passed.push('sign_up');
      signedUp = true;
    }
    got = await call(request, 'POST', plan.signin, body, {});
    if (broken(got.status)) return failed('sign_in', 'POST', plan.signin, got, 'broken');
    if ([401, 403].includes(got.status) && signedUp) return failed('sign_in', 'POST', plan.signin, got, 'refused a fresh account');
    if (!ok(got.status)) return unsettled('sign_in', 'POST', plan.signin, got, 'the sign-in refused the body');
    const token = aToken(parsed(got.text));
    if (token === null && plan.bearer) return unsettled('sign_in', 'POST', plan.signin, got, 'no token the smoke can read');
    headers = token ? { authorization: `Bearer ${token}` } : {};
    passed.push('sign_in');
  }
  const made = SMOKE.create;
  if (!made) return { held: true, passed };
  let record = null;
  let created = false;
  for (const data of made.bodies) {
    got = await call(request, 'POST', made.path, data, headers);
    if (broken(got.status)) return failed('create', 'POST', made.path, got, 'broken');
    if ([401, 403].includes(got.status)) {
      if (headers.authorization) return failed('create', 'POST', made.path, got, 'refused the token the sign-in gave');
      return unsettled('create', 'POST', made.path, got, 'a sign-in answered first');
    }
    if (ok(got.status)) { record = idOf(parsed(got.text), made.parameter); created = true; break; }
  }
  if (!created) return unsettled('create', 'POST', made.path, got, 'the create refused every example body');
  passed.push('create');
  let path;
  if (made.read && record !== null) path = made.before + encodeURIComponent(record) + made.after;
  else if (made.list) path = made.list;
  else return { held: true, passed };
  got = await call(request, 'GET', path, null, headers);
  if (broken(got.status)) return failed('read', 'GET', path, got, 'broken');
  if ([401, 403].includes(got.status) && headers.authorization) return failed('read', 'GET', path, got, 'refused the token the sign-in gave');
  if (!ok(got.status)) return unsettled('read', 'GET', path, got, 'the read was refused');
  passed.push('read');
  return { held: true, passed };
}

test('foundation smoke', async ({ request }) => {
  const found = await smoke(request);
  test.skip(found.held === null, MARKER + ' ' + JSON.stringify(found));
  if (!found.held) throw new Error(MARKER + ' ' + JSON.stringify(found));
});
"""


def playwright_smoke(plans: list[dict[str, Any]]) -> str:
    """A Playwright spec running the smoke as one test, against the suite's own web server."""
    return (_PLAYWRIGHT_SPEC.replace("__SMOKE__", json.dumps(plans[0]))
            .replace("__MARKER__", json.dumps(MARKER)))


#: The spec or module each probe runner compiles the smoke into.
RUNNERS = {"playwright": playwright_smoke, "pytest": pytest_smoke}


def _what_the_test_said(test: Any) -> dict[str, Any] | None:
    text = str(getattr(test, "message", "") or "")
    at = text.find(MARKER)
    if at < 0:
        return None
    try:
        found, _ = json.JSONDecoder().raw_decode(text[at + len(MARKER):].lstrip())
    except ValueError:
        return None
    return found if isinstance(found, dict) and "held" in found else None


def _the_server_log(project: Path, method: str, path: str) -> str:
    """What the server printed while the smoke ran: the error near its request, else the end of what it printed."""
    from app.acceptance import interface_contract as ic
    from app.acceptance import what_went_wrong

    printed = ic.what_the_server_printed(project)
    if not printed.strip():
        return ""
    near = what_went_wrong.what_the_server_printed_for(printed, path, method)
    tail = what_went_wrong.shown(printed, 1_500)
    return f"{near}\n\n{tail}" if near and near not in tail else tail


def run(repo_root: str | Path, due: Sequence[str] | None = None, *, runner: Any = None) -> Result | None:
    """The smoke against the product as it is now; None when it does not apply or cannot run. Never raises."""
    try:
        from app.acceptance import interface_contract as ic
        from app.acceptance import suite
        from app.stacks import contract

        root = Path(repo_root)
        plan, why = the_smoke(ic.the_locked_contract(root)[:ic.MOST_CHECKS], ic.bodies_for_the_probes(root), due)
        if plan is None:
            logger.debug("No foundation smoke: %s", why)
            return None
        found = contract.the_pack(root)
        name = found[0].probe_runner if found else ""
        probe = ic.PROBE_RUNNERS.get(name)
        if probe is None or name not in RUNNERS:
            return None
        project_name = str((found[1] or {}).get("project") or "")
        run_it = runner or suite._sandbox_runner(root)  # noqa: SLF001 - the suite's own runner
        report = ic._the_probe_s_report(root / project_name, project_name,  # noqa: SLF001
                                        {**probe, "foundation_smoke": RUNNERS[name]}, [plan], run_it,
                                        "foundation_smoke")
        if report is None or not report.found or not report.tests:
            return None
        test = report.tests[0]
        if getattr(test, "outcome", "") == "passed":
            steps = ["start", *(["sign_up"] if (plan["sign_in"] or {}).get("signup") else []),
                     *(["sign_in"] if plan["sign_in"] else []), *(["create"] if plan["create"] else []),
                     *(["read"] if plan["create"] and (plan["create"]["read"] or plan["create"]["list"]) else [])]
            return Result(held=True, passed=steps)
        said = _what_the_test_said(test)
        if said is None:
            # A test that failed without saying why is the smoke's own trouble, not the product's.
            return None
        result = Result(held=said.get("held"), step=str(said.get("step") or ""), method=str(said.get("method") or ""),
                        path=str(said.get("path") or ""), status=int(said.get("status") or 0),
                        said=str(said.get("said") or ""), why=str(said.get("why") or ""),
                        passed=[str(s) for s in said.get("passed") or []])
        if result.held is False:
            result.server_log = _the_server_log(root / project_name, result.method, result.path)
        return result
    except Exception:  # noqa: BLE001 - a smoke that cannot run says nothing
        logger.debug("Could not run the foundation smoke", exc_info=True)
        return None


def record(repo_root: str | Path, stage: str, result: Result | None, due: Sequence[str] | None = None) -> None:
    """Keep the smoke's result, and the criteria it was asked for, in the workspace and the run's transcript. Never raises."""
    entry = {"stage": stage, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "due": None if due is None else list(due),
             **({"held": None, "why": "not asked"} if result is None else asdict(result))}
    try:
        path = Path(repo_root) / RECORD_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entry, indent=2), encoding="utf-8")
    except OSError:
        pass
    try:
        from app.models.model_pin import current_run_id
        from app.observability.transcript import record as transcript_record

        transcript_record(current_run_id(), stage, RECORD_KIND,
                          **{k: v for k, v in entry.items() if k not in ("stage", "server_log")})
    except Exception:  # noqa: BLE001 - a record is evidence, not control flow
        logger.debug("Could not record the foundation smoke", exc_info=True)


def last(repo_root: str | Path) -> dict[str, Any]:
    """The latest smoke's record, or {}."""
    try:
        found = json.loads((Path(repo_root) / RECORD_FILE).read_text(encoding="utf-8"))
        return found if isinstance(found, dict) else {}
    except (OSError, ValueError):
        return {}


def _the_request(result: Result) -> str:
    return f"`{result.method} {result.path}`"


def _what_came_back(result: Result) -> str:
    from app.acceptance import what_went_wrong

    answered = "got no answer" if not result.status else f"answered {result.status}"
    said = f" - it said: {what_went_wrong.the_page_in_words(result.said)}" if result.said else ""
    why = {
        "refused a fresh account": " to the account the smoke had just made",
        "refused the token the sign-in gave": " with the token the sign-in had just given",
    }.get(result.why, "")
    return f"{answered}{why}{said}"


def description(result: Result) -> str:
    """The defect's description: the step that failed, the request, what came back."""
    passed = ", ".join(STEPS.get(step, step) for step in result.passed)
    return (f"{FOUNDATION_FAILS} The harness's smoke of it failed where {STEPS.get(result.step, result.step)}: "
            f"{_the_request(result)} {_what_came_back(result)}."
            + (f" Before it: {passed}." if passed else ""))


def is_a_smoke_defect(defect: Any) -> bool:
    """Whether `defect` is the smoke's."""
    return str(getattr(defect, "description", "") or "").startswith(FOUNDATION_FAILS)


def a_defect(result: Result, owner: str) -> Any:
    """The one blocking defect a failed smoke raises."""
    from app.agents.specialists import ReportedDefect
    from app.sprint import cause
    from app.tools.untrusted_text import defanged

    log = defanged(result.server_log, 2_000) if result.server_log else ""
    return ReportedDefect(
        description=description(result),
        severity="blocking",
        reproduction_steps=(
            "Start the product as the acceptance suite does; then, in turn: "
            + "; ".join(STEPS[step] for step in STEPS if step in (*result.passed, result.step))
            + f". The step that fails sends {_the_request(result)}."),
        expected_behavior=(
            "The product answers; a fresh account is made and signs in; a record made through the contract's create "
            "is read back - each with the status the contract gives. Until this holds, every test built on it fails "
            "the same way, so this is fixed first and every other failure is measured again once it holds."),
        actual_behavior=(f"{_the_request(result)} {_what_came_back(result)}."
                         + (f"\n\nWhat the server printed while the smoke ran:\n{log}" if log else "")),
        affected_files=[],
        owner=owner,
        kind=cause.PROBE_FINDING,
        evidence=[cause.a_probe_request("foundation smoke", f"{result.method} {result.path}")],
    )


def still_raised(repo_root: str | Path, text: str, *, runner: Any = None) -> bool | None:
    """Whether the smoke's defect would be raised again now; None when it is not the smoke's or the smoke cannot settle it."""
    if not str(text or "").startswith(FOUNDATION_FAILS):
        return None
    # Asked for the criteria the round asked it for: a create a later sprint builds is not this defect's.
    due = last(repo_root).get("due")
    result = run(repo_root, due if isinstance(due, list) else None, runner=runner)
    if result is None or result.held is None:
        return None
    return result.held is False


__all__ = [
    "FOUNDATION_FAILS", "MARKER", "RECORD_FILE", "RECORD_KIND", "RUNNERS", "STEPS", "Result", "a_defect",
    "description", "is_a_smoke_defect", "last", "playwright_smoke", "pytest_smoke", "record", "run", "still_raised",
    "the_smoke",
]
