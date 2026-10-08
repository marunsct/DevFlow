"""What every JavaScript pack shares: node:test units and Playwright acceptance runs."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

#: The Playwright release whose browser build the image installs. A different
#: version looks for a browser build that is not there.
PLAYWRIGHT = "1.63.0"

#: The accessibility engine the page probe runs (`page_check`). A dev
#: dependency only: it is test setup, never shipped, and a brief's "no external
#: dependencies" constrains what ships (`app.agents.brief_constraints`).
AXE_CORE = "4.14.0"

UNIT_SCRIPT = (
    "mkdir -p test-results && node --test --test-reporter=spec --test-reporter-destination=stdout "
    "--test-reporter=junit --test-reporter-destination=test-results/unit.xml tests/"
)

GITIGNORE = """node_modules/
test-results/
playwright-report/
data/
"""

INSTALL = (("npm", "install", "--no-audit", "--no-fund"),)
UNIT_TEST = ("npm", "test")
ACCEPTANCE_TEST = ("npm", "run", "test:acceptance")

#: The Node.js major version the harness's own image runs, so CI tests the
#: product on the runtime it was built and tested on.
NODE_MAJOR = "20"

CI_SETUP = (
    "      - uses: actions/setup-node@v4\n"
    "        with:\n"
    f"          node-version: {NODE_MAJOR}",
)

#: Playwright's browser build, which the harness's image already has and a CI
#: runner does not. Only for packs whose acceptance tests drive a page.
CI_BROWSERS = ("npx playwright install --with-deps chromium",)


def service_dockerfile(start: str, port: int = 3000) -> str:
    """A container for a Node.js service, started the way its `start` script starts it.

    Dependencies are installed before the source is copied, so a change to the
    code does not reinstall them; it runs as the image's unprivileged `node`
    user; and it listens on every interface (`HOST`), which inside a container
    is the only way anything reaches it. Configuration comes from the
    environment the service already reads - `PORT`, `DATA_DIR` - never a
    credential written into the file.
    """
    argv = ", ".join(f'"{part}"' for part in start.split())
    return (
        "# {{title}}: build with `docker build -t {{project}} .`, run with\n"
        f"# `docker run -p {port}:{port} -v {{{{project}}}}-data:/app/data {{{{project}}}}`.\n"
        f"FROM node:{NODE_MAJOR}-slim\n"
        f"ENV NODE_ENV=production HOST=0.0.0.0 PORT={port} DATA_DIR=/app/data\n"
        "WORKDIR /app\n"
        "COPY package.json package-lock.json* ./\n"
        "RUN npm install --omit=dev --no-audit --no-fund\n"
        "COPY . .\n"
        "RUN mkdir -p /app/data && chown -R node:node /app/data\n"
        "USER node\n"
        f"EXPOSE {port}\n"
        f"CMD [{argv}]\n"
    )


DOCKERIGNORE = """node_modules/
test-results/
playwright-report/
data/
tests/
acceptance/
.git/
*.log
"""


#: Where the page check writes what the page reported, relative to the project.
PAGE_LOAD_REPORT = "test-results/page-load.json"

#: The kept global setup of a pack whose product is a page. `%(page)s` is the
#: page's path. See `page_check`.
_PAGE_CHECK = """// Kept by the harness. Before any test runs, the page is loaded once with
// nothing driving it, and what it reports going wrong and what it shows are
// written down and printed: an error thrown while its scripts load stops all
// the code after it, and a control nothing renders is never there - either way
// every test fails with "element not found", which says nothing about why.
import { chromium } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';

const NOT_THE_PRODUCT = /favicon\\.ico/;

