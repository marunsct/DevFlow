"""A page that runs in a browser, built with React and TypeScript on Vite."""

from __future__ import annotations

from app.stacks import StackPack
from app.stacks.packs import _javascript as js

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
    "build": "tsc --noEmit && vite build",
    "test": "%(unit)s",
    "test:acceptance": "playwright test"
  },
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  },
  "devDependencies": {
    "@playwright/test": "%(playwright)s",
    "@testing-library/dom": "^10.4.0",
    "axe-core": "%(axe)s",
    "@testing-library/react": "^16.1.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^5.0.0",
    "jsdom": "^26.0.0",
    "typescript": "^5.6.0",
    "vite": "^7.0.0",
    "vitest": "^3.2.0"
  }
}
""" % {"unit": UNIT_SCRIPT, "playwright": js.PLAYWRIGHT, "axe": js.AXE_CORE}

VITE_CONFIG = """import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The harness runs the unit tests through this file; keep the `test` block.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.test.{ts,tsx}'],
  },
});
"""

TSCONFIG = """{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "jsx": "react-jsx",
    "strict": true,
    "skipLibCheck": true,
    "noEmit": true,
    "isolatedModules": true,
    "types": ["vite/client"]
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
  <div id="root"></div>
  <script type="module" src="/src/main.tsx"></script>
</body>
</html>
"""

MAIN = """import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import './styles.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
"""

APP = """export function App() {
  return (
    <main>
      <h1>{{title}}</h1>
    </main>
  );
}
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

SMOKE_UNIT = """import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { App } from '../src/App';

describe('App', () => {
  it('renders its heading', () => {
    render(<App />);
    expect(screen.getByRole('heading', { level: 1 })).toBeTruthy();
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

GUIDE = """Components and modules live in `src/` (`src/App.tsx` is the root component,
`src/main.tsx` mounts it). Unit tests go in `tests/`, named `<Name>.test.tsx` (or
`.test.ts` for code with no JSX), using Vitest (`import { describe, it, expect }
from 'vitest'`) and Testing Library (`render`, `screen`) in a simulated DOM. Run
them with `npm test`; check types with `npx tsc --noEmit`. Install a dependency
with `npm install <name>` (`--save-dev` for one only tests use). Never start a
server yourself."""

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
    name="browser-react",
    title="Browser app in React and TypeScript on Vite",
    kind="browser_app",
    language="typescript",
    frameworks=("react", "vite"),
    frontend_frameworks=("react",),
    files={
        "package.json": PACKAGE_JSON,
        "vite.config.ts": VITE_CONFIG,
        "tsconfig.json": TSCONFIG,
        "playwright.config.js": js.playwright_config(
            "node_modules/.bin/vite --host 127.0.0.1 --port ${port} --strictPort", "/", screenshot="on",
            checks_the_page=True,
        ),
        "playwright.setup.mjs": js.page_check("/"),
        "index.html": INDEX,
        "src/main.tsx": MAIN,
        "src/App.tsx": APP,
        "src/styles.css": STYLES,
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
    unit_pattern="*.test.tsx",
    kept_files=("playwright.config.js", "playwright.setup.mjs", "vite.config.ts"),
    unit_dom="Vitest's `jsdom` environment in `vite.config.ts`",
    kept_scripts={"test": UNIT_SCRIPT, "test:acceptance": "playwright test"},
    smoke_files={
        "tests/scaffold-smoke.test.tsx": SMOKE_UNIT,
        "acceptance/scaffold-smoke.spec.js": SMOKE_ACCEPTANCE,
    },
    guide=GUIDE,
    acceptance_guide=ACCEPTANCE_GUIDE,
    stack={
        "language": "TypeScript",
        "framework": "React",
        "frontend_framework": "React on Vite",
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
