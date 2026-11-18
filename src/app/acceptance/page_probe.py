"""The harness's own checks of a page product in a browser, written without a model (behind `PAGE_PROBE`).

Deep review 2026-11-18, item B5: page products had no check for markup typed into a text field being run as code, for
console errors and failed requests while an item is added, for sideways scrolling at a 360px-wide phone, or for an
item lost on a reload where the brief says the data persists. The pack's page check (`_javascript.page_check`)
already loads the page once before every suite run and records console errors at load, an accessibility engine's
serious and critical findings (axe-core, a dev dependency of the page packs) and the width at 375px; this probe
drives the page as a person adds an item, which the page check never does.

When a test round finds the locked suite green, one Playwright spec is run through the suite's own configuration
(its server, its address): each finding becomes one defect, worded with `PAGE_CHECK_FAILED`, and the probe settles
it. Only page products whose suite runs on Playwright are probed. A form is filled and sent the way the page sends
it: the form's submit control, else the Enter key in the field, else a control named for adding. A page with no
text field is not probed. Off until measured: a page's own way of adding an item may be one the probe cannot drive.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from app.switches import is_on

logger = logging.getLogger(__name__)

#: Off in code like every switch; the compose file says whether it is on.
ON_BY_DEFAULT = False

#: How the defect's description begins; the audit's switch-firing check and `still_raised` read it.
PAGE_CHECK_FAILED = "A check of the page in a browser finds:"
#: What a failed test of the probe throws before its finding, as JSON.
MARKER = "PAGE CHECK:"
#: The markup typed into each text field: it sets a flag only if the page adds it to the document as markup.
MARKUP = '<img src=x onerror="window.__probe_xss=1">'
#: The phone width the page must fit.
PHONE = (360, 740)

#: A brief saying the data outlives a reload: "notes persist", "survive a page reload", "saved in localStorage".
_PERSISTS = re.compile(
    r"\bpersist(?:s|ed|ence|ent)?\b|\bsurvives?\b[^.\n]{0,30}\breload|\bafter\b[^.\n]{0,20}\breload|"
    r"\blocal\s?storage\b|\bkept between\b|\bstill there\b[^.\n]{0,30}\b(?:reload|refresh)",
    re.I,
)

#: The checks, in the spec's order: (number, kind, title).
CHECKS = (
    (1, "markup_ran", "markup typed into a text field is shown as text"),
    (2, "errors", "no console error or failed request while an item is added"),
    (3, "overflow", f"the page fits a {PHONE[0]}px-wide screen"),
    (4, "not_kept", "an item added is still shown after a reload"),
)


def enabled() -> bool:
    return is_on("PAGE_PROBE", ON_BY_DEFAULT)


def the_brief_says_data_persists(brief: str) -> bool:
    """Whether the brief says what is added outlives a reload; only then is check 4 asked."""
    return bool(_PERSISTS.search(str(brief or "")))


_SPEC = """import { test, expect } from '@playwright/test';

const MARKER = %(marker)s;
const MARKUP = %(markup)s;
const PERSISTS = %(persists)s;
const NOT_THE_PRODUCT = /favicon\\.ico/;
const FIELDS = 'input:not([type]), input[type=text], input[type=search], textarea';

function found(kind, details) {
  throw new Error(MARKER + ' ' + JSON.stringify({ kind, ...details }));
}

// Fill each visible text field and send the form the way the page sends it; false when the page has no text field.
async function addAnItem(page, text) {
  const fields = page.locator(FIELDS).filter({ visible: true });
  const count = await fields.count();
  if (!count) return false;
  for (let i = 0; i < count; i += 1) await fields.nth(i).fill(text).catch(() => {});
  const first = fields.first();
  const form = first.locator('xpath=ancestor::form[1]');
  const submit = form.locator('[type=submit], button:not([type])').filter({ visible: true }).first();
  if (await form.count() && await submit.count()) {
    await submit.click().catch(() => {});
  } else {
    const named = page.getByRole('button', { name: /add|create|save|submit|post|send|new/i }).filter({ visible: true });
    if (!(await form.count()) && await named.count()) await named.first().click().catch(() => {});
    else await first.press('Enter').catch(() => {});
  }
  await page.waitForTimeout(600);
  return true;
}

