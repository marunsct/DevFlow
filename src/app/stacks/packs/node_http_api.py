"""An HTTP service in JavaScript, on Express."""

from __future__ import annotations

from app.stacks import StackPack
from app.stacks.packs import _javascript as js

PACKAGE_JSON = """{
  "name": "{{project}}",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "start": "node src/index.js",
    "test": "%(unit)s",
    "test:acceptance": "playwright test"
  },
  "dependencies": {
    "express": "^5.1.0"
  },
  "devDependencies": {
    "@playwright/test": "%(playwright)s"
  }
}
""" % {"unit": js.UNIT_SCRIPT, "playwright": js.PLAYWRIGHT}

APP = """import express from 'express';

// Builds the service. `src/index.js` starts it; unit tests call it directly.
export function createApp() {
  const app = express();
  app.use(express.json());

  app.get('/health', (request, response) => {
    response.json({ status: 'ok' });
  });

  return app;
}
"""

INDEX = """import { createApp } from './app.js';

const port = Number(process.env.PORT || 3000);

const host = process.env.HOST || '127.0.0.1';

createApp().listen(port, host, () => {
  console.log(`Listening on http://${host}:${port}`);
});
"""

#: How the service is started, by its `start` script and by its container.
SERVE_COMMAND = "node src/index.js"

#: How a person (or anything that deploys it) starts the service: the port in
#: PORT, the interface in HOST (default 127.0.0.1), its data under DATA_DIR.
START = f"""#!/bin/sh
cd "$(dirname "$0")" && exec {SERVE_COMMAND}
"""

SMOKE_UNIT = """import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createApp } from '../src/app.js';

test('the service reports its health', async () => {
  const server = createApp().listen(0, '127.0.0.1');
  await new Promise((resolve) => server.once('listening', resolve));
  try {
    const { port } = server.address();
    const response = await fetch(`http://127.0.0.1:${port}/health`);
    assert.deepEqual(await response.json(), { status: 'ok' });
  } finally {
    server.close();
  }
});
"""

SMOKE_ACCEPTANCE = """import { test, expect } from '@playwright/test';

test('the running service answers', async ({ request }) => {
  const response = await request.get('/health');
  expect(response.ok()).toBeTruthy();
  expect(await response.json()).toEqual({ status: 'ok' });
});
"""

GUIDE = js.UNIT_GUIDE + """
The service is built by `createApp()` in `src/app.js` and started by
`src/index.js` on the port in `PORT`. A service that stores data keeps it under
the directory in the `DATA_DIR` environment variable (default `data/`), never in
memory only. A unit test starts `createApp()` on port 0 and calls it with
`fetch`."""

ACCEPTANCE_GUIDE = """Acceptance tests go in `acceptance/`, named `<feature>.spec.js`, using
`@playwright/test` (`import { test, expect } from '@playwright/test'`) and its
`request` fixture, which calls the running service the way a client does:
`const response = await request.post('/items', { data: { ... } })`, then check
`response.status()` and `await response.json()`. The configuration starts the
service with an empty `DATA_DIR`; tests run one after another against the same
service, so a test must create what it reads and look for its own records
rather than counting all of them.
""" + js.NAMING

PACK = StackPack(
    name="node-http-api",
    title="HTTP service in JavaScript on Express",
    kind="http_api",
    language="javascript",
    frameworks=("express", "node", "node.js", "http"),
    files={
        "package.json": PACKAGE_JSON,
        "playwright.config.js": js.playwright_config("node src/index.js", "/health"),
        "src/app.js": APP,
        "src/index.js": INDEX,
        "start.sh": START,
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
    kept_files=("playwright.config.js",),
    kept_scripts={"start": SERVE_COMMAND, "test": js.UNIT_SCRIPT, "test:acceptance": "playwright test"},
    smoke_files={
        "tests/scaffold-smoke.test.js": SMOKE_UNIT,
        "acceptance/scaffold-smoke.spec.js": SMOKE_ACCEPTANCE,
    },
    guide=GUIDE,
    acceptance_guide=ACCEPTANCE_GUIDE,
    stack={
        "language": "JavaScript",
        "framework": "Express",
        "frontend_framework": "",
        "testing_framework": "node:test for unit tests, Playwright (request fixture) for acceptance tests",
    },
    check_families=frozenset({"javascript"}),
    evidence_dir="test-results/evidence",
    test_bugs=js.TEST_BUGS,
    assertion_names=js.playwright_assertions,
    module_system_mismatch=js.module_system_mismatch,
    unawaited_helpers=js.unawaited_helpers,
    locators_with_an_ignored_option=js.locators_with_a_name_option,
    code_runs_in="node",
    ci_setup=js.CI_SETUP,
    # The `request` fixture needs no browser.
    release_files={"Dockerfile": js.service_dockerfile(SERVE_COMMAND), ".dockerignore": js.DOCKERIGNORE},
)
