"""Creates sent at the same moment must each be kept, each with its own id (behind `CONCURRENT_WRITE_PROBE`).

Measured: in several benchmark families products lost writes made at the same moment - two records given one id, or
one record overwriting another in the store - which only an external quality test caught; the locked suite sends its
writes one at a time. When a test round finds the locked suite green, the contract's create line (a `POST` on a path
with no parameter that needs a body) is sent `AT_ONCE` creates at once with an example body the line takes, and the
list route on the same path is read when the contract has one. A defect when any of them answered a 5xx or nothing,
two answers carry the same id, or fewer of the created records are listed than were created.

A quality probe that starts the product once more per green round, so a switch until measured.
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

#: The words its defect gives, which the audit's switch-firing check reads.
SAID = "writes made at the same moment must each be kept with their own id"

#: How many creates are sent at once: as many as the hidden quality test, since a race shows only when requests
#: overlap. Measured on a Ruby run: a store that read its file outside the lock passed 10 at once in its last round,
#: and lost writes at 16 in the hidden test.
AT_ONCE = 16

#: How the defect's description begins; `still_raised` and the round read it back.
CONCURRENT_WRITES_LOST = "Writes made at the same moment are not each kept:"

#: What a failed test of the probe throws before its findings, as JSON.
MARKER = "WRITES AT ONCE:"

#: Why a create line was skipped: none of the example bodies, nor an empty one, made a record.
TOOK_NO_EXAMPLE_BODY = "the create line took none of the example bodies, so nothing was sent at once"

#: Keys that say a listing is one page of several, keys that give the whole count, and keys that hold the records.
_PAGING_KEYS = ("next", "page", "cursor", "limit", "offset", "hasMore", "has_more", "next_cursor", "nextCursor")
_TOTAL_KEYS = ("total", "count", "totalCount", "total_count")
_LIST_KEYS = ("items", "data", "results", "records")

#: A route's parameter, for reading its name.
_A_PARAMETER = re.compile(r"\{([^}]*)\}|:([A-Za-z_]\w*)")


def enabled() -> bool:
    return is_on("CONCURRENT_WRITE_PROBE", ON_BY_DEFAULT)


def _the_list_route(check: Any, lines: list[Any]) -> str:
    """The path of the contract's `GET` on the create line's own path, or ""."""
    path = check.path.rstrip("/")
    return next((c.path for c in lines if c.kind == "http" and c.method == "GET" and c.path.rstrip("/") == path), "")


def _the_id_name(check: Any, lines: list[Any]) -> str:
    """The name the contract gives a record's id on the create line's path (`/notes/{noteId}` gives `noteId`), or "id"."""
    path = check.path.rstrip("/")
    for line in lines:
        if line.kind != "http" or not line.path.startswith(path + "/"):
            continue
        found = _A_PARAMETER.match(line.path[len(path) + 1:])
        if found:
            return found.group(1) or found.group(2)
    return "id"


def concurrent_write_checks(lines: list[Any]) -> tuple[list[Any], list[str]]:
    """(the create lines the probe asks, the write lines it leaves and why): one per path, sign-in and sign-up writes left."""
    from app.acceptance import interface_contract as ic

    lines = [ic._a_literal_id_as_a_parameter(c) for c in lines]  # noqa: SLF001 - one reading of a line's route
    asked: list[Any] = []
    unasked: list[str] = []
    seen: set[str] = set()
    for check in lines:
        if not (check.kind == "http" and check.method == "POST" and ic._a_write_that_needs_a_body(check)):  # noqa: SLF001
            continue
        if ic._A_TEMPLATE.search(check.path) or check.path.rstrip("/") in seen:  # noqa: SLF001
            continue
        if ic._SIGNS_IN.search(check.path) or ic._SIGNS_UP.search(check.path):  # noqa: SLF001
            unasked.append(f"{check.line} (a sign-in or sign-up write makes no record to list)")
            continue
        seen.add(check.path.rstrip("/"))
        asked.append(check)
    return asked, unasked


def _case(check: Any, lines: list[Any], bodies: list[Any]) -> dict[str, Any]:
    return {"path": check.path, "list": _the_list_route(check, lines), "parameter": _the_id_name(check, lines),
            "bodies": [b for b in bodies if isinstance(b, dict)], "at_once": AT_ONCE}


def _title(number: int, check: Any) -> str:
    return f"{f'[{check.criterion}] ' if check.criterion else ''}contract {number}: {check.line} sent {AT_ONCE} at once"


_JS_HELPERS = """
const WRITES_AT_ONCE = %s;
function idOf(record, name) {
  if (!record || typeof record !== 'object') return null;
  const found = record[name] ?? record.id ?? record.data?.[name] ?? record.data?.id;
  return found === undefined || found === null ? null : String(found);
}
async function listing(request, path, name, headers) {
  const answer = await request.fetch(path, { method: 'GET', headers, failOnStatusCode: false }).catch(() => null);
  if (!answer || !answer.ok()) return null;
  const found = await answer.json().catch(() => null);
  let items = Array.isArray(found) ? found : null;
  let total = null;
  let paged = false;
  if (!items && found && typeof found === 'object') {
    for (const key of %s) if (Array.isArray(found[key])) { items = found[key]; break; }
    if (!items) items = Object.values(found).find(Array.isArray) ?? null;
    for (const key of %s) if (Number.isInteger(found[key])) { total = found[key]; break; }
    paged = %s.some((key) => key in found);
  }
  if (!items) return null;
  return { ids: items.map((r) => (r && typeof r === 'object' ? idOf(r, name) : String(r))), length: items.length, total, paged };
}
function kept(before, after, ids, made, atOnce) {
  if (!before || !after) return null;
  if (before.total !== null && after.total !== null) return Math.min(made, Math.max(0, after.total - before.total));
  if (before.paged || after.paged) return null;
  if (after.length === before.length && before.length >= atOnce) return null;
  if (ids.length && ids.length === made) return [...new Set(ids)].filter((id) => after.ids.includes(id)).length;
  return Math.min(made, Math.max(0, after.length - before.length));
}
"""

_JS_TEST = """test(%s, async ({ request }) => {
  const c = %s;
  const headers = typeof signedIn === 'function' ? await signedIn(request) : {};
  let body;
  for (const data of [...c.bodies, {}]) {
    const tried = await request.fetch(c.path, { method: 'POST', data, headers, failOnStatusCode: false });
    test.skip([401, 403].includes(tried.status()), %s);
    if (tried.ok()) { body = data; break; }
  }
  test.skip(body === undefined, %s);
  const before = c.list ? await listing(request, c.list, c.parameter, headers) : null;
  const answers = await Promise.all(Array.from({ length: c.at_once }, () =>
    request.fetch(c.path, { method: 'POST', data: body, headers, failOnStatusCode: false }).catch(() => null)));
  const statuses = answers.map((a) => (a ? a.status() : 0));
  const ids = [];
  for (const a of answers) {
    if (!a || !a.ok()) continue;
    const id = idOf(await a.json().catch(() => null), c.parameter);
    if (id !== null) ids.push(id);
  }
  const made = statuses.filter((s) => s >= 200 && s < 300).length;
  const same = [...new Set(ids.filter((id, i) => ids.indexOf(id) !== i))].slice(0, 5);
  const listed = before ? kept(before, await listing(request, c.list, c.parameter, headers), ids, made, c.at_once) : null;
  const failed = statuses.filter((s) => s === 0 || s >= 500).length;
  if (failed || same.length || (listed !== null && listed < made)) {
    throw new Error(WRITES_AT_ONCE + ' ' + JSON.stringify({ sent: c.at_once, body, statuses, same_id: same, made, listed, list: c.list }));
  }
});
"""


def playwright_concurrent_write_checks(asked: list[Any], lines: list[Any], bodies: list[Any]) -> str:
    """A Playwright spec with one test per create line, sending its creates at once with `Promise.all`.

    The bodies are JSON objects, sent as `data` objects: Playwright encodes an object as the JSON it is.
    """
    from app.acceptance import interface_contract as ic

    js = ic._js  # noqa: SLF001
    head = "import { test, expect } from '@playwright/test';\n"
    helpers = _JS_HELPERS % (js(MARKER), json.dumps(list(_LIST_KEYS)), json.dumps(list(_TOTAL_KEYS)),
                             json.dumps(list(_PAGING_KEYS)))
    tests = [_JS_TEST % (js(_title(n, c)), json.dumps(_case(c, lines, bodies)), js(ic.SIGN_IN_ANSWERED_FIRST),
                         js(TOOK_NO_EXAMPLE_BODY))
             for n, c in enumerate(asked, start=1)]
    return ic._with_sign_in_js(head + helpers + "\n" + "\n".join(tests), ic.sign_in_plan(lines, bodies))  # noqa: SLF001


_PYTEST_TAIL = '''
import threading
from concurrent.futures import ThreadPoolExecutor

AT_ONCE_CASES = json.loads(%r)
MARKER = %r
LIST_KEYS = json.loads(%r)
TOTAL_KEYS = json.loads(%r)
PAGING_KEYS = json.loads(%r)


def _json(raw):
    try:
        return json.loads(raw or b"null")
    except ValueError:
        return None


def _id_of(record, name):
    if not isinstance(record, dict):
        return None
    found = record.get(name, record.get("id"))
    if found is None and isinstance(record.get("data"), dict):
        found = record["data"].get(name, record["data"].get("id"))
    return None if found is None else str(found)


def _listing(base_url, case, extra):
    try:
        status, raw = _call(base_url, "GET", case["list"], None, extra)
    except Exception:
        return None
    if not 200 <= status < 300:
        return None
    found = _json(raw)
    items, total, paged = (found if isinstance(found, list) else None), None, False
    if isinstance(found, dict):
        items = next((found[k] for k in LIST_KEYS if isinstance(found.get(k), list)), None)
        if items is None:
            items = next((v for v in found.values() if isinstance(v, list)), None)
        total = next((found[k] for k in TOTAL_KEYS if type(found.get(k)) is int), None)
        paged = any(k in found for k in PAGING_KEYS)
    if items is None:
        return None
    return {"ids": [_id_of(r, case["parameter"]) if isinstance(r, dict) else str(r) for r in items],
            "length": len(items), "total": total, "paged": paged}


def _kept(before, after, ids, made, at_once):
    if before is None or after is None:
        return None
    if before["total"] is not None and after["total"] is not None:
        return min(made, max(0, after["total"] - before["total"]))
    if before["paged"] or after["paged"]:
        return None
    if after["length"] == before["length"] and before["length"] >= at_once:
        return None
    if ids and len(ids) == made:
        return sum(1 for i in set(ids) if i in after["ids"])
    return min(made, max(0, after["length"] - before["length"]))


@pytest.mark.parametrize("case", AT_ONCE_CASES, ids=[case["id"] for case in AT_ONCE_CASES])
def test_writes_at_once(case, base_url):
    extra = _signed_in(base_url)
    body = None
    for data in [*case["bodies"], {}]:
        status, _ = _call(base_url, "POST", case["path"], data, extra)
        if status in (401, 403):
            pytest.skip(%r)
        if 200 <= status < 300:
            body = data
            break
    if body is None:
        pytest.skip(%r)
    before = _listing(base_url, case, extra) if case["list"] else None
    gate = threading.Barrier(case["at_once"])

    def one(_):
        try:
            gate.wait(timeout=30)
        except threading.BrokenBarrierError:
            pass
        try:
            return _call(base_url, "POST", case["path"], body, extra)
        except Exception:
            return 0, b""

    with ThreadPoolExecutor(max_workers=case["at_once"]) as pool:
        answers = list(pool.map(one, range(case["at_once"])))
    statuses = [status for status, _ in answers]
    made = sum(1 for status in statuses if 200 <= status < 300)
    ids = [i for status, raw in answers if 200 <= status < 300
           for i in [_id_of(_json(raw), case["parameter"])] if i is not None]
    same = sorted({i for i in ids if ids.count(i) > 1})[:5]
    listed = _kept(before, _listing(base_url, case, extra), ids, made, case["at_once"]) if before is not None else None
    failed = [status for status in statuses if status == 0 or status >= 500]
    found = {"sent": case["at_once"], "body": body, "statuses": statuses, "same_id": same, "made": made,
             "listed": listed, "list": case["list"]}
    assert not (failed or same or (listed is not None and listed < made)), MARKER + " " + json.dumps(found)
'''


def pytest_concurrent_write_checks(asked: list[Any], lines: list[Any], bodies: list[Any]) -> str:
    """A pytest module with one case per create line, sending its creates at once from threads held at one barrier."""
    from app.acceptance import interface_contract as ic

    head = ic._PYTEST_PROBE.split("@pytest.mark.parametrize", 1)[0]  # noqa: SLF001 - its calls and its sign-in
    head = head % (json.dumps([]), json.dumps(ic.sign_in_plan(lines, bodies)), json.dumps(list(ic._TOKEN_KEYS)))  # noqa: SLF001
    cases = [{**_case(c, lines, bodies), "id": _title(n, c)} for n, c in enumerate(asked, start=1)]
    return head + _PYTEST_TAIL % (json.dumps(cases), MARKER, json.dumps(list(_LIST_KEYS)), json.dumps(list(_TOTAL_KEYS)),
                                  json.dumps(list(_PAGING_KEYS)), ic.SIGN_IN_ANSWERED_FIRST, TOOK_NO_EXAMPLE_BODY)


#: The spec or module each probe runner compiles the create lines into.
RUNNERS = {"playwright": playwright_concurrent_write_checks, "pytest": pytest_concurrent_write_checks}

#: Where the lines the probe could not ask are kept for the release.
_UNASKED_KEY = "interface_contract_concurrent_write_unchecked"


def what_the_test_found(test: Any) -> dict[str, Any] | None:
    """The findings a failed test of the probe threw after `MARKER`, or None when it threw none."""
    text = str(getattr(test, "message", "") or "")
    at = text.find(MARKER)
    if at < 0:
        return None
    try:
        found, _ = json.JSONDecoder().raw_decode(text[at + len(MARKER):].lstrip())
    except ValueError:
        return None
    return found if isinstance(found, dict) else None


def concurrent_write_errors(repo_root: str | Path, *, runner: Any = None) -> list[tuple[Any, dict[str, Any]]] | None:
    """Each create line of the locked contract that does not keep creates sent at once, with what the probe found.

    None when off or when the probe cannot run. What could not be asked is kept for the release to name.
    """
    if not enabled():
        return None
    try:
        from app.acceptance import interface_contract as ic
        from app.acceptance import probe_coverage, suite
        from app.stacks import contract

        root = Path(repo_root)
        state = suite._state(root)  # noqa: SLF001 - one state file for the suite and its contract
        bodies = list(state.get("interface_contract_bodies") or [])
        lines = ic.the_locked_contract(root)[:ic.MOST_CHECKS]
        asked, unchecked = concurrent_write_checks(lines)
        found = contract.the_pack(root)
        name = found[0].probe_runner if found else ""
        probe = ic.PROBE_RUNNERS.get(name)
        if probe is None or name not in RUNNERS:
            unchecked += [f"{c.line} (no runner on this stack probes it)" for c in asked]
            asked = []
        errors: list[tuple[Any, dict[str, Any]]] | None = None
        report = None
        if asked:
            project_name = str((found[1] or {}).get("project") or "")
            run = runner or suite._sandbox_runner(root)  # noqa: SLF001 - the suite's own runner
            compiled = {**probe, "concurrent_write_checks": partial(RUNNERS[name], lines=lines, bodies=bodies)}
            report = ic._the_probe_s_report(root / project_name, project_name, compiled, asked, run,  # noqa: SLF001
                                            "concurrent_write_checks")
            if report is None or not report.found:
                unchecked += [f"{c.line} (the probe's runner wrote no report)" for c in asked]
                report = None
            else:
                errors = []
                for test in report.tests:
                    check = ic._the_check_of(test, asked)  # noqa: SLF001
                    if check is None:
                        continue
                    outcome = getattr(test, "outcome", "")
                    if outcome == "skipped":
                        unchecked.append(f"{check.line} ({ic.SIGN_IN_ANSWERED_FIRST}, or {TOOK_NO_EXAMPLE_BODY})")
                    elif outcome == "failed" and (findings := what_the_test_found(test)) is not None:
                        errors.append((check, findings))
                    elif outcome == "failed":
                        unchecked.append(f"{check.line} (the probe got no findings back)")
        state = suite._state(root)  # noqa: SLF001 - read again: the runner's suite calls may have saved it
        state[_UNASKED_KEY] = list(dict.fromkeys(unchecked))
        suite._save_state(root, state)  # noqa: SLF001
        probe_coverage.write(root, "concurrent_write", probe_coverage.coverage(
            considered=len(lines), asked=asked, report=report,
            not_asked=[(u.rsplit(" (", 1)[0], u.rsplit(" (", 1)[-1].rstrip(")")) for u in unchecked
                       if not any(u.startswith(c.line) for c in asked)],
            check_of=lambda test: ic._the_check_of(test, asked),  # noqa: SLF001
        ))
        return errors
    except Exception:  # noqa: BLE001 - a check that cannot run says nothing
        logger.debug("Could not probe the contract with writes made at once", exc_info=True)
        return None


def what_came_back(found: dict[str, Any]) -> str:
    """What the creates sent at once were answered, and what the ids and the listing showed."""
    statuses = [int(s) for s in found.get("statuses") or [] if isinstance(s, (int, float))]
    counted = ", ".join(f"{'no answer' if s == 0 else s} x{statuses.count(s)}" for s in sorted(set(statuses)))
    parts = [f"they answered {counted or 'nothing'}"]
    if found.get("same_id"):
        parts.append("two or more answers carried the same id (" + ", ".join(f"`{i}`" for i in found["same_id"][:5]) + ")")
    listed, made = found.get("listed"), found.get("made")
    if isinstance(listed, int) and isinstance(made, int) and listed < made:
        parts.append(f"`GET {found.get('list') or ''}` listed {listed} of the {made} created")
    return "; ".join(parts)


def concurrent_write_description(found: list[tuple[Any, dict[str, Any]]]) -> str:
    """The defect's description: what was sent, what came back, and what a product must do with writes made at once."""
    each = "; ".join(
        f"`{check.method} {check.path}` was sent {f.get('sent') or AT_ONCE} creates at once, each with the body "
        f"`{json.dumps(f.get('body') if f.get('body') is not None else {})[:200]}`: {what_came_back(f)}"
        for check, f in found[:4]
    )
    return (
        f"{CONCURRENT_WRITES_LOST} {each}. {SAID[0].upper()}{SAID[1:]}, each answered with a status under 500: "
        "serialise the store's writes (one write at a time, or each in its own transaction) and let the store give "
        "each record its id, so no write made at the same moment overwrites, drops or shares an id with another."
    )