test('page check 1: markup typed into a text field is shown as text', async ({ page }) => {
  await page.goto('/');
  test.skip(!(await addAnItem(page, MARKUP)), 'the page has no text field');
  await page.waitForTimeout(400);
  if (await page.evaluate(() => window.__probe_xss === 1)) found('markup_ran', {});
});

test('page check 2: no console error or failed request while an item is added', async ({ page }) => {
  const problems = [];
  const note = (text) => { if (problems.length < 8 && !problems.includes(text)) problems.push(text); };
  page.on('pageerror', (error) => note(`uncaught error: ${String(error.message).split('\\n')[0].slice(0, 200)}`));
  page.on('console', (message) => {
    if (message.type() === 'error' && !message.text().startsWith('Failed to load resource')) {
      note(`console error: ${message.text().slice(0, 200)}`);
    }
  });
  page.on('requestfailed', (request) => {
    if (!NOT_THE_PRODUCT.test(request.url())) note(`request failed: ${request.url()} (${request.failure()?.errorText})`);
  });
  page.on('response', (response) => {
    if (response.status() >= 500 && !NOT_THE_PRODUCT.test(response.url())) {
      note(`HTTP ${response.status()} for ${response.request().method()} ${response.url()}`);
    }
  });
  await page.goto('/');
  await page.waitForTimeout(400);
  await addAnItem(page, `probe item ${Date.now()}`);
  if (problems.length) found('errors', { problems });
});

test('page check 3: the page fits a %(width)spx-wide screen', async ({ page }) => {
  await page.setViewportSize({ width: %(width)s, height: %(height)s });
  await page.goto('/');
  await page.waitForTimeout(400);
  const measure = () => page.evaluate(() => Math.max(0, document.documentElement.scrollWidth - window.innerWidth));
  let wider = await measure();
  if (wider <= 1 && await addAnItem(page, `probe item with a rather long name ${Date.now()}`)) wider = await measure();
  if (wider > 1) found('overflow', { wider });
});

