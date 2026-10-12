"""A page that runs in a browser, built with Svelte and TypeScript on Vite."""

from __future__ import annotations

from app.stacks import StackPack
from app.stacks.packs import _javascript as js
from app.stacks.packs import browser_react as react

UNIT_SCRIPT = react.UNIT_SCRIPT

PACKAGE_JSON = """{
  "name": "{{project}}",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "start": "vite --host 127.0.0.1",
    "build": "vite build",
    "check": "svelte-check --tsconfig ./tsconfig.json",
    "test": "%(unit)s",
    "test:acceptance": "playwright test"
  },
  "devDependencies": {
    "@playwright/test": "%(playwright)s",
    "@sveltejs/vite-plugin-svelte": "^6.0.0",
    "@testing-library/svelte": "^5.2.0",
    "axe-core": "%(axe)s",
    "jsdom": "^26.0.0",
    "svelte": "^5.0.0",
    "svelte-check": "^4.0.0",
    "typescript": "^5.6.0",
    "vite": "^7.0.0",
    "vitest": "^3.2.0"
  }
}
""" % {"unit": UNIT_SCRIPT, "playwright": js.PLAYWRIGHT, "axe": js.AXE_CORE}

VITE_CONFIG = """import { defineConfig } from 'vitest/config';
import { svelte } from '@sveltejs/vite-plugin-svelte';

// The harness runs the unit tests through this file; keep the `test` block.
export default defineConfig({
  plugins: [svelte()],
  // Svelte resolves its browser build for tests in a simulated DOM.
  resolve: process.env.VITEST ? { conditions: ['browser'] } : undefined,
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.test.ts'],
  },
});
"""

SVELTE_CONFIG = """import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

// TypeScript in `<script lang="ts">` blocks.
export default { preprocess: vitePreprocess() };
"""

TSCONFIG = """{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "skipLibCheck": true,
    "noEmit": true,
    "isolatedModules": true,
    "verbatimModuleSyntax": true,
    "types": ["svelte", "vite/client"]
  },
  "include": ["src", "tests"]
}
"""

INDEX = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{title}}</title>
</head>
<body>
  <div id="app"></div>
  <script type="module" src="/src/main.ts"></script>
</body>
</html>
"""

MAIN = """import { mount } from 'svelte';
import App from './App.svelte';
import './styles.css';

mount(App, { target: document.getElementById('app')! });
"""

APP = """<script lang="ts">
</script>

<main>
  <h1>{{title}}</h1>
</main>
"""

SMOKE_UNIT = """import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import App from '../src/App.svelte';

describe('App', () => {
  it('renders its heading', () => {
    render(App);
    expect(screen.getByRole('heading', { level: 1 })).toBeTruthy();
  });
});
"""

GUIDE = """Components live in `src/` as Svelte 5 components written with `<script lang="ts">`
(`src/App.svelte` is the root, `src/main.ts` mounts it); state uses runes (`$state`,
`$derived`). Unit tests go in `tests/`, named `<Name>.test.ts`, using Vitest (`import {
describe, it, expect } from 'vitest'`) and Testing Library (`render`, `screen`) in a
simulated DOM. Run them with `npm test`; check types with `npm run check`. Install a
dependency with `npm install <name>` (`--save-dev` for one only tests use). Never start
a server yourself."""

PACK = StackPack(
    name="browser-svelte",
    title="Browser app in Svelte and TypeScript on Vite",
    kind="browser_app",
    language="typescript",
    frameworks=("svelte",),
    frontend_frameworks=("svelte",),
    files={
        "package.json": PACKAGE_JSON,
        "vite.config.ts": VITE_CONFIG,
        "svelte.config.js": SVELTE_CONFIG,
        "tsconfig.json": TSCONFIG,
        "playwright.config.js": js.playwright_config(
            "node_modules/.bin/vite --host 127.0.0.1 --port ${port} --strictPort", "/", screenshot="on",
            checks_the_page=True,
        ),
        "playwright.setup.mjs": js.page_check("/"),
        "index.html": INDEX,
        "src/main.ts": MAIN,
        "src/App.svelte": APP,
        "src/styles.css": react.STYLES,
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
        "acceptance/scaffold-smoke.spec.js": react.SMOKE_ACCEPTANCE,
    },
    guide=GUIDE,
    acceptance_guide=react.ACCEPTANCE_GUIDE,
    stack={
        "language": "TypeScript",
        "framework": "Svelte",
        "frontend_framework": "Svelte on Vite",
        "testing_framework": "Vitest with Testing Library for unit tests, Playwright for acceptance tests",
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
