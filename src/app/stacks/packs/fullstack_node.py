"""A browser interface served by its own HTTP service, both in JavaScript on Express."""

from __future__ import annotations

from app.stacks import StackPack
from app.stacks.packs import _javascript as js
from app.stacks.packs import node_http_api as api

APP = """import express from 'express';
import { fileURLToPath } from 'node:url';

const publicDir = fileURLToPath(new URL('../public', import.meta.url));

// Builds the service: the JSON interface under /api, and the page from public/.
// `src/index.js` starts it; unit tests call it directly.
export function createApp() {
  const app = express();
  app.use(express.json());

  app.get('/api/health', (request, response) => {
    response.json({ status: 'ok' });
  });

  app.use(express.static(publicDir));
  return app;
}
"""

PAGE = """<!DOCTYPE html>
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
  <script type="module" src="main.js"></script>
</body>
</html>
"""

PAGE_MAIN = """// The page's entry point: index.html loads this file as a module. Import the
// page's modules here and connect them to the page; reach the service with
// fetch('/api/...').

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

SMOKE_UNIT = api.SMOKE_UNIT.replace("/health", "/api/health")

SMOKE_ACCEPTANCE = """import { test, expect } from '@playwright/test';

test('the page opens and the service answers', async ({ page, request }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('data-ready', 'true');
  expect(errors).toEqual([]);
  expect((await request.get('/api/health')).ok()).toBeTruthy();
});
"""

GUIDE = js.UNIT_GUIDE + """
The service is built by `createApp()` in `src/app.js`: the JSON interface under
`/api/`, and the page from `public/` (`public/index.html` loads `public/main.js`
as a module). The page reaches the service with `fetch('/api/...')`. Data the
service stores lives under the directory in `DATA_DIR` (default `data/`). Unit
tests cover the service's modules and the page's modules that do not touch the
page; the page itself is covered by the acceptance suite."""

ACCEPTANCE_GUIDE = """Acceptance tests go in `acceptance/`, named `<feature>.spec.js`, using
`@playwright/test`. The configuration starts the product's own service with an
empty `DATA_DIR`. Test what a user does through the page with the `page` fixture,
from `await page.goto('/')`. """ + js.FIND_CONTROLS + """ Act with `fill`,
`click` and `press('Enter')`. Test the service's interface with the `request`
fixture (`await request.post('/api/...', { data })`). To prove something
persists, change it, `await page.reload()`, and check it is still there. Tests run
one after another against the same service, so a test must create what it reads.
""" + js.NAMING

PACK = StackPack(
    name="fullstack-node",
    title="Browser app with its own HTTP service, in JavaScript on Express",
    kind="fullstack",
    language="javascript",
    frameworks=("express", "node", "node.js", "html", "vanilla", "javascript"),
    files={
        # The service's manifest, with the page probe's accessibility engine:
        # this product has a page, the service alone does not.
        "package.json": api.PACKAGE_JSON.replace(
            '"@playwright/test": "%s"' % js.PLAYWRIGHT,
            '"@playwright/test": "%s",\n    "axe-core": "%s"' % (js.PLAYWRIGHT, js.AXE_CORE),
        ),
        "playwright.config.js": js.playwright_config(
            "node src/index.js", "/api/health", screenshot="on", checks_the_page=True
        ),
        "playwright.setup.mjs": js.page_check("/"),
        "src/app.js": APP,
        "src/index.js": api.INDEX,
        "public/index.html": PAGE,
        "public/main.js": PAGE_MAIN,
        "public/styles.css": STYLES,
        "start.sh": api.START,
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
    kept_files=("playwright.config.js", "playwright.setup.mjs"),
    kept_scripts=api.PACK.kept_scripts,
    smoke_files={
        "tests/scaffold-smoke.test.js": SMOKE_UNIT,
        "acceptance/scaffold-smoke.spec.js": SMOKE_ACCEPTANCE,
    },
    guide=GUIDE,
    acceptance_guide=ACCEPTANCE_GUIDE,
    stack={
        "language": "JavaScript",
        "framework": "Express",
        "frontend_framework": "None (plain HTML, CSS and JavaScript modules)",
        "testing_framework": "node:test for unit tests, Playwright for acceptance tests",
    },
    check_families=frozenset({"javascript", "browser"}),
    evidence_dir="test-results/evidence",
    test_bugs=js.TEST_BUGS,
    runtime_report=js.PAGE_LOAD_REPORT,
    locators_nobody_sees=js.LOCATORS_NOBODY_SEES,
    locators_that_do_not_exist=js.LOCATORS_THAT_DO_NOT_EXIST,
    locators_that_pick_one=js.LOCATORS_THAT_PICK_ONE,
    locators_by_a_missing_name=js.LOCATORS_BY_A_NAME_THE_ROLE_NEVER_HAS,
    finds_by_name=js.FINDS_BY_NAME,
    contradicting_locators=js.asserted_without_the_text_it_is_found_by,
    locator_left_behind=js.a_locator_left_behind,
    opens_no_page=js.tests_that_never_open_the_page,
    expects_what_it_never_gave=js.expects_what_it_never_gave,
    positions_it_asserts=js.positions_it_asserts,
    filtered_by_a_field_value=js.a_locator_filtered_by_a_field_value,
    failure_pages=js.failure_pages,
    near_misses=js.near_misses,
    needs_what_it_never_made=js.needs_what_it_never_made,
    assertion_names=js.playwright_assertions,
    code_runs_in="both",
    ci_setup=js.CI_SETUP,
    ci_prepare=js.CI_BROWSERS,
    release_files=api.PACK.release_files,
)
