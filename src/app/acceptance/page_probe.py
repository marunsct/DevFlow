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
it: the form's submit control, else the Enter key in the field, else a control named for adding. Only the fields of
the form holding the first text field are filled, each with a value its meaning accepts (an address, an e-mail, a
number, a date, a phone number, else the text), so a field that checks its value does not refuse the item and a field
outside the form (a filter) does not hide it. A page with no
text field is not probed. Off until measured: a page's own way of adding an item may be one the probe cannot drive.

Check 5 (LF.1590): each control the interface contract names on the page is the only element carrying its label where
it sits - within the item of a list it belongs to, or on the page for a control shown once. Measured on one run: every
item of a list carried two elements labelled with the control's name, the control (named by the label element
wrapping it) and that label element, given `aria-label` with the same name; the locked suite found the control by its
role and passed, and three hidden tests finding it by its label failed on two matches. A label is read the way a
browser reads one for a label lookup: `aria-labelledby`, `aria-label`, and each label element linked to the element or
wrapping it. The same control shown once in each of several items is not a repeat: each item is its own place.
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
    (5, "repeated_label", "each control the contract names is the only element carrying its label where it sits"),
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
const SMALL_SCREENS = %(small_screens)s;
const CONTROLS = %(controls)s;
const NOT_THE_PRODUCT = /favicon\\.ico/;
const FIELDS = 'input:not([type]), input[type=text], input[type=search], input[type=url], input[type=email], ' +
  'input[type=number], input[type=date], input[type=tel], textarea';
// What a field takes, from its type first, then the words of its name, id, placeholder, autocomplete and labels.
const TYPED = { url: 'url', email: 'email', number: 'number', date: 'date', tel: 'phone' };
const MEANINGS = [
  ['url', /\\b(?:url|uri|link|website|href|https?)\\b/],
  ['email', /\\b(?:e ?mail)\\b/],
  ['phone', /\\b(?:phone|tel|telephone|mobile)\\b/],
  ['date', /\\bdate\\b/],
  ['number', /\\b(?:number|count|quantity|qty|price|age|amount)\\b/],
];

function found(kind, details) {
  throw new Error(MARKER + ' ' + JSON.stringify({ kind, ...details }));
}

// 'url', 'email', 'phone', 'date', 'number', or 'text' for a field that takes any words.
async function whatItTakes(field) {
  const said = await field.evaluate((el) => ({
    type: String(el.getAttribute('type') || '').toLowerCase(),
    words: [el.name, el.id, el.placeholder, el.getAttribute('autocomplete'), el.getAttribute('aria-label'),
      ...Array.from(el.labels || [], (label) => label.textContent)].filter(Boolean).join(' '),
  })).catch(() => ({ type: '', words: '' }));
  if (TYPED[said.type]) return TYPED[said.type];
  const words = said.words.replace(/([a-z0-9])([A-Z])/g, '$1 $2').toLowerCase().replace(/[^a-z0-9]+/g, ' ');
  const meaning = MEANINGS.find(([, pattern]) => pattern.test(words));
  return meaning ? meaning[0] : 'text';
}

// A value a field of this kind accepts; a text field gets the text itself.
function aValueFor(kind, text) {
  if (kind === 'url') return 'https://example.com/' + (text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'probe');
  if (kind === 'email') return `probe+${Date.now()}@example.com`;
  if (kind === 'number') return '1';
  if (kind === 'date') return new Date().toISOString().slice(0, 10);
  if (kind === 'phone') return '+15550100';
  return text;
}