test('page check 4: an item added is still shown after a reload', async ({ page }) => {
  test.skip(!PERSISTS, 'the brief does not say the data persists');
  await page.goto('/');
  const text = `probe kept ${Date.now()}`;
  test.skip(!(await addAnItem(page, text)), 'the page has no text field');
  const shown = page.getByText(text, { exact: false }).first();
  test.skip(!(await shown.isVisible().catch(() => false)), 'the item added is not shown, so nothing can be reloaded');
  await page.reload();
  await page.waitForTimeout(600);
  if (!(await page.getByText(text, { exact: false }).first().isVisible().catch(() => false))) found('not_kept', { text });
});
"""


def playwright_page_checks(_web: list[Any], *, persists: bool = False) -> str:
    """The spec: the four checks, each throwing `MARKER` and its finding when the page fails it."""
    return _SPEC % {"marker": json.dumps(MARKER), "markup": json.dumps(MARKUP), "persists": json.dumps(bool(persists)),
                    "width": PHONE[0], "height": PHONE[1]}


_NUMBER = re.compile(r"\bpage check (\d)\b")


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


def _a_page_product(repo_root: Path) -> tuple[Any, dict[str, Any]] | None:
    from app.stacks import contract

    found = contract.the_pack(repo_root)
    if found is None or found[0].probe_runner != "playwright" or not getattr(found[0], "runtime_report", ""):
        return None
    return found


def page_errors(repo_root: str | Path, brief: str | None = None, *, runner: Any = None) -> list[dict[str, Any]] | None:
    """What the page checks found, one finding per failed check; None when off, not a page product, or it cannot run.

    `brief` says whether check 4 is asked; None reads what the last asking kept, as `still_raised` does.
    """
    if not enabled():
        return None
    try:
        from app.acceptance import interface_contract as ic
        from app.acceptance import suite

        root = Path(repo_root)
        found = _a_page_product(root)
        if found is None:
            return None
        project_name = str((found[1] or {}).get("project") or "")
        run = runner or suite._sandbox_runner(root)  # noqa: SLF001 - the suite's own runner
        state = suite._state(root)  # noqa: SLF001 - one state file for the suite and its probes
        if brief is None:
            persists = bool(state.get(_PERSISTS_KEY))
        else:
            persists = the_brief_says_data_persists(brief)
            state[_PERSISTS_KEY] = persists
            suite._save_state(root, state)  # noqa: SLF001
        probe = {**ic.PROBE_RUNNERS["playwright"],
                 "page_checks": lambda web: playwright_page_checks(web, persists=persists)}
        report = ic._the_probe_s_report(root / project_name, project_name, probe, [None], run,  # noqa: SLF001
                                        "page_checks")
        if report is None or not report.found:
            return None
        errors: list[dict[str, Any]] = []
        for test in report.tests:
            if getattr(test, "outcome", "") == "failed" and (finding := what_the_test_found(test)) is not None:
                errors.append(finding)
        return errors
    except Exception:  # noqa: BLE001 - a check that cannot run says nothing
        logger.debug("Could not check the page in a browser", exc_info=True)
        return None


#: Where the brief's word on persistence is kept for `still_raised`.
_PERSISTS_KEY = "page_probe_persists"

#: How each finding opens in the defect; `still_raised` reads them back.
_OPENINGS = {
    "markup_ran": "markup typed into a text field and sent was run as code",
    "errors": "while the page loaded and an item was added, it reported",
    "overflow": f"at a {PHONE[0]}px-wide screen the page is",
    "not_kept": "an item added was gone after the page was reloaded",
}


def _said(finding: dict[str, Any]) -> str:
    kind = finding.get("kind")
    if kind == "markup_ran":
        return (f"markup typed into a text field and sent was run as code: `{MARKUP}` set a flag only markup added to "
                "the page can set")
    if kind == "errors":
        return "while the page loaded and an item was added, it reported: " + "; ".join(
            str(p) for p in finding.get("problems") or [])[:900]
    if kind == "overflow":
        return f"at a {PHONE[0]}px-wide screen the page is {finding.get('wider')}px wider than the screen and scrolls sideways"
    if kind == "not_kept":
        return "an item added was gone after the page was reloaded, where the brief says the data persists"
    return str(kind)


def page_description(found: list[dict[str, Any]]) -> str:
    """The defect's description: each check the page failed, and what a page does instead."""
    return (
        f"{PAGE_CHECK_FAILED} " + "; ".join(_said(f) for f in found) + ". Text a person types is shown as text, never "
        "added to the page as markup (set it as text content, or escape it); the page reports no error and every "
        f"request it makes is answered under 500; it fits a {PHONE[0]}px-wide screen without scrolling sideways; and "
        "what the brief says persists is shown again after a reload."
    )


def still_raised(repo_root: str | Path, description: str, *, runner: Any = None) -> bool | None:
    """Whether a defect with this description would be raised again now; None when it is not this probe's or it cannot run."""
    text = str(description or "")
    if not text.startswith(PAGE_CHECK_FAILED):
        return None
    if not enabled():
        # Switched off in mid-run: nothing can settle it, and an open defect would never close.
        return False
    errors = page_errors(repo_root, runner=runner)
    if errors is None:
        return None
    return any(_OPENINGS.get(str(f.get("kind")), "\0") in text for f in errors)


__all__ = ["CHECKS", "MARKER", "MARKUP", "ON_BY_DEFAULT", "PAGE_CHECK_FAILED", "PHONE", "enabled", "page_description",
           "page_errors", "playwright_page_checks", "still_raised", "the_brief_says_data_persists",
           "what_the_test_found"]
