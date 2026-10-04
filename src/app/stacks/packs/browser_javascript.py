"""A page that runs in a browser, in plain JavaScript modules with no build step."""

from __future__ import annotations

from app.stacks import StackPack
from app.stacks.packs import _javascript as js

#: The DOM the unit tests run in. 26 is the last release that supports the
#: Node the image and the CI file run (20); 27 and later need 22.
JSDOM = "26.1.0"

#: The unit runner, with a browser's globals installed in every test process
#: first (`test-setup.mjs`, which the harness keeps).
UNIT_SCRIPT = js.UNIT_SCRIPT.replace("node --test", "node --import ./test-setup.mjs --test")

#: A browser's globals for unit tests. Without it a test of anything that
#: touches the page had to build its own DOM, and four runs in a row spent
#: their first sprint on exactly that - a hand-written `setup.js` that left
#: `beforeEach` undefined, `HTMLButtonElement is not defined`, tests that
#: could not find the form - while every acceptance test passed. The React
#: pack's runner has always provided one; this gives the plain pack the same.
DOM_SETUP = """// Kept by the harness: a browser's globals - window, document, localStorage,
// HTMLElement, Event and the rest - installed before every unit test file, so a
// test can import a module that touches the page and call it. Each test file
// runs in its own process and gets a fresh, empty page; reset
// document.body.innerHTML in beforeEach to start each test clean.
import { JSDOM } from 'jsdom';

const dom = new JSDOM('<!DOCTYPE html><html><head></head><body></body></html>', {
  url: 'http://localhost/',
  pretendToBeVisual: true,
});
// Node has its own versions of these; a test hands them back to the page
// (dispatchEvent(new Event(...)), new FormData(form), { signal }), and the page
// accepts only its own. Node keeps the rest it has: timers, URL, crypto, console.
const thePageS = ['Event', 'EventTarget', 'CustomEvent', 'MessageEvent', 'DOMException',
  'AbortController', 'AbortSignal', 'Blob', 'File', 'FormData'];

globalThis.window = dom.window;
for (const name of Object.getOwnPropertyNames(dom.window)) {
  if (name in globalThis && !thePageS.includes(name)) continue;
  try {
    globalThis[name] = dom.window[name];
  } catch {
    // A property the window does not let go of; nothing needs it.
  }
}
"""

PACKAGE_JSON = """{
  "name": "{{project}}",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "start": "node scripts/serve.mjs",
    "test": "%(unit)s",
    "test:acceptance": "playwright test"
  },
  "devDependencies": {
    "@playwright/test": "%(playwright)s",
    "jsdom": "%(jsdom)s"
  }
}
""" % {"unit": UNIT_SCRIPT, "playwright": js.PLAYWRIGHT, "jsdom": JSDOM}

SERVE = """// Serves this project's files: for the acceptance tests, and for a person
// trying the product (`npm start`, then open the address it prints).
import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { extname, join, normalize, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(fileURLToPath(new URL('..', import.meta.url)));
const port = Number(process.argv[2] || process.env.PORT || 4173);
const types = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
  '.txt': 'text/plain; charset=utf-8',
};

createServer(async (request, response) => {
  const path = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
  let file = normalize(join(root, path));
  if (file !== root && !file.startsWith(root + sep)) {
    response.writeHead(403).end();
    return;
  }
  try {
    if ((await stat(file)).isDirectory()) file = join(file, 'index.html');
    const body = await readFile(file);
    response.writeHead(200, {
      'Content-Type': types[extname(file).toLowerCase()] || 'application/octet-stream',
      'Cache-Control': 'no-store',
    });
    response.end(body);
  } catch {
    response.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' }).end('Not found');
  }
}).listen(port, '127.0.0.1', () => {
  console.log(`Serving ${root} at http://127.0.0.1:${port}/`);
});
"""

INDEX = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{title}}</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <main id="app">
    <h1>{{title}}</h1>
  </main>
  <script type="module" src="src/main.js"></script>
</body>
</html>
"""

MAIN = """// The page's entry point: index.html loads this file as a module. Import the
// product's modules here and connect them to the page.

document.documentElement.dataset.ready = 'true';
"""

STYLES = """*, *::before, *::after { box-sizing: border-box; }

body {
  margin: 0;
  font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
  line-height: 1.5;
}

main {
  max-width: 48rem;
  margin: 0 auto;
  padding: 1rem;
}
"""

SMOKE_UNIT = """import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('the page loads its entry module', async () => {
  const page = await readFile(new URL('../index.html', import.meta.url), 'utf8');
  assert.match(page, /src="src\\/main\\.js"/);
});