// Fill the fields of the form that holds the first visible text field, each with a value it accepts, and send it the
// way the page sends it. Returns the text to find the item by afterwards (what the first field taking any words got,
// else the address written), or false when the page has no text field.
async function addAnItem(page, text) {
  const first = page.locator(FIELDS).filter({ visible: true }).first();
  if (!(await first.count())) return false;
  const form = first.locator('xpath=ancestor::form[1]');
  const inAForm = (await form.count()) > 0;
  // A field outside the form (a filter, a search) is left alone: what it holds would narrow the list shown.
  const fields = inAForm ? form.locator(FIELDS).filter({ visible: true }) : first;
  const count = await fields.count();
  let words = null;
  let address = null;
  for (let i = 0; i < count; i += 1) {
    const field = fields.nth(i);
    const kind = await whatItTakes(field);
    const value = aValueFor(kind, text);
    await field.fill(value).catch(() => {});
    if (kind === 'text' && words === null) words = value;
    if ((kind === 'url' || kind === 'email') && address === null) address = value;
  }
  // A form is sent the way the browser sends it, through its own submit handlers; a field outside a form by Enter.
  // A page that adds only through a pointer on a control outside a form is not driven, and its checks are skipped.
  if (inAForm) await form.evaluate((f) => (f.requestSubmit ? f.requestSubmit() : f.submit())).catch(() => {});
  else await first.press('Enter').catch(() => {});
  await page.waitForTimeout(600);
  return words ?? address ?? text;
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
  test.skip(!SMALL_SCREENS, 'the brief does not ask for small screens');
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
  const text = await addAnItem(page, `probe kept ${Date.now()}`);
  test.skip(!text, 'the page has no text field');
  const shown = page.getByText(text, { exact: false }).first();
  test.skip(!(await shown.isVisible().catch(() => false)), 'the item added is not shown, so nothing can be reloaded');
  await page.reload();
  await page.waitForTimeout(600);
  if (!(await page.getByText(text, { exact: false }).first().isVisible().catch(() => false))) found('not_kept', { text });
});

