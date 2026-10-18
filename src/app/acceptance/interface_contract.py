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

Runs where the pack's acceptance runner is Playwright, which starts the
product the same way for every web pack. Other runners are not checked yet.
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

_CRITERION = r"((?:AC|CR)-\d+)"
_HTTP = re.compile(_CRITERION + r"\s+(GET|POST|PUT|PATCH|DELETE)\s+(/\S*)\s*->\s*(\d{3})\s*$")
_PAGE = re.compile(_CRITERION + r"\s+page\s+(/\S*)\s+([a-z]+)\s+\"([^\"]+)\"\s*$")
_COMMAND = re.compile(_CRITERION + r"\s+command\s+(.+?)\s*->\s*exit\s+(\d+)\s*$")

#: Where the compiled checks are written, inside the project, for one release run.
CHECK_DIR = "harness-contract"
CONFIG_FILE = "playwright.contract.config.mjs"
REPORT_FILE = "test-results/contract.xml"

#: Checks run at most, so a long contract stays a seconds-long release step.
MOST_CHECKS = 40


@dataclass(frozen=True)
class Check:
    """One line of the contract, parsed."""

    criterion: str
    kind: str  # "http", "page" or "command"
    line: str
    method: str = ""
    path: str = ""
    status: int = 0
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
        if not line:
            continue
        if match := _HTTP.match(line):
            checks.append(Check(match[1], "http", line, method=match[2], path=match[3], status=int(match[4])))
        elif match := _PAGE.match(line):
            checks.append(Check(match[1], "page", line, path=match[2], role=match[3], name=match[4]))
        elif match := _COMMAND.match(line):
            checks.append(Check(match[1], "command", line, command=match[2], exit_code=int(match[3])))
        else:
            unreadable.append(line)
    return checks, unreadable


def record_at_lock(repo_root: str | Path, lines: list[str] | tuple[str, ...]) -> list[Check]:
    """Keep the contract beside the locked suite; what was kept."""
    from app.acceptance import suite

    checks, _ = parse(lines)
    state = suite._state(repo_root)  # noqa: SLF001 - one state file for the suite and its contract
    state["interface_contract"] = [asdict(check) for check in checks]
    suite._save_state(repo_root, state)  # noqa: SLF001
    return checks


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
                f"  expect(answer.status()).toBe({check.status});\n"
                "});\n"
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


def what_the_contract_checks_find(repo_root: str | Path, *, runner: Any = None) -> list[str]:
    """A completion gap for each contract check the product fails at release; [] when none, or none can run."""
    try:
        from app.acceptance import junit, suite
        from app.stacks import contract

        root = Path(repo_root)
        found = contract.the_pack(root)
        checks = [c for c in the_locked_contract(root) if c.kind in ("http", "page")][:MOST_CHECKS]
        if found is None or not checks:
            return []
        pack, record = found
        probe = PROBE_RUNNERS.get(pack.probe_runner)
        if probe is None:
            return []
        project = root / str(record.get("project") or "")
        (project / CHECK_DIR).mkdir(parents=True, exist_ok=True)
        (project / CHECK_DIR / "contract.spec.js").write_text(probe["checks"](checks), encoding="utf-8")
        (project / CONFIG_FILE).write_text(probe["config"](probe["base_config"]), encoding="utf-8")
        report_file = project / REPORT_FILE
        junit.clear(report_file)
        try:
            (runner or suite._sandbox_runner(root))(  # noqa: SLF001 - the suite's own runner
                list(probe["command"]), "test", str(record.get("project") or ""),
            )
            report = junit.read(report_file)
        finally:
            shutil.rmtree(project / CHECK_DIR, ignore_errors=True)
            (project / CONFIG_FILE).unlink(missing_ok=True)
    except Exception:  # noqa: BLE001 - the release says nothing it cannot measure
        logger.debug("Could not run the interface contract's checks", exc_info=True)
        return []
    if not report.found:
        return ["The interface contract's checks could not run at release: their runner wrote no report."]
    failed = [t for t in report.tests if getattr(t, "outcome", "") not in ("passed", "skipped")]
    logger.info("Interface contract at release: %d of %d check(s) failed", len(failed), len(report.tests))
    return [
        (
            f"At release the product does not keep its interface contract: {t.name}"
            + (" - at a bare visit; the control may be shown only to a signed-in user" if " page /" in t.name else "")
        )[:400]
        for t in failed[:10]
    ]
