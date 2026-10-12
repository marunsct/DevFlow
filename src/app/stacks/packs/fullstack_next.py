"""A browser interface and its own HTTP service in one Next.js application, in TypeScript."""

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
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "test": "%(unit)s",
    "test:acceptance": "playwright test"
  },
  "dependencies": {
    "next": "^15.5.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  },
  "devDependencies": {
    "@playwright/test": "%(playwright)s",
    "@testing-library/dom": "^10.4.0",
    "@testing-library/react": "^16.1.0",
    "@types/node": "^22.0.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^5.0.0",
    "axe-core": "%(axe)s",
    "jsdom": "^26.0.0",
    "typescript": "^5.6.0",
    "vitest": "^3.2.0"
  }
}
""" % {"unit": UNIT_SCRIPT, "playwright": js.PLAYWRIGHT, "axe": js.AXE_CORE}

NEXT_CONFIG = """/** @type {import('next').NextConfig} */
const nextConfig = {};

export default nextConfig;
"""

TSCONFIG = """{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
"""

NEXT_ENV = """/// <reference types="next" />
/// <reference types="next/image-types/global" />
"""

VITEST_CONFIG = """import { defineConfig } from 'vitest/config';
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

LAYOUT = """import type { ReactNode } from 'react';
import './globals.css';

export const metadata = { title: '{{title}}' };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
"""

PAGE = """export default function Home() {
  return (
    <main>
      <h1>{{title}}</h1>
    </main>
  );
}
"""

HEALTH = """// The service's health, as every pack's service reports it.
export function GET() {
  return Response.json({ status: 'ok' });
}
"""

SMOKE_UNIT = """import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import Home from '../app/page';

describe('the home page', () => {
  it('renders its heading', () => {
    render(<Home />);
    expect(screen.getByRole('heading', { level: 1 })).toBeTruthy();
  });
});
"""

SMOKE_ACCEPTANCE = """import { test, expect } from '@playwright/test';

test('the page opens and the service answers', async ({ page, request }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  expect(errors).toEqual([]);
  expect((await request.get('/api/health')).ok()).toBeTruthy();
});
"""

GUIDE = """The product is one Next.js application in TypeScript, on the App Router: pages and
layouts in `app/` (`app/page.tsx` is the home page, `app/layout.tsx` wraps every page;
mark a component that uses state or events with `'use client'`), and the HTTP service
as route handlers under `app/api/` (`app/api/<name>/route.ts` exporting `GET`,
`POST` ...). Unit tests go in `tests/`, named `<Name>.test.tsx` (or `.test.ts`), using
Vitest and Testing Library in a simulated DOM. Run them with `npm test`. Data the
service keeps lives under the directory in `DATA_DIR` (default `data/`); a product
meant for a database server reads its address from `DATABASE_URL` and, when that is
unset, keeps a file database under `DATA_DIR`, which is what every test runs on. Never
start a server yourself: the acceptance suite's configuration builds and starts it."""

ACCEPTANCE_GUIDE = """Acceptance tests go in `acceptance/`, named `<feature>.spec.js`, using
`@playwright/test` (`import { test, expect } from '@playwright/test'`). The
configuration builds the application and starts it with an empty `DATA_DIR`; open the
page with `await page.goto('/')` - never a `file://` address, a host or a port.
""" + js.FIND_CONTROLS + """ Act the way a user does: `fill`,
`click`, `press('Enter')`, `check`, `selectOption`. Test the service's interface with
the `request` fixture (`await request.post('/api/...', { data })`), checking
`response.status()` and `await response.json()`. To prove something persists, change
it, `await page.reload()`, and check it is still there. Tests run one after another
against the same service, so a test must create what it reads and look for its own
records rather than counting all of them.
""" + js.NAMING

START = "node_modules/.bin/next build && exec node_modules/.bin/next start -H 127.0.0.1 -p $PORT"

DOCKERFILE = """# {{title}}: build with `docker build -t {{project}} .`, run with
# `docker run -p 3000:3000 -v {{project}}-data:/app/data {{project}}`.
FROM node:%(node)s-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npx next build

FROM node:%(node)s-slim
ENV NODE_ENV=production HOST=0.0.0.0 PORT=3000 DATA_DIR=/app/data NEXT_TELEMETRY_DISABLED=1
WORKDIR /app
COPY --from=build /app ./
RUN npm prune --omit=dev && mkdir -p /app/data && chown -R node:node /app/data
USER node
EXPOSE 3000
CMD ["sh", "-c", "exec npx next start -H \\"$HOST\\" -p \\"$PORT\\""]
""" % {"node": js.NODE_MAJOR}

PACK = StackPack(
    name="fullstack-next",
    title="Browser app with its own HTTP service in Next.js (React and TypeScript)",
    kind="fullstack",
    language="typescript",
    frameworks=("next", "next.js", "nextjs"),
    frontend_frameworks=("react",),
    files={
        "package.json": PACKAGE_JSON,
        "next.config.mjs": NEXT_CONFIG,
        "tsconfig.json": TSCONFIG,
        "next-env.d.ts": NEXT_ENV,
        "vitest.config.ts": VITEST_CONFIG,
        "playwright.config.js": js.playwright_config(
            START, "/api/health", screenshot="on", checks_the_page=True, server_timeout_ms=300_000,
        ),
        "playwright.setup.mjs": js.page_check("/"),
        "app/layout.tsx": LAYOUT,
        "app/page.tsx": PAGE,
        "app/globals.css": react.STYLES,
        "app/api/health/route.ts": HEALTH,
        ".gitignore": js.GITIGNORE + ".next/\nnext-env.d.ts\n*.tsbuildinfo\n",
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
    kept_files=("playwright.config.js", "playwright.setup.mjs", "vitest.config.ts"),
    unit_dom="Vitest's `jsdom` environment in `vitest.config.ts`",
    kept_scripts={"test": UNIT_SCRIPT, "test:acceptance": "playwright test"},
    smoke_files={
        "tests/scaffold-smoke.test.tsx": SMOKE_UNIT,
        "acceptance/scaffold-smoke.spec.js": SMOKE_ACCEPTANCE,
    },
    guide=GUIDE,
    acceptance_guide=ACCEPTANCE_GUIDE,
    stack={
        "language": "TypeScript",
        "framework": "Next.js",
        "frontend_framework": "React (Next.js App Router)",
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
    code_runs_in="both",
    ci_setup=js.CI_SETUP,
    ci_prepare=js.CI_BROWSERS,
    release_files={"Dockerfile": DOCKERFILE, ".dockerignore": js.DOCKERIGNORE + ".next/\n"},
)
