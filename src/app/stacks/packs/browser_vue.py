"""A page that runs in a browser, built with Vue and TypeScript on Vite."""

from __future__ import annotations

from app.stacks import StackPack
from app.stacks.packs import _javascript as js
from app.stacks.packs._fullstack import VUE

UNIT_SCRIPT = (
    "vitest run --reporter=default --reporter=junit --outputFile.junit=test-results/unit.xml"
)

PACKAGE_JSON = """{
  "name": "{{project}}",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "start": "vite --host 127.0.0.1",
    "build": "vue-tsc --noEmit && vite build",
    "test": "%(unit)s",
    "test:acceptance": "playwright test"
  },
  "dependencies": {
    "vue": "^3.5.0"
  },
  "devDependencies": {
    "@playwright/test": "%(playwright)s",
    "@vitejs/plugin-vue": "^6.0.0",
    "@vue/test-utils": "^2.4.6",
    "axe-core": "%(axe)s",
    "jsdom": "^26.0.0",
    "typescript": "^5.6.0",
    "vite": "^7.0.0",
    "vitest": "^3.2.0",
    "vue-tsc": "^3.0.0"
  }
}
""" % {"unit": UNIT_SCRIPT, "playwright": js.PLAYWRIGHT, "axe": js.AXE_CORE}

VITE_CONFIG = """import { defineConfig } from 'vitest/config';
import vue from '@vitejs/plugin-vue';

// The harness runs the unit tests through this file; keep the `test` block.
export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.test.ts'],
  },
});
"""

TSCONFIG = VUE.files["tsconfig.json"].replace('"include": ["src", "tests/client"]', '"include": ["src", "tests"]')

SMOKE_UNIT = """import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import App from '../src/App.vue';

describe('App', () => {
  it('renders its heading', () => {
    const wrapper = mount(App);
    expect(wrapper.find('h1').exists()).toBe(true);
  });
});
"""

SMOKE_ACCEPTANCE = """import { test, expect } from '@playwright/test';

test('the page opens and renders', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  expect(errors).toEqual([]);
});
"""

GUIDE = """Components live in `src/` as Vue single-file components written with `<script setup
lang="ts">` (`src/App.vue` is the root, `src/main.ts` mounts it). Unit tests go in
`tests/`, named `<Name>.test.ts`, using Vitest (`import { describe, it, expect } from
'vitest'`) and Vue Test Utils (`mount`) in a simulated DOM. Run them with `npm test`;
check types with `npx vue-tsc --noEmit`. Install a dependency with `npm install <name>`
(`--save-dev` for one only tests use). Never start a server yourself."""

ACCEPTANCE_GUIDE = """Acceptance tests go in `acceptance/`, named `<feature>.spec.js`, using
`@playwright/test` (`import { test, expect } from '@playwright/test'`). The
configuration starts the product's development server; open the page with
`await page.goto('/')` - never a `file://` address, a host or a port.
""" + js.FIND_CONTROLS + """ Act the way a user does: `fill`,
`click`, `press('Enter')`, `check`, `selectOption`. Every test starts in a fresh
browser, so nothing one test stores is seen by another. To prove something
persists, change it, `await page.reload()`, and check it is still there. To check
a small screen, `await page.setViewportSize({ width: 375, height: 667 })`.
""" + js.NAMING

PACK = StackPack(
    name="browser-vue",
    title="Browser app in Vue and TypeScript on Vite",
    kind="browser_app",
    language="typescript",
    frameworks=("vue", "vue.js", "vuejs"),
    frontend_frameworks=("vue", "vue.js", "vuejs"),
    files={
        "package.json": PACKAGE_JSON,
        "vite.config.ts": VITE_CONFIG,
        "tsconfig.json": TSCONFIG,
        "playwright.config.js": js.playwright_config(
            "node_modules/.bin/vite --host 127.0.0.1 --port ${port} --strictPort", "/", screenshot="on",
            checks_the_page=True,
        ),
        "playwright.setup.mjs": js.page_check("/"),
        "index.html": VUE.files["index.html"],
        "src/env.d.ts": VUE.files["src/env.d.ts"],
        "src/main.ts": VUE.files["src/main.ts"],
        "src/App.vue": VUE.files["src/App.vue"],
        "src/styles.css": VUE.files["src/styles.css"],
        ".gitignore": js.GITIGNORE + "dist/\n",
    },
    install=js.INSTALL,
    unit_test=js.UNIT_TEST,
    acceptance_test=js.ACCEPTANCE_TEST,
    unit_report="test-results/unit.xml",
    acceptance_report="test-results/acceptance.xml",
    unit_dir="tests",
    acceptance_dir="acceptance",
    acceptance_pattern="*.spec.js",
    unit_pattern="*.test.ts",
    kept_files=("playwright.config.js", "playwright.setup.mjs", "vite.config.ts"),
    unit_dom="Vitest's `jsdom` environment in `vite.config.ts`",
    kept_scripts={"test": UNIT_SCRIPT, "test:acceptance": "playwright test"},
    smoke_files={
        "tests/scaffold-smoke.test.ts": SMOKE_UNIT,
        "acceptance/scaffold-smoke.spec.js": SMOKE_ACCEPTANCE,
    },
    guide=GUIDE,
    acceptance_guide=ACCEPTANCE_GUIDE,
    stack={
        "language": "TypeScript",
        "framework": "Vue",
        "frontend_framework": "Vue on Vite",
        "testing_framework": "Vitest with Vue Test Utils for unit tests, Playwright for acceptance tests",
    },
    check_families=frozenset({"javascript", "browser", "typescript"}),
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
    storage_before_page_open=js.storage_before_page_open,
    module_system_mismatch=js.module_system_mismatch,
    unawaited_helpers=js.unawaited_helpers,
    locators_with_an_ignored_option=js.locators_with_a_name_option,
    expects_what_it_never_gave=js.expects_what_it_never_gave,
    positions_it_asserts=js.positions_it_asserts,
    filtered_by_a_field_value=js.a_locator_filtered_by_a_field_value,
    failure_pages=js.failure_pages,
    near_misses=js.near_misses,
    needs_what_it_never_made=js.needs_what_it_never_made,
    assertion_names=js.playwright_assertions,
    code_runs_in="browser",
    ci_setup=js.CI_SETUP,
    ci_prepare=js.CI_BROWSERS,
)