export default async function pageCheck(config) {
  const baseURL = config.projects?.[0]?.use?.baseURL;
  if (!baseURL) return;
  const problems = [];
  let shows = '';
  // How the page sits on a phone, and how it looks: measured once here, so
  // every run of the suite records it. See `app.analysis.interface_checks`.
  const layout = {};
  const root = config.configFile ? dirname(config.configFile) : process.cwd();
  mkdirSync(join(root, 'test-results'), { recursive: true });
  const note = (text) => {
    if (problems.length < 20 && !problems.includes(text)) problems.push(text);
  };
  let browser;
  try {
    browser = await chromium.launch();
  } catch (error) {
    // Not the product's problem, and the tests will say so themselves.
    console.log(`The page check could not start a browser: ${String(error.message).split('\\n')[0]}`);
    return;
  }
  try {
    const page = await browser.newPage();
    page.on('pageerror', (error) => note(`uncaught error: ${error.message}`));
    page.on('console', (message) => {
      if (message.type() === 'error' && !message.text().startsWith('Failed to load resource')) {
        note(`console error: ${message.text()}`);
      }
    });
    page.on('requestfailed', (request) => {
      if (!NOT_THE_PRODUCT.test(request.url())) {
        note(`request failed: ${request.url()} (${request.failure()?.errorText})`);
      }
    });
    page.on('response', (response) => {
      if (response.status() >= 400 && !NOT_THE_PRODUCT.test(response.url())) {
        note(`HTTP ${response.status()} for ${response.url()}`);
      }
    });
    await page.goto(new URL('%(page)s', baseURL).href, { waitUntil: 'load', timeout: 10_000 });
    await page.waitForTimeout(500);
    // What a person opening the page sees, as the accessibility tree the
    // tests' locators search: a control a test cannot find is either absent
    // here or named differently here.
    shows = (await page.locator('body').ariaSnapshot({ timeout: 3_000 })).slice(0, 1_500);
    try {
      // What an accessibility engine finds on the page as it loads: only what
      // it calls serious or critical. axe-core is a dev dependency of the
      // project; without it this measures nothing and says nothing.
      const axe = createRequire(import.meta.url).resolve('axe-core/axe.min.js');
      await page.addScriptTag({ path: axe });
      layout.accessibility = await page.evaluate(async () => {
        const found = await window.axe.run(document, { resultTypes: ['violations'] });
        return found.violations
          .filter((rule) => rule.impact === 'serious' || rule.impact === 'critical')
          .slice(0, 10)
          .map((rule) => ({
            id: rule.id,
            impact: rule.impact,
            help: rule.help,
            count: rule.nodes.length,
            where: rule.nodes.slice(0, 3).map((node) => node.target.join(' ')),
            // What axe measured, element by element: for contrast, the two
            // colours, the ratio and the ratio needed. Without it one run's
            // fixers changed colours blind for three rounds.
            why: rule.nodes.slice(0, 3).map((node) => String(
              (node.any && node.any[0] && node.any[0].message) || node.failureSummary || '',
            ).replace(/\\s+/g, ' ').slice(0, 240)),
          }));
      });
    } catch (error) {
      // Not installed, or the page would not run it: nothing is said.
    }
    try {
      await page.setViewportSize({ width: 1280, height: 800 });
      await page.screenshot({ path: join(root, 'test-results/page-desktop.png'), fullPage: true });
      await page.setViewportSize({ width: 375, height: 740 });
      await page.waitForTimeout(200);
      layout.phoneOverflow = await page.evaluate(
        () => Math.max(0, document.documentElement.scrollWidth - window.innerWidth),
      );
      await page.screenshot({ path: join(root, 'test-results/page-phone.png'), fullPage: true });
    } catch (error) {
      // A measurement that cannot be taken says nothing; the tests still run.
    }
  } catch (error) {
    note(`the page did not load: ${String(error.message).split('\\n')[0]}`);
  } finally {
    await browser.close();
  }
  writeFileSync(join(root, '%(report)s'), JSON.stringify({ problems, shows, layout }, null, 2));
  if (problems.length) {
    console.log(
      '\\nThe page reported these problems when it loaded, before any test touched it:\\n'
      + problems.map((problem) => `  - ${problem}`).join('\\n')
      + '\\nCode that throws while the page loads stops everything after it, so the tests '
      + 'then fail with "element not found". Fix these first.\\n',
    );
  }
  if (shows) {
    console.log(`\\nThe page, loaded with nothing driving it, shows:\\n${shows}\\n`);
  }
  if (layout.accessibility?.length) {
    console.log(
      '\\nAn accessibility check of the page as it loads finds these serious or critical problems:\\n'
      + layout.accessibility
        .map((rule) => `  - ${rule.id} (${rule.impact}): ${rule.help} - ${rule.count} element(s), e.g. ${rule.where.join(', ')}`
          + (rule.why || []).filter(Boolean).map((why, i) => `\\n      ${rule.where[i] || ''}: ${why}`).join(''))
        .join('\\n')
      + '\\n',
    );
  }
}
"""


def page_check(page_path: str = "/") -> str:
    """The kept global setup that loads the page once and records what it reports.

    Measured on one run: the page threw `loadTasks(...).then is not a function`
    while its scripts loaded, so nothing rendered, and every test failed with
    "element not found". The stages after it edited labels and markup,
    because nothing they could run showed the error - an engineer would have
    seen it in the browser console at once. Playwright starts the
    server before its global setup, so this sees the product the tests see,
    and its output is in every run of the suite, the agents' and the
    harness's alike.

    It also records what the page shows - its accessibility tree, which is
    what the tests' locators search. On another run the page loaded cleanly
    and every test still waited for a field labelled "Title": the form was
    built by an `init()` nothing called. Six fix stages worked on unit-test
    setup instead, because "element not found" cannot tell an absent control
    from a misnamed one, and the page's own tree tells both at a glance.
    """
    return _PAGE_CHECK % {"page": page_path, "report": PAGE_LOAD_REPORT}


def playwright_config(
    server_command: str,
    ready_path: str = "/",
    screenshot: str = "only-on-failure",
    *,
    checks_the_page: bool = False,
) -> str:
    """A Playwright configuration that starts the product with `server_command`.

    The port is chosen once per run of the suite and published in
    `ACCEPTANCE_PORT`, because Playwright evaluates this file in its main
    process and again in each worker: a random pick per evaluation started the
    server on one port and pointed every test at another, so every run an agent
    started failed with ERR_CONNECTION_REFUSED (only the harness's own runs,
    which pass the port, worked) - and the agents, reasonably, went after the
    server and this file, dozens of refused calls a run.

    The server is told its port in `PORT`, and gets a fresh `DATA_DIR` under
    `test-results/` for every run of the suite - named fresh, not emptied by a
    shell chain: one run's stages copied `rm -rf ... && node ...` out of this
    file and tried to run it themselves, fourteen times. A product with a page keeps a
    screenshot of every test (`screenshot="on"`) as evidence for its reviews.
    """
    return """import { defineConfig } from '@playwright/test';