test('a module that touches the page can be tested', async () => {
  await import('../src/main.js');
  assert.equal(document.documentElement.dataset.ready, 'true');
});
"""

SMOKE_ACCEPTANCE = """import { test, expect } from '@playwright/test';

test('the page opens and runs its script', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('data-ready', 'true');
  expect(errors).toEqual([]);
});
"""

GUIDE = js.UNIT_GUIDE + """
`index.html` loads `src/main.js` as a module; import the product's modules there.
Unit tests already run with a browser's globals - `document`, `window`,
`localStorage`, `HTMLElement`, `Event` - set up by `test-setup.mjs`, which the
harness keeps: a test may import a module that touches the page and call it.
Do not build a DOM of your own or install another; put the markup a test needs
into `document.body.innerHTML` in `beforeEach`. To run one file, run
`node --import ./test-setup.mjs --test tests/<module>.test.js` in the project
directory: a bare `node --test` skips the setup, and every test that touches the
page fails with `document is not defined`. What a user does across the whole
page is the acceptance suite's to prove."""

ACCEPTANCE_GUIDE = """Acceptance tests go in `acceptance/`, named `<feature>.spec.js`, using
`@playwright/test` (`import { test, expect } from '@playwright/test'`). The
configuration starts the product's own server; open the page with
`await page.goto('/')` - never a `file://` address, a host or a port.
""" + js.FIND_CONTROLS + """ Act the way a user does: `fill`,
`click`, `press('Enter')`, `check`, `selectOption`. Every test starts in a fresh
browser, so nothing one test stores is seen by another. To prove something
persists, change it, `await page.reload()`, and check it is still there. To
check a small screen, `await page.setViewportSize({ width: 375, height: 667 })`
and assert what must still be usable.
""" + js.NAMING

PACK = StackPack(
    name="browser-javascript",
    title="Browser app in plain JavaScript modules",
    kind="browser_app",
    language="javascript",
    frameworks=("vanilla", "html", "css", "dom", "browser", "es modules", "javascript"),
    files={
        "package.json": PACKAGE_JSON,
        "playwright.config.js": js.playwright_config("node scripts/serve.mjs", "/", screenshot="on", checks_the_page=True),
        "playwright.setup.mjs": js.page_check("/"),
        "test-setup.mjs": DOM_SETUP,
        "scripts/serve.mjs": SERVE,
        "index.html": INDEX,
        "src/main.js": MAIN,
        "styles.css": STYLES,
        ".gitignore": js.GITIGNORE,
    },
    install=js.INSTALL,
    unit_test=js.UNIT_TEST,
    acceptance_test=js.ACCEPTANCE_TEST,
    unit_report="test-results/unit.xml",
    acceptance_report="test-results/acceptance.xml",
    unit_dir="tests",
    acceptance_dir="acceptance",
    acceptance_pattern="*.spec.js",
    unit_pattern="*.test.js",
    kept_files=("playwright.config.js", "playwright.setup.mjs", "test-setup.mjs", "scripts/serve.mjs"),
    unit_dom="`test-setup.mjs`",
    kept_scripts={"start": "node scripts/serve.mjs", "test": UNIT_SCRIPT, "test:acceptance": "playwright test"},
    smoke_files={
        "tests/scaffold-smoke.test.js": SMOKE_UNIT,
        "acceptance/scaffold-smoke.spec.js": SMOKE_ACCEPTANCE,
    },
    guide=GUIDE,
    acceptance_guide=ACCEPTANCE_GUIDE,
    stack={
        "language": "JavaScript",
        "framework": "None (plain HTML, CSS and JavaScript modules)",
        "frontend_framework": "None (plain HTML, CSS and JavaScript modules)",
        "testing_framework": "node:test for unit tests, Playwright for acceptance tests",
    },
    check_families=frozenset({"javascript", "browser"}),
    evidence_dir="test-results/evidence",
    test_bugs=js.TEST_BUGS,
    runtime_report=js.PAGE_LOAD_REPORT,
    locators_nobody_sees=js.LOCATORS_NOBODY_SEES,
    failure_pages=js.failure_pages,
    near_misses=js.near_misses,
    assertion_names=js.playwright_assertions,
    code_runs_in="browser",
    ci_setup=js.CI_SETUP,
    ci_prepare=js.CI_BROWSERS,
)
