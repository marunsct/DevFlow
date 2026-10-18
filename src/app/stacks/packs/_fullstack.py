"""Browser interfaces built with a component framework, served by the product's own HTTP service.

One shape for every pair: the interface is built with Vite into `dist/`, and
the service serves it beside its JSON interface under `/api/` - so the product
runs as one process on one port, the way it is deployed, and the acceptance
suite drives it there with Playwright, through the page and through `/api/`.
`scripts/serve-acceptance.mjs` builds the interface and starts the service for
the suite; unit tests cover the interface's code in a simulated DOM and the
service's code on its own runtime, and report together.

A pair is a frontend (React or Vue, in TypeScript) and a service (Express in
JavaScript, or FastAPI in Python); `fullstack_pack` composes one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.stacks import StackPack
from app.stacks.packs import _javascript as js
from app.stacks.packs import _python


@dataclass(frozen=True)
class Frontend:
    """What one component framework adds to a project, in TypeScript on Vite."""

    name: str
    #: Words in a stack's frontend framework that name this one.
    words: tuple[str, ...]
    label: str
    dependencies: dict[str, str]
    dev_dependencies: dict[str, str]
    vite_plugin_import: str
    vite_plugin_call: str
    files: dict[str, str]
    #: Unit test file pattern under `tests/client/`.
    unit_glob: str
    smoke_unit: tuple[str, str]
    guide: str
    #: The page's root component the scaffold writes as a stub (`StackPack.entrypoints`).
    entry: str = ""


@dataclass(frozen=True)
class Service:
    """What one HTTP framework adds: where the service lives and how it starts."""

    name: str
    words: tuple[str, ...]
    label: str
    language: str
    files: dict[str, str]
    #: The command `serve-acceptance.mjs` starts once the interface is built:
    #: argv as a JavaScript array literal, `PORT` and `DATA_DIR` set.
    start_argv: str
    install: tuple[tuple[str, ...], ...]
    unit_script: str
    kept: tuple[str, ...]
    smoke_unit: tuple[str, str]
    guide: str
    testing: str
    ci_setup: tuple[str, ...] = ()
    release_files: dict[str, str] = field(default_factory=dict)
    dependencies: dict[str, str] = field(default_factory=dict)
    dev_dependencies: dict[str, str] = field(default_factory=dict)
    check_families: frozenset[str] = frozenset()
    #: The service's app module the scaffold writes as a stub (`StackPack.entrypoints`).
    entry: str = ""


# --- the page -------------------------------------------------------------------

INDEX = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{title}}</title>
</head>
<body>
  <div id="%(root)s"></div>
  <script type="module" src="/src/%(main)s"></script>
</body>
</html>
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

TSCONFIG = """{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "Bundler",%(jsx)s
    "strict": true,
    "skipLibCheck": true,
    "noEmit": true,
    "isolatedModules": true,
    "allowJs": true,
    "types": ["vite/client"]
  },
  "include": ["src", "tests/client"]
}
"""

REACT = Frontend(
    entry="src/App.tsx",
    name="react",
    words=("react",),
    label="React",
    dependencies={"react": "^19.0.0", "react-dom": "^19.0.0"},
    dev_dependencies={
        "@testing-library/dom": "^10.4.0",
        "@testing-library/react": "^16.1.0",
        "@types/react": "^19.0.0",
        "@types/react-dom": "^19.0.0",
        "@vitejs/plugin-react": "^5.0.0",
    },
    vite_plugin_import="import react from '@vitejs/plugin-react';",
    vite_plugin_call="react()",
    files={
        "index.html": INDEX % {"root": "root", "main": "main.tsx"},
        "tsconfig.json": TSCONFIG % {"jsx": '\n    "jsx": "react-jsx",'},
        "src/main.tsx": """import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import './styles.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
""",
        "src/App.tsx": """export function App() {
  return (
    <main>
      <h1>{{title}}</h1>
    </main>
  );
}
""",
        "src/styles.css": STYLES,
    },
    unit_glob="*.test.tsx",
    smoke_unit=("tests/client/scaffold-smoke.test.tsx", """import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { App } from '../../src/App';