// The harness runs this suite; keep it as it is. Acceptance tests reach the
// product through the server below - never from disk, and never on another port.
// The harness passes a free port; a run started by hand picks one at random, so
// two runs on one machine never fight over it. Picked once and put in the
// environment: Playwright loads this file again in every worker process, and
// workers inherit the environment, so they all reach the one server started.
process.env.ACCEPTANCE_PORT ||= String(20000 + Math.floor(Math.random() * 20000));
process.env.ACCEPTANCE_RUN ||= String(Date.now());
const port = Number(process.env.ACCEPTANCE_PORT);

export default defineConfig({
  testDir: './acceptance',
  testMatch: '**/*.spec.js',
  // Short on purpose: the suite is written before the product, and runs red
  // many times a sprint. A control that does not exist yet must fail in
  // seconds, not wait out a 30-second default per action.
  timeout: 15_000,
  expect: { timeout: 3_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['junit', { outputFile: 'test-results/acceptance.xml' }]],
  outputDir: 'test-results/evidence',%(global_setup)s
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    actionTimeout: 3_000,
    navigationTimeout: 10_000,
    screenshot: '%(screenshot)s',
    trace: 'off',
  },
  webServer: {
    command: `%(command)s`,
    url: `http://127.0.0.1:${port}%(ready)s`,
    // A fresh, empty data directory for every run of the suite.
    env: { PORT: String(port), DATA_DIR: `test-results/acceptance-data-${port}-${process.env.ACCEPTANCE_RUN}` },
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
""" % {
        "command": server_command, "ready": ready_path, "screenshot": screenshot,
        "global_setup": "\n  globalSetup: './playwright.setup.mjs'," if checks_the_page else "",
    }


UNIT_GUIDE = """Unit tests go in `tests/`, one file per module, named `<module>.test.js`, using
`node:test` and `node:assert/strict`, and import the product's modules directly.
Run them with `npm test`. Install a dependency with `npm install <name>` (add
`--save-dev` for one only tests use). Never start a server yourself."""

#: Playwright's per-failure context: the test's name, then the page's
#: accessibility tree at the moment it failed, in a fenced yaml block.
_CONTEXT_NAME = re.compile(r"^- Name: .*? >> (.+)$", re.M)
_CONTEXT_PAGE = re.compile(r"```yaml\n(.*?)\n```", re.S)


def failure_pages(project_root: Path, evidence_dir: str) -> dict[str, str]:
    """Test title -> the page's accessibility tree when that test failed.

    Playwright writes `error-context.md` beside each failure's screenshot. Its
    page snapshot says what was there when the assertion gave up - on one run
    a list item whose Edit button changed nothing when clicked and whose
    checkbox had no label - where the failure message says only "element not
    found". Never raises.
    """
    found: dict[str, str] = {}
    try:
        for path in sorted((project_root / evidence_dir).glob("*/error-context.md")):
            text = path.read_text(encoding="utf-8", errors="replace")
            name, page = _CONTEXT_NAME.search(text), _CONTEXT_PAGE.search(text)
            if name and page:
                title = name.group(1).strip()
                # Nested in `describe` blocks the name is "outer >> title"
                # here and "outer › title" in the JUnit report: keep both
                # the whole name and the title alone.
                for key in (title, title.split(" >> ")[-1].strip()):
                    found.setdefault(key, page.group(1).strip())
    except OSError:
        pass
    return found


#: The locator a Playwright action was waiting for, from its call log: the
#: last `getByRole`, `getByLabel` or `getByText` with a string argument.
_WAITED_FOR = re.compile(r"waiting for (.*)")
_BY_ROLE = re.compile(r"""getByRole\((['"])(\w+)\1\s*(?:,\s*\{([^}]*)\})?\)""")
_BY_NAME = re.compile(r"""getBy(Label|Text)\((['"])((?:(?!\2).)*)\2\s*(?:,\s*\{([^}]*)\})?\)""")
_NAME_OPTION = re.compile(r"""name:\s*(['"])((?:(?!\1).)*)\1""")
_EXACT_OPTION = re.compile(r"exact:\s*true")

#: A node in Playwright's page snapshot: `- textbox "Title:" [ref=e5]`, and
#: text on its own: `- text: "Title:"`.
_SNAPSHOT_NODE = re.compile(r'^[ \t]*-[ \t]*([a-z]+)[ \t]+"((?:[^"\\]|\\.)*)"', re.M)
_SNAPSHOT_TEXT = re.compile(r'^[ \t]*-[ \t]*text:[ \t]*"?(.*?)"?[ \t]*$', re.M)
#: An element's own text after its role: `- paragraph: Buy milk`,
#: `- listitem [ref=e9]: Read`. An input's value is shown the same way
#: (`- textbox "Title": milk`) and is not text a locator finds, so not those.
_SNAPSHOT_CONTENT = re.compile(
    r'^[ \t]*-[ \t]*(?!text:)([a-z]+)(?:[ \t]+"(?:[^"\\]|\\.)*")?(?:[ \t]+\[[^\]]*\])*:[ \t]+"?(.+?)"?[ \t]*$', re.M
)
_HOLDS_A_VALUE = frozenset({"textbox", "searchbox", "combobox", "spinbutton", "slider"})


def _loose(name: str) -> str:
    return re.sub(r"[\W_]+", "", name).lower()


def _same_as(wanted: str, name: str, exact: bool) -> bool:
    """Whether Playwright would take `name` for `wanted`: exact is the whole
    string, case and all; otherwise a case-insensitive substring. Both with
    whitespace normalised, as Playwright does."""
    wanted, name = " ".join(wanted.split()), " ".join(name.split())
    return name == wanted if exact else wanted.lower() in name.lower()


def _what_it_waited_for(message: str) -> tuple[str, str, str, bool, str] | None:
    """(kind, role, name, exact, locator text) of the last named locator a
    failed action waited for, or None."""
    waits = _WAITED_FOR.findall(message or "")
    if not waits:
        return None
    by_role = list(_BY_ROLE.finditer(waits[-1]))
    by_name = list(_BY_NAME.finditer(waits[-1]))
    last_role = by_role[-1] if by_role else None
    last_name = by_name[-1] if by_name else None
    if last_role and (not last_name or last_role.start() > last_name.start()):
        options = last_role.group(3) or ""
        named = _NAME_OPTION.search(options)
        if not named:
            return None
        return ("role", last_role.group(2), named.group(2),
                bool(_EXACT_OPTION.search(options)), last_role.group(0))
    if last_name:
        return (last_name.group(1).lower(), "", last_name.group(3),
                bool(_EXACT_OPTION.search(last_name.group(4) or "")), last_name.group(0))
    return None


def _nodes_and_texts(page: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    nodes = [(role, name) for role, name in _SNAPSHOT_NODE.findall(page) if role != "text"]
    texts = [("text", text) for text in _SNAPSHOT_TEXT.findall(page) if text] + [
        ("text", text) for role, text in _SNAPSHOT_CONTENT.findall(page)
        if role not in _HOLDS_A_VALUE
    ]
    return nodes, texts


def _found(sought: tuple[str, str, str, bool, str], page: str) -> bool:
    """Whether anything on `page` is what `sought` looks for, by Playwright's rules."""
    kind, role, wanted, exact, _ = sought
    nodes, texts = _nodes_and_texts(page)
    if kind == "role":
        candidates = [(r, n) for r, n in nodes if r == role]
    elif kind == "label":
        candidates = nodes
    else:
        candidates = nodes + texts
    return any(_same_as(wanted, name, exact) for _, name in candidates)


#: What a page snapshot marks that is not the page: element refs, focus, cursor.
_SNAPSHOT_MARKS = re.compile(r"\s*\[(?:ref=\w+|active|cursor=\w+)\]")


def _as_shown(page: str) -> str:
    return "\n".join(_SNAPSHOT_MARKS.sub("", line).rstrip() for line in (page or "").strip().splitlines())


def needs_what_it_never_made(failures: Sequence[tuple[str, str, str]], fresh: str) -> dict[str, str]:
    """Locked tests that wait for something only data brings, having made none.

    `failures` is (test name, failure message, page it failed on); `fresh` is
    the page as it first loads. One run locked three tests that opened the
    page and at once waited for an item's own controls - `checkbox "Done"`,
    `button "Edit"`, `button "Delete"` - while every test starts from an empty
    product. Each failed on the page exactly as it first loads, so it had
    created nothing; and the product showed `checkbox "Done"` on the page
    another test failed on, after that test had added something. Only both
    together say so: a control missing from a fresh page that no other page
    shows either is the product's to build. Test name -> why. Never raises.
    """
    found: dict[str, str] = {}
    fresh_page = _as_shown(fresh)
    if not fresh_page:
        return found
    for name, message, page in failures:
        if _as_shown(page) != fresh_page:
            continue
        sought = _what_it_waited_for(message)
        if sought is None or _found(sought, fresh_page):
            continue
        for other, _, elsewhere in failures:
            if other == name or _as_shown(elsewhere) == fresh_page or not _found(sought, elsewhere):
                continue
            found[name] = (
                f"it waits for {sought[4]} on the page exactly as it first loads - it has "
                f"created nothing yet - and the product shows that only once something "
                f"exists: it is on the page `{other}` failed on, after that test made "
                "something"
            )
            break
    return found


def near_misses(message: str, page: str) -> str:
    """What on the page a failed locator nearly matched, or "".

    One run spent six fix stages on a locked test waiting for
    `getByLabel('Title', { exact: true })` while the page it failed on showed
    `textbox "Title:"`. Both were in front of every stage - the call log and
    the page - and none connected them. Said only when nothing on the page
    matches the locator under Playwright's own rules and something differs
    from it only in case, punctuation or role; otherwise the miss is about
    something else (timing, visibility, the action before it) and this is
    silent. Never raises.
    """
    try:
        sought = _what_it_waited_for(message)
        if sought is None or not page:
            return ""
        kind, wanted_role, wanted, exact, locator = sought
        nodes, texts = _nodes_and_texts(page)
        if _found(sought, page):
            return ""
        near = []
        for role, name in nodes + (texts if kind == "text" else []):
            close = _loose(name) == _loose(wanted) or (
                kind == "role" and role != wanted_role and _same_as(wanted, name, exact)
            )
            shown = f'{role} "{name}"' if role != "text" else f'text "{name}"'
            if close and shown not in near:
                near.append(shown)
        if not near:
            return ""
        return (
            f"\nNearly there: the test waits for {locator}, and nothing on the page "
            f"matches it; the page has {', '.join(near[:3])}. A locked test is the "
            "requirement, so the page is what changes to match it."
        )
    except Exception:  # noqa: BLE001 - a hint is never worth a failure
        return ""


#: A matcher's declaration in the runner's own type definitions.
_DECLARED_MATCHER = re.compile(r"^\s+(to[A-Z][A-Za-z]*)\s*[(<]", re.M)


def playwright_assertions(project_root: Path) -> frozenset[str]:
    """Every `expect(...).toX` matcher the installed Playwright declares, or empty when unreadable.

    Read from the project's own `node_modules`, so it is the version the suite
    will run on. Measured on one run: a locked suite called
    `expect(...).toBeUnchecked()`, which does not exist, in two tests that
    failed before reaching it until the product was built - and then could
    never pass.
    """
    names: set[str] = set()
    for relative in ("node_modules/playwright/types/test.d.ts", "node_modules/@playwright/test/types/test.d.ts"):
        try:
            names.update(_DECLARED_MATCHER.findall((project_root / relative).read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
    return frozenset(names)


#: How a browser test finds a control, shared by every pack with a page. The
#: matcher sentence because two runs' QA wrote `toBeUnchecked()`, which
#: Playwright does not define; the check caught it each time
#: (`assertions_that_do_not_exist`), and each time cost the suite a send-back.
#:
#: The last because `check()` confirms the new state on the control after
#: clicking it. One run's locked suite checked the last record shown in a
#: view of unfinished records; the product rightly took it out of that view at
#: once, `check()` timed out on a control that was gone, and two criteria were
#: deferred as undeliverable on a product the benchmark's hidden tests passed
#: 10 of 10.
FIND_CONTROLS = """Find each control by the name a person sees, exactly as the brief gives
it: a field the brief says is labelled "Email" is
`page.getByLabel('Email', { exact: true })`, a button named "Send" is
`page.getByRole('button', { name: 'Send', exact: true })`, an entry of a list is
`page.getByRole('listitem')`. A placeholder is not a label, and a test id or a CSS
class is not something a person sees: never find a control by them - a product
could pass such a test and still lack what the brief asked for. Nor by a CSS
selector on its role: `locator('[role="listitem"]')` matches only an element
carrying that attribute, never an `<li>` whose role is its own. Assert only with
matchers Playwright defines: a checked box is `toBeChecked()`, an unchecked one
`not.toBeChecked()` - there is no `toBeUnchecked`. An action that takes its own
control off the page - a record that no longer belongs in the view shown once it
changes - is a `click()`, not `check()` or `uncheck()`: those confirm the new
state on the control afterwards, a control that has gone cannot be confirmed,
and the test times out on a product that did the right thing. Assert the change
on what the page shows after it. Act on a locator - `page.getByLabel(...).fill(...)`,
never `page.fill(selector, ...)` or `page.click(selector)` - and never take
`.first()` of a control found by its name: both act on whichever match comes
first, so a page that shows the same control twice still passes, where a
locator refuses more than one. A locator found by its text keeps that filter:
once the test changes the text, find the item again by its new text. A list
item takes no name from its text: find one by
`page.getByRole('listitem').filter({ hasText: '...' })`, never by
`getByRole('listitem', { name: '...' })`, which matches none. What an edit
shows - its field, the control that confirms it - is found on the page by its
label or name, not inside the item: while it is edited the item's text is in a
field, and a field's value is not text a filter can match."""

#: Locators that find a control by something no person sees. A suite that
#: uses one is sent back by the acceptance review (`suite.locators_nobody_sees`).
#: Measured on one run: QA found a field the brief called "labelled" by its
#: placeholder, the product gave it a placeholder and no label, the locked
#: suite passed, and three of the benchmark's hidden tests - which find it by
#: its label - failed.
#:
#: A CSS selector on `role` too: `[role="listitem"]` matches only an element
#: that carries the attribute, never one whose role is its own - an `<li>` in a
#: list, a `<button>`. One run's locked suite found every task that way, so a
#: product rendering a plain list would have failed it while doing exactly what
#: the brief asked.
#:
#: And any other CSS selector on an attribute, a class or an id. One run's
#: locked suite found every completion control as
#: `input[type="checkbox"].task-complete`: the brief labelled it "Done", the
#: product gave it no label, the suite passed - and the two hidden tests that
#: find it by its label failed. A selector on the document's head (a
#: `meta[name="viewport"]`) is not a control, and an engine prefix
#: (`text=`, `role=`) is not CSS.
LOCATORS_NOBODY_SEES = (
    r"\bgetByPlaceholder\s*\(",
    r"\bgetByTestId\s*\(",
    r"""\blocator\s*\(\s*(['"`])(?![a-z_-]+=)(?!\s*(?:meta|link|script|style|head|html|title)\b)"""
    r"""(?:(?!\1).)*?(?:\[\s*[\w-]+\s*[~|^$*]?=|[.#][A-Za-z_-])""",
)

#: Roles that take no name from what they show, found by a `name` anyway: the
#: locator matches nothing on a page that shows exactly what the brief asks.
#: Measured on one run, in a browser: `getByRole('listitem', { name: 'Original' })`
#: found 0 items on a page listing "Original"; `filter({ hasText })` found 1.
#: The locked edit tests that used it could never pass.
LOCATORS_BY_A_NAME_THE_ROLE_NEVER_HAS = (
    r"""\bgetByRole\s*\(\s*['"`](?:listitem|list|paragraph|generic)['"`]\s*,\s*\{[^}]*\bname\s*:""",
)


#: Ways a test acts on whichever of several matches comes first. Playwright's
#: locators are strict - one that matches two controls refuses to act - and
#: these are the ways round it. One run's locked suite pressed its filters
#: with `page.click('text=Active')`; the product drew every filter twice, the
#: suite passed, and the hidden test that finds the filter by its name failed
#: on "resolved to 2 elements".
LOCATORS_THAT_PICK_ONE = (
    r"""\bpage\s*\.\s*(?:click|dblclick|fill|check|uncheck|hover|press|type|tap|focus|"""
    r"""selectOption|setChecked|setInputFiles|dispatchEvent)\s*\(\s*['"`]""",
    r"""\b(?:getByLabel|getByText|getByTitle|getByAltText)\s*\([^()]*\)\s*\.\s*(?:first|last|nth)\s*\(""",
    r"""\bgetByRole\s*\([^()]*\bname\s*:[^()]*\)\s*\.\s*(?:first|last|nth)\s*\(""",
    r"""\b(?:locator|filter)\s*\([^()]*\bhasText\s*:[^()]*\)\s*\.\s*(?:first|last|nth)\s*\(""",
)

#: A locator found by the text it shows: `const row = page.getByRole(...).filter({ hasText: 'x' })`.
_FOUND_BY_TEXT = re.compile(
    r"""\b(?:const|let|var)\s+(\w+)\s*=\s*[^;\n]*?\.filter\(\s*\{\s*hasText\s*:\s*(?:(['"`])(.+?)\2|/(.+?)/\w*)"""
)
_A_TEST = re.compile(r"\btest\s*\(")


def asserted_without_the_text_it_is_found_by(text: str) -> list[tuple[int, str, str]]:
    """(line, locator, text) where a test finds something by a text and asserts it does not show it.

    A locator filtered by a text matches only what shows that text, so asserting
    that what it finds - or anything inside it - does not contain the text can
    pass only on a page that hides the text somewhere in it. Measured on one
    run: the locked test found an item by its title, edited the title, and
    asserted the item no longer showed the old one; a fix stage kept the old
    title in an invisible element "for locator matching", and the customer's
    check that the old title is gone failed.
    """
    found = []
    starts = [match.start() for match in _A_TEST.finditer(text)] + [len(text)]
    for begin, end in zip(starts, starts[1:]):
        body = text[begin:end]
        for match in _FOUND_BY_TEXT.finditer(body):
            name, said = match.group(1), match.group(3) or match.group(4) or ""
            if not said:
                continue
            negated = re.compile(
                r"expect\(\s*" + re.escape(name) + r"\b[^;]*?\)\s*\.\s*not\s*\.\s*(?:toContainText|toHaveText)\(\s*"
                r"(?:(['\"`])" + re.escape(said) + r"\1|/" + re.escape(said) + r"/)"
            )
            for hit in negated.finditer(body, match.end()):
                found.append((text.count("\n", 0, begin + hit.start()) + 1, name, said))
    return found


_FAILED_LOCATOR_TEXT = re.compile(r"""Locator:[^\n]*\.filter\(\{\s*hasText:\s*(?:'([^'\n]+)'|"([^"\n]+)"|/([^/\n]+)/\w*)""")
_EXPECTED_TEXT = re.compile(r'Expected (?:substring|string): "([^"\n]+)"')


def a_locator_left_behind(message: str) -> tuple[str, str] | None:
    """(old text, new text) when a test failed on a locator found by a text the page no longer shows.

    The test changed the text, then looked for the new one through the
    locator it had found by the old: "element(s) not found", while the page it
    failed on shows the new text and not the old. The product did the change;
    the test cannot see it. Measured on one run: two locked tests of editing
    failed this way on every round of two attempts at a sprint, handed each
    time to product fixers who may not change the suite.
    """
    found = _FAILED_LOCATOR_TEXT.search(message or "")
    expected = _EXPECTED_TEXT.search(message or "")
    if not found or not expected or "element(s) not found" not in message:
        return None
    old = next(group for group in found.groups() if group)
    new = expected.group(1)
    if old in new:
        return None
    page = message.split("What the page showed when this failed:", 1)
    if len(page) < 2 or new not in page[1] or old in page[1]:
        return None
    return old, new


_A_HELPER = re.compile(r"(?:async\s+)?function\s+(\w+)\s*\(|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(")


def tests_that_never_open_the_page(text: str) -> list[tuple[int, str]]:
    """(line, title) of each test that acts on `page` with nothing that opens it.

    Every test starts in a blank browser tab, so one that never calls `goto` -
    itself, in a `beforeEach`, or through a helper of the file that does - acts
    on a page with nothing on it and can never pass. Measured on one run: two
    locked tests filled the title field with no `page.goto('/')`, timed out
    on every round, and the QA lead asked whether any right product could pass
    them said none could not.
    """
    if re.search(r"\bbeforeEach\s*\([^)]*\)?[\s\S]{0,600}?\bgoto\s*\(", text):
        return []
    opening = set()
    starts = [match.start() for match in _A_TEST.finditer(text)]
    for match in _A_HELPER.finditer(text):
        name = match.group(1) or match.group(2)
        following = text[match.end():next((at for at in starts if at > match.start()), len(text))]
        if name and re.search(r"\bgoto\s*\(", following[:2000]):
            opening.add(name)
    found = []
    for begin, end in zip(starts, starts[1:] + [len(text)]):
        body = text[begin:end]
        if "page" not in body or re.search(r"\bgoto\s*\(", body):
            continue
        if any(re.search(rf"\b{re.escape(name)}\s*\(", body) for name in opening):
            continue
        title = re.match(r"""test\s*\(\s*(['"`])(.*?)\1""", body)
        found.append((text.count("\n", 0, begin) + 1, title.group(2) if title else "a test"))
    return found


#: Something only the test can know: the clock, a random number, a fresh id.
_MADE_AT_RUN_TIME = re.compile(
    r"\bDate\s*\.\s*now\s*\(|\bMath\s*\.\s*random\s*\(|\brandomUUID\s*\(|\bperformance\s*\.\s*now\s*\(|"
    r"\bnew\s+Date\s*\(\s*\)\s*\.\s*(?:getTime|valueOf|toISOString)\s*\("
)
_A_BINDING = re.compile(r"\b(?:const|let|var)\s+(\w+)\s*=\s*([^;\n]+)")
#: What stands just before a value a test looks for, not one it gives:
#: `hasText: v`, `getByRole('row', { name: v`, `getByText(v`, `toHaveText(v`,
#: `text=${v`. A `name:` anywhere else may be a request body's - given.
_LOOKED_FOR = re.compile(
    r"""(?:\bhasText\s*:|\bgetByRole\s*\([^()]*\{[^{}()]*\bname\s*:|\bgetBy\w+\s*\(|\.\s*to[A-Z]\w*\s*\(|"""
    r"""text=\$\{|has-text\(\s*['"`]?\$\{)\s*$"""
)


def expects_what_it_never_gave(text: str) -> list[tuple[int, str, str]]:
    """(line, title, value) of each test that looks for a value it made and never gave the product.

    A value made by the test at run time - from the clock, a random number, a
    fresh id, or a helper of the file that uses one - exists only in the test.
    A test that looks for it on the page without first entering it, sending
    it, or passing it to anything that might, can never pass. Measured on one
    run: the locked test of adding, editing and deleting in turn made a new
    title, pressed Save without typing it, and looked for an item showing it;
    every round of three sprints failed it, and the criterion was deferred.
    """
    starts = [match.start() for match in _A_TEST.finditer(text)]
    makers = set()
    helpers = list(_A_HELPER.finditer(text))
    bounds = sorted({*starts, *(match.start() for match in helpers), len(text)})
    for match in helpers:
        name = match.group(1) or match.group(2)
        body = text[match.end():next(at for at in bounds if at > match.start())]
        if name and _MADE_AT_RUN_TIME.search(body[:400]):
            makers.add(name)
    made_by = re.compile(
        _MADE_AT_RUN_TIME.pattern
        + "".join(rf"|\b{re.escape(name)}\s*\(" for name in sorted(makers))
    )
    found = []
    for begin, end in zip(starts, starts[1:] + [len(text)]):
        body = text[begin:end]
        title = re.match(r"""test\s*\(\s*(['"`])(.*?)\1""", body)
        for binding in _A_BINDING.finditer(body):
            value, made = binding.group(1), binding.group(2)
            if not made_by.search(made):
                continue
            uses = [use for use in re.finditer(rf"\b{re.escape(value)}\b", body) if use.start() >= binding.end()]
            looked = [use for use in uses if _LOOKED_FOR.search(body[max(0, use.start() - 120):use.start()])]
            if looked and len(looked) == len(uses):
                line = text.count("\n", 0, begin + looked[0].start()) + 1
                found.append((line, title.group(2) if title else "a test", value))
    return found


#: A position in a list a test reads: `.nth(1)`, `.first()`, `.last()`.
_A_POSITION = re.compile(r"\.\s*(?:nth\s*\(\s*(\d+)\s*\)|(first)\s*\(\s*\)|(last)\s*\(\s*\))")
#: What a test asserts a thing shows.
_ITS_TEXT = re.compile(r"\b(?:toContainText|toHaveText)\s*\(|\bgetByText\s*\(")


def positions_it_asserts(text: str) -> list[tuple[int, str, list[str]]]:
    """(line, title, positions) of each test that asserts what is shown at two or more places in a list.

    Reading a position to act on it - the first item's checkbox - says nothing
    about order; asserting what two positions show does. Measured on one run:
    the locked list test added two items and expected the second at
    position 0 and the first at position 1 - newest first - while the locked
    removal test removed the first item and expected the second to remain -
    oldest first. Each fix that made one pass broke the other, twice, and
    neither criterion said anything about order.
    """
    found = []
    starts = [match.start() for match in _A_TEST.finditer(text)]
    for begin, end in zip(starts, starts[1:] + [len(text)]):
        body = text[begin:end]
        title = re.match(r"""test\s*\(\s*(['"`])(.*?)\1""", body)
        held: dict[str, str] = {}
        positions: list[str] = []
        first_line = 0
        offset = 0
        for statement in body.split(";"):
            where = [
                match.group(1) or ("0" if match.group(2) else "last")
                for match in _A_POSITION.finditer(statement)
            ]
            bound = re.match(r"\s*(?:const|let|var)\s+(\w+)\s*=", statement)
            if bound and where:
                held[bound.group(1)] = where[-1]
            if _ITS_TEXT.search(statement):
                asserted = where[-1:] or [
                    held[name] for name in held if re.search(rf"\b{re.escape(name)}\b", statement)
                ][-1:]
                for position in asserted:
                    if position not in positions:
                        positions.append(position)
                        first_line = first_line or text.count("\n", 0, begin + offset) + 1
            offset += len(statement) + 1
        if len(positions) >= 2:
            found.append((first_line, title.group(2) if title else "a test", positions))
    return found


_FILTERED_BY_TEXT = re.compile(r"""\.filter\(\{\s*hasText:\s*(?:'([^'\n]+)'|"([^"\n]+)"|/([^/\n]+)/\w*)""")
#: What a test looked for inside the filtered item: `.getByLabel('Edit title')`
#: or `.getByRole('button', { name: 'Save' })`.
_WITHIN_THE_FILTER = re.compile(
    r"""^\s*\}?\s*\)?\s*\.(?:getByLabel\(\s*'([^']+)'|getByRole\(\s*'\w+'\s*,\s*\{\s*name:\s*'([^']+)')"""
)
#: A line of the page tree for a field, its value after the colon.
_A_FIELD_LINE = re.compile(r"^\s*-\s*(?:textbox|searchbox|combobox|spinbutton)\b.*:\s*(.+)$")


def a_locator_filtered_by_a_field_value(message: str) -> str | None:
    """The text, when a test failed on a locator filtered by it and the page shows it only in a field.

    A field's value is not the text of what holds it, so `filter({ hasText })`
    stops matching an item the moment its text moves into a field to be
    edited. Measured on one run: three locked edit tests found the "Edit
    title" field and the "Save" control inside the item filtered by its title;
    the page they failed on showed the item holding a field "Edit title" whose
    value was that title - and nothing else with it - on every round of three
    attempts at a sprint.
    """
    message = message or ""
    found = _FILTERED_BY_TEXT.search(message)
    if not found or not ("Timeout" in message or "element(s) not found" in message):
        return None
    said = next(group for group in found.groups() if group)
    page = message.split("What the page showed when this failed:", 1)
    if len(page) < 2:
        return None
    lines = [line for line in page[1].splitlines() if said in line]
    if lines:
        return said if all(_A_FIELD_LINE.match(line) for line in lines) else None
    # Shown nowhere at all: the field's value was changed too. The test's own
    # target - the field or control it looked for inside the item - being on
    # the page is the evidence the item is there, being edited.
    target = _WITHIN_THE_FILTER.search(message[found.end():found.end() + 200])
    wanted = target and (target.group(1) or target.group(2))
    if wanted and f'"{wanted}"' in page[1]:
        return said
    return None


#: How a test finds a control by a name, with `{name}` for the name escaped.
#: A suite that never finds a control the brief names this way cannot tell a
#: product that gave it that name from one that did not.
FINDS_BY_NAME = (
    r"""\bgetByLabel\s*\(\s*(?:(['"`]){name}\1|/\^?{name}\$?/)""",
    r"""\bgetByRole\s*\([^()]*\bname\s*:\s*(?:(['"`]){name}\1|/\^?{name}\$?/)""",
)

#: The whole shape of a test, callback included. The example once ended in
#: `...`; one run's QA wrote `async (page) => ...`, Playwright refused every
#: test before running any ("First argument must use the object destructuring
#: pattern"), and QA spent ten minutes reading Playwright's own source to learn
#: that a test receives its fixtures as one object.
NAMING = """Each test's title starts with the id of the criterion it proves, in square
brackets, and its callback takes the fixtures it uses as one destructured object:
`test('[AC-3] a completed item stays completed after a reload', async ({ page }) => { ... })`
(`async ({ request }) => ...` for a service; never `async (page) => ...`, which
Playwright refuses before running any test). A test that proves two:
`[AC-3][AC-4] ...`. A test with no criterion id in its title proves nothing the
harness can count."""


#: A Playwright failure raised by the spec's own code. Product code runs in the
#: page, where its errors surface through `page.evaluate` or as failed
#: expectations, so a bare TypeError or ReferenceError is the test's. One run's
#: locked suite called `addTask(page, ...)` on a helper declared
#: `addTask({ page }, ...)`: nine of eleven tests threw before touching the page.
#:
#: And Playwright's own refusals of the spec's shape, which no product can get
#: past: one run's locked suite left a test unclosed, so the next two were
#: written inside its body and the runner failed it with "did not expect
#: test() to be called here" - read as the product failing, round after round.
TEST_BUGS = (
    r"Playwright Test did not expect \S+ to be called here",
    r"First argument must use the object destructuring pattern",
    r"^(?!.*\bevaluate\b).*\b(?:TypeError|ReferenceError|SyntaxError)\b",
    r"^(?!.*\bevaluate\b).*Cannot read propert(?:y|ies) of (?:undefined|null)",
    r"^(?!.*\bevaluate\b).*\bis not a function\b",
    r"^(?!.*\bevaluate\b).*\bis not defined\b",
)