def still_raised(repo_root: str | Path, description: str, *, runner: Any = None) -> bool | None:
    """Whether a defect with this description would be raised again now; None when it is not this probe's or it cannot run."""
    text = str(description or "")
    if not text.startswith(CONCURRENT_WRITES_LOST):
        return None
    if not enabled():
        # Switched off in mid-run: nothing can settle it, and an open defect would never close.
        return False
    errors = concurrent_write_errors(repo_root, runner=runner)
    if errors is None:
        return None
    return any(f"`{check.method} {check.path}` was sent" in text for check, _ in errors)


def what_it_did_not_ask(repo_root: str | Path) -> list[str]:
    """A completion gap naming the create lines the last probe could not ask; [] when none or it is off. Never raises."""
    try:
        from app.acceptance import suite

        if not enabled():
            return []
        lines = [str(line) for line in suite._state(repo_root).get(_UNASKED_KEY) or []]  # noqa: SLF001
        if not lines:
            return []
        return [(f"{len(lines)} write line(s) of the interface contract were not sent {AT_ONCE} creates at once: "
                 + "; ".join(lines[:5]) + ("; ..." if len(lines) > 5 else ""))[:800]]
    except Exception:  # noqa: BLE001 - the release says nothing it cannot measure
        logger.debug("Could not read what the concurrent-write probe left unasked", exc_info=True)
        return []


__all__ = [
    "AT_ONCE", "CONCURRENT_WRITES_LOST", "MARKER", "ON_BY_DEFAULT", "RUNNERS", "SAID", "TOOK_NO_EXAMPLE_BODY",
    "concurrent_write_checks", "concurrent_write_description", "concurrent_write_errors", "enabled", "what_came_back",
    "playwright_concurrent_write_checks", "pytest_concurrent_write_checks", "still_raised", "what_it_did_not_ask",
    "what_the_test_found",
]