describe('App', () => {
  it('renders its heading', () => {
    render(<App />);
    expect(screen.getByRole('heading', { level: 1 })).toBeTruthy();
  });
});
"""),
    guide="""The interface is React in TypeScript: components in `src/` (`src/App.tsx` is the root,
`src/main.tsx` mounts it). Its unit tests go in `tests/client/`, named
`<Name>.test.tsx`, using Vitest (`import { describe, it, expect } from 'vitest'`) and
Testing Library (`render`, `screen`) in a simulated DOM.""",
)

VUE = Frontend(
    entry="src/App.vue",
    name="vue",
    words=("vue", "vue.js", "vuejs"),
    label="Vue",
    dependencies={"vue": "^3.5.0"},
    dev_dependencies={
        "@vitejs/plugin-vue": "^6.0.0",
        "@vue/test-utils": "^2.4.6",
        "vue-tsc": "^3.0.0",
    },
    vite_plugin_import="import vue from '@vitejs/plugin-vue';",
    vite_plugin_call="vue()",
    files={
        "index.html": INDEX % {"root": "app", "main": "main.ts"},
        "tsconfig.json": TSCONFIG % {"jsx": '\n    "jsx": "preserve",'},
        "src/env.d.ts": """/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue';
  const component: DefineComponent<object, object, unknown>;
  export default component;
}
""",
        "src/main.ts": """import { createApp } from 'vue';
import App from './App.vue';
import './styles.css';

createApp(App).mount('#app');
""",
        "src/App.vue": """<script setup lang="ts">
</script>

<template>
  <main>
    <h1>{{title}}</h1>
  </main>
</template>
""",
        "src/styles.css": STYLES,
    },
    unit_glob="*.test.ts",
    smoke_unit=("tests/client/scaffold-smoke.test.ts", """import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import App from '../../src/App.vue';

describe('App', () => {
  it('renders its heading', () => {
    const wrapper = mount(App);
    expect(wrapper.find('h1').exists()).toBe(true);
  });
});
"""),
    guide="""The interface is Vue 3 in TypeScript: single-file components in `src/` (`src/App.vue` is
the root, `src/main.ts` mounts it), written with `<script setup lang="ts">`. Its unit
tests go in `tests/client/`, named `<Name>.test.ts`, using Vitest (`import { describe,
it, expect } from 'vitest'`) and Vue Test Utils (`mount`) in a simulated DOM.""",
)


# --- the services ---------------------------------------------------------------

EXPRESS_APP = """import express from 'express';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const page = fileURLToPath(new URL('../dist', import.meta.url));

// Builds the service: the JSON interface under /api, and the built page from
// dist/ (`npm run build`). `server/index.js` starts it; unit tests call it directly.
export function createApp() {
  const app = express();
  app.use(express.json());

  app.get('/api/health', (request, response) => {
    response.json({ status: 'ok' });
  });

  if (existsSync(page)) {
    app.use(express.static(page));
    // Any other address that is not the API is the page: it routes on the client.
    app.use((request, response, next) => {
      if (request.method !== 'GET' || request.path.startsWith('/api/')) return next();
      response.sendFile('index.html', { root: page });
    });
  }
  return app;
}
"""

EXPRESS_INDEX = """import { createApp } from './app.js';

const port = Number(process.env.PORT || 3000);
const host = process.env.HOST || '127.0.0.1';

createApp().listen(port, host, () => {
  console.log(`Listening on http://${host}:${port}`);
});
"""

EXPRESS = Service(
    entry="server/app.js",
    name="express",
    words=("express",),
    label="Express",
    language="javascript",
    files={"server/app.js": EXPRESS_APP, "server/index.js": EXPRESS_INDEX},
    start_argv="['node', 'server/index.js']",
    install=js.INSTALL,
    unit_script=(
        "vitest run --reporter=default --reporter=junit --outputFile.junit=test-results/unit.xml"
    ),
    kept=(),
    smoke_unit=("tests/server/scaffold-smoke.test.js", """import { describe, expect, it } from 'vitest';
import { createApp } from '../../server/app.js';

describe('the service', () => {
  it('reports its health', async () => {
    const server = createApp().listen(0, '127.0.0.1');
    await new Promise((resolve) => server.once('listening', resolve));
    try {
      const { port } = server.address();
      const response = await fetch(`http://127.0.0.1:${port}/api/health`);
      expect(await response.json()).toEqual({ status: 'ok' });
    } finally {
      server.close();
    }
  });
});
"""),
    guide="""The service is Express in JavaScript: `createApp()` in `server/app.js` builds it - the
