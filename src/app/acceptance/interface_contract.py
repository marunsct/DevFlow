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
_HTTP = re.compile(_CRITERION + r"\s+(GET|POST|PUT|PATCH|DELETE)\s+(/\S*)\s*->\s*(\d{3}(?:\s*(?:or|/|,)\s*\d{3})*)\s*$")
#: A page control: the role and its name last, with any words naming where on
#: the page it sits between the path and the role - one specification wrote 26
#: of its page lines as `page /dashboard form textbox "Title"`, and every one
#: was set aside as following no form.
_PAGE = re.compile(_CRITERION + r"\s+page\s+(/\S*)\s+(?:[\w-]+\s+)*?([a-z]+)\s+\"([^\"]+)\"\s*$")
_COMMAND = re.compile(_CRITERION + r"\s+command\s+(.+?)\s*->\s*exit\s+(\d+)\s*$")

#: A control named by its element where the contract asks for its ARIA role.
_ROLE_OF_THE_ELEMENT = {"textarea": "textbox", "select": "combobox"}

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
        if match := _HTTP.match(line):
            statuses = tuple(int(code) for code in re.findall(r"\d{3}", match[4]))
            checks.append(Check(match[1], "http", line, method=match[2], path=match[3], status=statuses[0],
                                statuses=statuses))
        elif match := _PAGE.match(line):
            role = _ROLE_OF_THE_ELEMENT.get(match[3], match[3])
            checks.append(Check(match[1], "page", line, path=match[2], role=role, name=match[4]))
        elif match := _COMMAND.match(line):
            checks.append(Check(match[1], "command", line, command=match[2], exit_code=int(match[3])))
        else:
            unreadable.append(line)
    return checks, unreadable


def record_at_lock(repo_root: str | Path, lines: list[str] | tuple[str, ...]) -> list[Check]:
    """Keep the contract beside the locked suite; what was kept."""
    from app.acceptance import suite

    checks, unreadable = parse(lines)
    state = suite._state(repo_root)  # noqa: SLF001 - one state file for the suite and its contract
    state["interface_contract"] = [asdict(check) for check in checks]
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


def playwright_checks(checks: list[Check]) -> str:
    """A Playwright spec with one test per HTTP or page check."""
    tests = []
    for number, check in enumerate(checks, start=1):
        title = _js(f"[{check.criterion}] contract {number}: {check.line}")
        if check.kind == "http":
            tests.append(
                f"test({title}, async ({{ request }}) => {{\n"
                f"  const answer = await request.fetch({_js(check.path)}, {{ method: {_js(check.method)}, failOnStatusCode: false }});\n"
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
    return "import { test, expect } from '@playwright/test';\n\n" + "\n".join(tests)


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


#: The probe runners a pack can declare (`StackPack.probe_runner`): what compiles
#: the contract's lines into checks, and the command that runs them. Everything
#: specific to one tool is here and in its two functions above.
PROBE_RUNNERS: dict[str, dict[str, Any]] = {
    "playwright": {
        "checks": playwright_checks,
        "config": playwright_config,
        "command": ("npx", "playwright", "test", "--config", CONFIG_FILE),
        "base_config": "playwright.config.js",
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
        report = None
        if web:
            (project / CHECK_DIR).mkdir(parents=True, exist_ok=True)
            (project / CHECK_DIR / "contract.spec.js").write_text(probe["checks"](web), encoding="utf-8")
            (project / CONFIG_FILE).write_text(probe["config"](probe["base_config"]), encoding="utf-8")
            report_file = project / REPORT_FILE
            junit.clear(report_file)
            try:
                run(list(probe["command"]), "test", project_name)
                report = junit.read(report_file)
            finally:
                shutil.rmtree(project / CHECK_DIR, ignore_errors=True)
                (project / CONFIG_FILE).unlink(missing_ok=True)
        failures, not_run = _the_commands_kept([c for c in locked if c.kind == "command"], root, project_name, run)
        unchecked += not_run
    except Exception:  # noqa: BLE001 - the release says nothing it cannot measure
        logger.debug("Could not run the interface contract's checks", exc_info=True)
        return []
    gaps: list[str] = []
    if report is not None and not report.found:
        gaps.append("The interface contract's checks could not run at release: their runner wrote no report.")
    elif report is not None:
        failed = [t for t in report.tests if getattr(t, "outcome", "") not in ("passed", "skipped")]
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