// In the page: where one of `shown` (the control's instances) sits - the widest element holding it and no other
// instance, so each item of a list is its own place and a control shown once has the whole page - and the elements
// there carrying `name` as a label, when more than one does; else null.
function carriedTwice({ shown, name }) {
  const plain = (text) => String(text || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const wanted = plain(name);
  const textOf = (node, without) => {
    let text = '';
    const walk = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
    while (walk.nextNode()) if (!without || !without.contains(walk.currentNode)) text += walk.currentNode.textContent;
    return text;
  };
  // How an element is labelled with `name`, by each way a label lookup reads a label.
  const labels = (el) => {
    const said = [];
    const by = el.getAttribute('aria-labelledby');
    if (by) {
      const named = by.split(/\s+/).map((id) => document.getElementById(id)).filter(Boolean);
      if (named.length) said.push(['aria-labelledby', named.map((n) => textOf(n)).join(' ')]);
    }
    if (el.hasAttribute('aria-label')) said.push(['aria-label', el.getAttribute('aria-label')]);
    for (const label of el.labels || []) {
      said.push([label.contains(el) ? 'the label element around it' : 'a label element linked to it', textOf(label, el)]);
    }
    return said.filter(([, text]) => plain(text) === wanted).map(([how]) => how);
  };
  const tag = (el) => '<' + el.localName + (el.id ? ` id="${el.id}"` : '') +
    (el.getAttribute('class') ? ` class="${el.getAttribute('class')}"` : '') + '>';
  for (const one of shown) {
    let place = one;
    while (place.parentElement && shown.filter((other) => place.parentElement.contains(other)).length === 1) {
      place = place.parentElement;
    }
    const carriers = [place, ...place.querySelectorAll('*')]
      .map((el) => [el, labels(el)]).filter(([, how]) => how.length);
    if (carriers.length > 1) {
      return { count: carriers.length, where: place.parentElement ? 'item' : 'page',
               carriers: carriers.slice(0, 4).map(([el, how]) => `${tag(el)} by ${how.join(' and ')}`) };
    }
  }
  return null;
}

test('page check 5: each control the contract names is the only element carrying its label where it sits', async ({ page }) => {
  test.skip(!CONTROLS.length, 'the contract names no control on this page');
  await page.goto('/');
  await page.waitForTimeout(400);
  // An item added first, so the controls each item of a list shows are on the page.
  await addAnItem(page, `probe item ${Date.now()}`);
  const repeated = [];
  for (const { role, name } of CONTROLS) {
    const shown = await page.getByRole(role, { name, exact: true }).elementHandles().catch(() => []);
    if (!shown.length) continue;
    const twice = await page.evaluate(carriedTwice, { shown: shown.slice(0, 20), name }).catch(() => null);
    if (twice) repeated.push({ role, name, ...twice });
  }
  if (repeated.length) found('repeated_label', { controls: repeated.slice(0, 6) });
});
"""


def playwright_page_checks(_web: list[Any], *, persists: bool = False, small_screens: bool = False,
                           controls: Any = ()) -> str:
    """The spec: the five checks, each throwing `MARKER` and its finding when the page fails it.

    Check 3 (the phone width) is asked only when the brief asks for small screens, as the pack's own 375px check is
    (`interface_checks.asks_for_small_screens`): a brief that never asks for a phone is not held to one. Check 5 is
    asked of `controls`, the (role, name) of each control the contract names on the page (`controls_on_the_page`).
    """
    named = [{"role": str(role), "name": str(name)} for role, name in controls or ()]
    return _SPEC % {"marker": json.dumps(MARKER), "markup": json.dumps(MARKUP), "persists": json.dumps(bool(persists)),
                    "small_screens": json.dumps(bool(small_screens)), "controls": json.dumps(named),
                    "width": PHONE[0], "height": PHONE[1]}


def controls_on_the_page(checks: Any) -> list[tuple[str, str]]:
    """The (role, name) of each control the contract's page lines name on the page the probe opens, once each.

    Only lines a page can show at all (`interface_contract.why_a_bare_visit_cannot_check` says nothing against them);
    a line on another path is not on the page the probe opens.
    """
    from app.acceptance import interface_contract as ic

    named: list[tuple[str, str]] = []
    for check in checks or ():
        if getattr(check, "kind", "") != "page" or str(getattr(check, "path", "") or "/") not in ("/", "/index.html"):
            continue
        if ic.why_a_bare_visit_cannot_check(check) or not check.name:
            continue
        role = ic._ELEMENT_ROLES.get(check.role, check.role)  # noqa: SLF001 - the contract's own reading of a role
        if (role, check.name) not in named:
            named.append((role, check.name))
    return named


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
            small_screens = bool(state.get(_SMALL_SCREENS_KEY))
        else:
            from app.analysis.interface_checks import asks_for_small_screens

            persists = the_brief_says_data_persists(brief)
            small_screens = asks_for_small_screens(brief)
            state[_PERSISTS_KEY] = persists
            state[_SMALL_SCREENS_KEY] = small_screens
            suite._save_state(root, state)  # noqa: SLF001
        controls = controls_on_the_page(ic.the_locked_contract(root))
        probe = {**ic.PROBE_RUNNERS["playwright"],
                 "page_checks": lambda web: playwright_page_checks(web, persists=persists, small_screens=small_screens,
                                                                   controls=controls)}
        report = ic._the_probe_s_report(root / project_name, project_name, probe, [None], run,  # noqa: SLF001
                                        "page_checks")
        if report is None or not report.found:
            _kept(root, "could not run: the probe's runner wrote no report", report)
            return None
        errors: list[dict[str, Any]] = []
        for test in report.tests:
            if getattr(test, "outcome", "") == "failed" and (finding := what_the_test_found(test)) is not None:
                errors.append(finding)
        _kept(root, f"found {len(errors)}" if errors else "ran clean", report, errors)
        return errors
    except Exception as error:  # noqa: BLE001 - a check that cannot run says nothing
        logger.debug("Could not check the page in a browser", exc_info=True)
        _kept(Path(repo_root), f"could not run: {type(error).__name__}: {str(error)[:160]}")
        return None


#: The page probe's record in `.harness/contract-probe.json`, beside the contract probes' (`probe_coverage`).
RECORD_KIND = "page"


def _kept(root: Path, outcome: str, report: Any = None, found: list[dict[str, Any]] | None = None) -> None:
    """The probe's outcome kept beside the contract probes': whether it ran clean, found something, or could not run,
    and each check's result. Measured: the probe was reached in 8 of 45 workspaces and nothing told "four checks
    passed" from "did not run". Never raises."""
    try:
        from app.acceptance import probe_coverage

        checks = {f"page check {number}": title for number, _, title in CHECKS}
        named = {}
        for test in getattr(report, "tests", None) or []:
            number = _NUMBER.search(str(getattr(test, "name", "") or ""))
            if number:
                named[f"page check {number.group(1)}"] = test
        skipped = [{"line": title, "reason": " ".join(str(getattr(named[check], "message", "") or "skipped").split())[:200]}
                   for check, title in checks.items() if check in named and getattr(named[check], "outcome", "") == "skipped"]
        skipped += [{"line": title, "reason": "no result"} for check, title in checks.items()
                    if report is not None and check not in named]
        probed = [title for check, title in checks.items()
                  if check in named and getattr(named[check], "outcome", "") != "skipped"]
        probe_coverage.write(root, RECORD_KIND, {
            "outcome": outcome, "considered": len(CHECKS), "asked": len(CHECKS) if report is not None else 0,
            "probed": len(probed), "skipped": skipped, "found": [str(f.get("kind")) for f in found or []],
        })
    except Exception:  # noqa: BLE001 - a record must never change what the probe found
        logger.debug("Could not keep the page probe's outcome", exc_info=True)


#: Where the brief's word on persistence is kept for `still_raised`.
_PERSISTS_KEY = "page_probe_persists"
#: And its word on small screens.
_SMALL_SCREENS_KEY = "page_probe_small_screens"

#: How each finding opens in the defect; `still_raised` reads them back.
_OPENINGS = {
    "markup_ran": "markup typed into a text field and sent was run as code",
    "errors": "while the page loaded and an item was added, it reported",
    "overflow": f"at a {PHONE[0]}px-wide screen the page is",
    "not_kept": "an item added was gone after the page was reloaded",
    "repeated_label": "more than one element carries the label of a control the contract names",
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
    if kind == "repeated_label":
        return ("more than one element carries the label of a control the contract names, so a test or a screen "
                "reader finding the control by its label meets several: " + "; ".join(
                    f'{c.get("role")} "{c.get("name")}": {c.get("count")} elements '
                    f'{"within one item" if c.get("where") == "item" else "on the page"} - '
                    + ", ".join(str(x) for x in c.get("carriers") or [])
                    for c in finding.get("controls") or [] if isinstance(c, dict))[:900])
    return str(kind)


def page_description(found: list[dict[str, Any]]) -> str:
    """The defect's description: each check the page failed, and what a page does instead."""
    return (
        f"{PAGE_CHECK_FAILED} " + "; ".join(_said(f) for f in found) + ". Text a person types is shown as text, never "
        "added to the page as markup (set it as text content, or escape it); the page reports no error and every "
        f"request it makes is answered under 500; it fits a {PHONE[0]}px-wide screen without scrolling sideways; "
        "what the brief says persists is shown again after a reload; and each control the contract names is the only "
        "element carrying its label within its item, or on the page for a control shown once: the label names the "
        "control (a label element around it or linked to it, or `aria-label` on the control itself) and is never "
        "given again to that label element or to anything around the control."
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


__all__ = ["CHECKS", "MARKER", "MARKUP", "ON_BY_DEFAULT", "PAGE_CHECK_FAILED", "PHONE", "controls_on_the_page", "enabled",
           "page_description",
           "page_errors", "playwright_page_checks", "still_raised", "the_brief_says_data_persists",
           "what_the_test_found"]