JSON interface under `/api/`, and the built page from `dist/` - and `server/index.js`
starts it on the port in `PORT`. Its unit tests go in `tests/server/`, named
`<module>.test.js`, using Vitest: start `createApp()` on port 0 and call it with `fetch`.""",
    testing="Vitest for unit tests of the page and the service",
    dependencies={"express": "^5.1.0"},
    check_families=frozenset({"javascript"}),
    release_files={
        "Dockerfile": """# {{title}}: build with `docker build -t {{project}} .`, run with
# `docker run -p 3000:3000 -v {{project}}-data:/app/data {{project}}`.
FROM node:%(node)s-slim AS page
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npx vite build

FROM node:%(node)s-slim
ENV NODE_ENV=production HOST=0.0.0.0 PORT=3000 DATA_DIR=/app/data
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY server ./server
COPY --from=page /app/dist ./dist
RUN mkdir -p /app/data && chown -R node:node /app/data
USER node
EXPOSE 3000
CMD ["node", "server/index.js"]
""" % {"node": js.NODE_MAJOR},
        ".dockerignore": js.DOCKERIGNORE + "dist/\n",
    },
)

FASTAPI_MAIN = '''"""The service: the JSON interface under /api, and the built page from dist/."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

PAGE = Path(__file__).resolve().parent.parent / "dist"

app = FastAPI(title="{{title}}")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


if (PAGE / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=PAGE / "assets"), name="assets")


@app.middleware("http")
async def the_page(request: Request, call_next):
    """Any address no route answers that is not the API is the page: it routes on the client."""
    response = await call_next(request)
    if (
        response.status_code == 404
        and request.method == "GET"
        and not request.url.path.startswith("/api/")
        and (PAGE / "index.html").is_file()
    ):
        wanted = (PAGE / request.url.path.lstrip("/")).resolve()
        if wanted.is_file() and PAGE in wanted.parents:
            return FileResponse(wanted)
        return FileResponse(PAGE / "index.html")
    return response
'''

UNIT_TESTS = """// Kept by the harness: `npm test` runs the page's unit tests and the service's,
// and writes one report. Run it as it is.
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';

mkdirSync('test-results', { recursive: true });
const parts = [
  // [report, command, arguments, the exit code that means "no tests yet"]
  ['test-results/unit-page.xml', 'node_modules/.bin/vitest',
    ['run', '--passWithNoTests', '--reporter=default', '--reporter=junit',
     '--outputFile.junit=test-results/unit-page.xml'], 0],
  ['test-results/unit-service.xml', %(python)s,
    ['-m', 'pytest', 'tests', '-q', '--junitxml=test-results/unit-service.xml'], 5],
];
let failed = false;
const suites = [];
for (const [report, command, args, none] of parts) {
  rmSync(report, { force: true });
  const run = spawnSync(command, args, { stdio: 'inherit' });
  if (run.status !== 0 && run.status !== none) failed = true;
  if (!existsSync(report)) { failed = true; continue; }
  const text = readFileSync(report, 'utf8');
  suites.push(...(text.match(/<testsuite[\\s>][\\s\\S]*?<\\/testsuite>/g) || []));
}
writeFileSync('test-results/unit.xml', `<?xml version="1.0" encoding="UTF-8"?>\\n<testsuites>\\n${suites.join('\\n')}\\n</testsuites>\\n`);
process.exit(failed ? 1 : 0);
"""

FASTAPI = Service(
    entry="{{package}}/main.py",
    name="fastapi",
    words=("fastapi", "starlette", "uvicorn"),
    label="FastAPI",
    language="python",
    files={
        "requirements.txt": "fastapi>=0.115\nuvicorn>=0.30\n",
        "requirements-dev.txt": "pytest>=8\nhttpx>=0.27\n",
        "pytest.ini": _python.PYTEST_INI.replace("[pytest]\n", "[pytest]\ntestpaths = tests\n"),
        "{{package}}/__init__.py": '"""{{title}}."""\n',
        "{{package}}/main.py": FASTAPI_MAIN,
        "scripts/unit-tests.mjs": UNIT_TESTS % {"python": "'.venv/bin/python'"},
    },
    start_argv="['.venv/bin/python', '-m', 'uvicorn', '{{package}}.main:app', '--host', '127.0.0.1', '--port', process.env.PORT]",
    install=(
        *js.INSTALL,
        *_python.INSTALL,
    ),
    unit_script="node scripts/unit-tests.mjs",
    kept=("pytest.ini", "scripts/unit-tests.mjs"),
    smoke_unit=("tests/test_scaffold_smoke.py", '''from fastapi.testclient import TestClient

from {{package}}.main import app


def test_the_service_reports_its_health():
    assert TestClient(app).get("/api/health").json() == {"status": "ok"}
'''),
    guide="""The service is FastAPI in Python: the application object is `app` in
`{{package}}/main.py` - the JSON interface under `/api/` (keep every route there), and
the built page from `dist/`. Its unit tests go in `tests/`, named `test_<module>.py`, as
pytest functions calling routes through `fastapi.testclient.TestClient(app)`. Install a
Python dependency by adding it to `requirements.txt` (`requirements-dev.txt` for one
only tests use) and running `.venv/bin/python -m pip install -r requirements.txt`.""",
    testing="Vitest for unit tests of the page, pytest for unit tests of the service",
    ci_setup=_python.CI_SETUP,
    check_families=frozenset({"python"}),
    release_files={
        "Dockerfile": """# {{title}}: build with `docker build -t {{project}} .`, run with
# `docker run -p 8000:8000 -v {{project}}-data:/app/data {{project}}`.
FROM node:%(node)s-slim AS page
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npx vite build

FROM python:%(python)s-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8000 DATA_DIR=/app/data
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY {{package}} ./{{package}}
COPY --from=page /app/dist ./dist
RUN useradd --create-home --uid 10001 app && mkdir -p /app/data && chown -R app:app /app/data
USER app
EXPOSE 8000
CMD ["sh", "-c", "exec python -m uvicorn {{package}}.main:app --host \\"$HOST\\" --port \\"$PORT\\""]
""" % {"node": js.NODE_MAJOR, "python": _python.PYTHON_VERSION},
        ".dockerignore": _python.DOCKERIGNORE + "node_modules/\ndist/\n",
    },
)


# --- what every pair shares -------------------------------------------------------

SERVE_ACCEPTANCE = """// Kept by the harness: the acceptance suite's server. Builds the page into dist/,
// then starts the service, which serves it beside /api/ on the port in PORT.
// Playwright starts this for every run of the suite; never start it yourself.
import { spawn } from 'node:child_process';
import { build } from 'vite';

await build({ logLevel: 'warn' });
const service = spawn(%(argv)s[0], %(argv)s.slice(1), { stdio: 'inherit', env: process.env });
service.on('exit', (code) => process.exit(code ?? 1));
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => service.kill(signal));
"""

VITE_CONFIG = """import { defineConfig } from 'vitest/config';
%(plugin_import)s

// The harness builds the page and runs the unit tests through this file; keep
// the `test` block. `npm run dev` serves the page with the service's /api/
// passed through to it on the port in API_PORT.
export default defineConfig({
  plugins: [%(plugin_call)s],
  server: {
    proxy: { '/api': `http://127.0.0.1:${process.env.API_PORT || %(api_port)s}` },
  },
  test: {
    projects: [
      { extends: true, test: { name: 'page', environment: 'jsdom', include: ['tests/client/**/*.test.{ts,tsx}'] } },%(service_project)s
    ],
  },
});
"""

SERVICE_PROJECT = """
      { extends: true, test: { name: 'service', environment: 'node', include: ['tests/server/**/*.test.{js,ts}'] } },"""

PACKAGE_JSON = """{
  "name": "{{project}}",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite --host 127.0.0.1",
    "build": "vite build",
    "start": "%(start)s",
    "test": "%(unit)s",
    "test:acceptance": "playwright test"
  },
  "dependencies": %(dependencies)s,
  "devDependencies": %(dev_dependencies)s
}
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

ACCEPTANCE_GUIDE = """Acceptance tests go in `acceptance/`, named `<feature>.spec.js`, using
`@playwright/test` (`import { test, expect } from '@playwright/test'`). The
configuration builds the page and starts the product's own service with an empty
`DATA_DIR`; open the page with `await page.goto('/')` - never a `file://` address, a
host or a port. """ + js.FIND_CONTROLS + """ Act the way a user does: `fill`,
`click`, `press('Enter')`, `check`, `selectOption`. Test the service's interface with
the `request` fixture (`await request.post('/api/...', { data })`), checking
`response.status()` and `await response.json()`. To prove something persists, change
it, `await page.reload()`, and check it is still there. Tests run one after another
against the same service, so a test must create what it reads and look for its own
records rather than counting all of them.
""" + js.NAMING

DATA_GUIDE = """Data the service keeps lives under the directory in `DATA_DIR` (default `data/`). A
product meant for a database server reads its address from `DATABASE_URL`; when that is
unset it keeps a file database under `DATA_DIR`, which is what every test runs on. The
page reaches the service with `fetch('/api/...')`. Never start a server yourself: the
acceptance suite's configuration builds the page and starts the service."""


def _json(entries: dict[str, str]) -> str:
    import json

    return json.dumps(dict(sorted(entries.items())), indent=2).replace("\n", "\n  ")


def fullstack_pack(frontend: Frontend, service: Service) -> StackPack:
    """The pack for `frontend` served by `service`."""
    api_port = "8000" if service.language == "python" else "3000"
    start = "node scripts/serve-acceptance.mjs"
    unit_glob = frontend.unit_glob
    files = {
        "package.json": PACKAGE_JSON % {
            "start": start,
            "unit": service.unit_script,
            "dependencies": _json({**frontend.dependencies, **service.dependencies}),
            "dev_dependencies": _json({
                "@playwright/test": js.PLAYWRIGHT,
                "axe-core": js.AXE_CORE,
                "jsdom": "^26.0.0",
                "typescript": "^5.6.0",
                "vite": "^7.0.0",
                "vitest": "^3.2.0",
                **frontend.dev_dependencies,
                **service.dev_dependencies,
            }),
        },
        "vite.config.ts": VITE_CONFIG % {
            "plugin_import": frontend.vite_plugin_import,
            "plugin_call": frontend.vite_plugin_call,
            "api_port": api_port,
            "service_project": SERVICE_PROJECT if service.language != "python" else "",
        },
        "playwright.config.js": js.playwright_config(
            start, "/api/health", screenshot="on", checks_the_page=True,
        ),
        "playwright.setup.mjs": js.page_check("/"),
        "scripts/serve-acceptance.mjs": SERVE_ACCEPTANCE % {"argv": service.start_argv},
        ".gitignore": js.GITIGNORE + "dist/\n" + (_python.GITIGNORE if service.language == "python" else ""),
        **frontend.files,
        **service.files,
    }
    title = f"Browser app in {frontend.label} with its own HTTP service in {service.label}"
    return StackPack(
        name=f"fullstack-{frontend.name}-{service.name}",
        title=title,
        kind="fullstack",
        language=service.language if service.language == "python" else "typescript",
        frameworks=service.words,
        frontend_frameworks=frontend.words,
        files=files,
        install=service.install,
        unit_test=js.UNIT_TEST,
        acceptance_test=js.ACCEPTANCE_TEST,
        unit_report="test-results/unit.xml",
        acceptance_report="test-results/acceptance.xml",
        unit_dir="tests",
        acceptance_dir="acceptance",
        acceptance_pattern="*.spec.js",
        unit_pattern=unit_glob,
        kept_files=(
            "playwright.config.js", "playwright.setup.mjs", "vite.config.ts", "scripts/serve-acceptance.mjs",
            *service.kept,
        ),
        kept_scripts={"test": service.unit_script, "test:acceptance": "playwright test", "start": start},
        smoke_files={
            frontend.smoke_unit[0]: frontend.smoke_unit[1],
            service.smoke_unit[0]: service.smoke_unit[1],
            "acceptance/scaffold-smoke.spec.js": SMOKE_ACCEPTANCE,
        },
        guide=f"{frontend.guide}\n{service.guide}\nRun every unit test with `npm test`. {DATA_GUIDE}",
        entrypoints=tuple(e for e in (frontend.entry, service.entry) if e),
        acceptance_guide=ACCEPTANCE_GUIDE,
        stack={
            "language": "Python and TypeScript" if service.language == "python" else "TypeScript and JavaScript",
            "framework": service.label,
            "frontend_framework": f"{frontend.label} on Vite",
            "testing_framework": f"{service.testing}, Playwright for acceptance tests",
        },
        check_families=frozenset({"javascript", "browser", "typescript"}) | service.check_families,
        evidence_dir="test-results/evidence",
        test_bugs=js.TEST_BUGS + (_python.TEST_BUGS if service.language == "python" else ()),
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
        ci_setup=js.CI_SETUP + service.ci_setup,
        ci_prepare=js.CI_BROWSERS,
        release_files=service.release_files,
    )
