"""HTTP services in any language, tested from outside the way a client meets them.

The service is written in its own language and tested by its own runner,
reporting JUnit XML. Its acceptance suite is Playwright's `request` fixture
against the running service, with the machinery every pack shares: a free
port in `PORT`, a fresh `DATA_DIR`, and the service built and started by the
suite's configuration. QA therefore writes acceptance tests one way, whatever
the service is written in, and a stage that builds the service never runs it
by hand.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.stacks import StackPack
from app.stacks.packs import _javascript as js

PACKAGE_JSON = """{
  "name": "{{project}}-acceptance",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "test:acceptance": "playwright test"
  },
  "devDependencies": {
    "@playwright/test": "%s"
  }
}
""" % js.PLAYWRIGHT

SMOKE_ACCEPTANCE = """import { test, expect } from '@playwright/test';

test('the running service answers', async ({ request }) => {
  const response = await request.get('/health');
  expect(response.ok()).toBeTruthy();
  expect(await response.json()).toEqual({ status: 'ok' });
});
"""

ACCEPTANCE_GUIDE = """Acceptance tests go in `acceptance/`, named `<feature>.spec.js`, using
`@playwright/test` (`import { test, expect } from '@playwright/test'`) and its
`request` fixture, which calls the running service the way a client does:
`const response = await request.post('/items', { data: { ... } })`, then check
`response.status()` and `await response.json()`. The configuration builds and
starts the service with an empty `DATA_DIR`; tests run one after another against
the same service, so a test must create what it reads and look for its own
records rather than counting all of them.
""" + js.NAMING

#: The harness's own helper for the one thing the suite's single running service cannot do: stop the service and start
#: it again on the same data. It runs the project's `start.sh` (which the pack writes and keeps) on a free port and the
#: data folder the test names. Measured over five runs: QA marked every persistence criterion "cannot be verified, the
#: server runs once per suite" and shipped it deferred; one product lost its notes on a restart and the hidden test caught it.
SERVICE_HELPER = """'use strict';
// Kept by the harness. Starts the project's own start script on a free port and a data folder of the test's choosing, so a
// test can stop the service and start it again on the same data.
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const net = require('node:net');
const os = require('node:os');
const path = require('node:path');

const PROJECT = path.resolve(__dirname, '..');
// Every service started here, stopped when this process ends even if a test never calls `stop()`.
const STARTED = new Set();
function stopAll() {
  for (const pid of STARTED) {
    try { process.kill(-pid, 'SIGKILL'); } catch (ignored) { /* already gone */ }
  }
  STARTED.clear();
}
process.once('exit', stopAll);
for (const signalName of ['SIGINT', 'SIGTERM']) {
  process.once(signalName, () => { stopAll(); process.exit(1); });
}

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

async function waitUntilUp(baseURL, child, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) throw new Error('the service exited with code ' + child.exitCode + ' before it answered');
    try {
      await fetch(baseURL + '/health');
      return;
    } catch (error) {
      await new Promise((resolve) => setTimeout(resolve, 200));
    }
  }
  throw new Error('the service did not answer within ' + timeoutMs + ' ms');
}

async function startService({ dataDir, timeoutMs = 60000 } = {}) {
  const directory = dataDir || fs.mkdtempSync(path.join(os.tmpdir(), 'service-data-'));
  const port = await freePort();
  const child = spawn('sh', ['start.sh'], {
    cwd: PROJECT,
    env: { ...process.env, PORT: String(port), HOST: '127.0.0.1', DATA_DIR: directory, HARNESS_SERVICE_OF: PROJECT },
    stdio: 'ignore',
    detached: true,
  });
  // The test process may end without waiting for the service; its exit handler then stops it.
  child.unref();
  STARTED.add(child.pid);
  const baseURL = 'http://127.0.0.1:' + port;
  try {
    await waitUntilUp(baseURL, child, timeoutMs);
  } catch (error) {
    try { process.kill(-child.pid, 'SIGKILL'); } catch (ignored) { /* already gone */ }
    throw error;
  }
  return {
    baseURL,
    dataDir: directory,
    async stop() {
      if (child.exitCode !== null) return;
      const exited = new Promise((resolve) => child.once('exit', resolve));
      try { process.kill(-child.pid, 'SIGTERM'); } catch (ignored) { /* already gone */ }
      await Promise.race([exited, new Promise((resolve) => setTimeout(resolve, 5000))]);
      try { process.kill(-child.pid, 'SIGKILL'); } catch (ignored) { /* already gone */ }
      STARTED.delete(child.pid);
    },
  };
}

module.exports = { startService };
"""

#: The factory the kept start file calls is called as it is: measured on a small-model run, `createApp` was made
#: `async` to load the data first, the kept start file then served the `fetch` of a Promise, and every request
#: answered 500 for two sprint attempts. On the next two runs the draft wrote `export default function
#: createApp(dataDir)` - a default export with a parameter - and the service did not load.
FACTORY_GUIDE = (
    "`createApp()` is a named export (`export function createApp()`, not `export default`) that takes no "
    "parameters: the start file calls it with none, so it reads what it needs - `DATA_DIR`, limits - from the "
    "environment itself. It returns the application itself, never a Promise: the start file uses the result at "
    "once, so it is not `async`. Data the service needs is loaded inside the handlers that use it (or once, on the "
    "first request), not before `createApp` returns."
)

RESTART_GUIDE = """A criterion about the data surviving a restart is tested, not deferred, and only that criterion uses the
harness's helper `acceptance/service.cjs`; every other test uses the `request` fixture against the service the
configuration already started. For the restart criterion: `const { startService } = require('./service.cjs');` then
`const first = await startService(); await request.post(first.baseURL + '/items', { data: { ... } }); await first.stop();
const second = await startService({ dataDir: first.dataDir }); const kept = await request.get(second.baseURL + '/items');
... await second.stop();`. Requests always send a body as `data: { ... }` - the `request` fixture does not read a `body:`
option and the service would receive nothing. Do not edit the helper."""

#: What "every test runs on the file database" means for the schema.
ON_THE_FILE_DATABASE = (
    "The schema, its column types, its queries and its migrations must work on that file "
    "database as well as on the server: the tests never reach a database server, so a type "
    "or a query only the server has stops the product before any test runs."
)

DATA_GUIDE = """A service that stores data keeps it under the directory in the `DATA_DIR`
environment variable (default `data/`), never in memory only; one meant for a
database server reads its address from `DATABASE_URL` and, when that is unset,
keeps a file database under `DATA_DIR`, which is what every test runs on. """ + ON_THE_FILE_DATABASE + """ The
service listens on the port in `PORT` and the interface in `HOST`. Never start
it yourself: the acceptance suite's configuration builds and starts it."""

GITIGNORE = js.GITIGNORE

#: How a person (or anything that deploys it) starts the service: the pack's own start command, from the project.
START_SCRIPT = """#!/bin/sh
cd "$(dirname "$0")" && %s
"""


def service_pack(
    *,
    name: str,
    title: str,
    language: str,
    frameworks: tuple[str, ...],
    files: Mapping[str, str],
    install: tuple[tuple[str, ...], ...],
    unit_test: tuple[str, ...],
    unit_report: str,
    unit_dir: str,
    unit_pattern: str,
    start: str,
    server_timeout_ms: int,
    smoke_unit: tuple[str, str],
    guide: str,
    stack: Mapping[str, str],
    ci_setup: tuple[str, ...],
    release_files: Mapping[str, str],
    kept_files: tuple[str, ...] = (),
    gitignore: str = "",
    kept_scripts: dict[str, str] | None = None,
    entrypoint: str = "",
    required_exports: Mapping[str, tuple[str, ...]] | None = None,
    relative_import_extension: str = "",
    typecheck: tuple[str, ...] = (),
) -> StackPack:
    """A pack for an HTTP service in its own language, accepted through Playwright's `request` fixture."""
    # The brief names the service by its `start.sh`, and the suite runs that script when the project has one
    # (`the_brief_s_start_or`). Left to the team, a small model wrote one that ran the module defining the
    # application and never listening: the web server timed out and no test ran. The pack writes it, from its own
    # start command, and keeps it - as the Python packs do.
    script = {"start.sh": START_SCRIPT % start} if "\n" not in start.strip() else {}
    return StackPack(
        name=name,
        title=title,
        kind="http_api",
        language=language,
        frameworks=frameworks,
        # A service in JavaScript brings its own manifest, holding the
        # acceptance runner beside its own dependencies; any other language
        # gets one that holds only the runner.
        files={
            "package.json": PACKAGE_JSON,
            **files,
            **script,
            "acceptance/service.cjs": SERVICE_HELPER,
            "playwright.config.js": js.playwright_config(js.the_brief_s_start_or(start), "/health", server_timeout_ms=server_timeout_ms),
            ".gitignore": GITIGNORE + gitignore,
        },
        install=(*install, *js.INSTALL),
        unit_test=unit_test,
        acceptance_test=js.ACCEPTANCE_TEST,
        unit_report=unit_report,
        acceptance_report="test-results/acceptance.xml",
        unit_dir=unit_dir,
        acceptance_dir="acceptance",
        acceptance_pattern="*.spec.js",
        unit_pattern=unit_pattern,
        kept_files=("playwright.config.js", "acceptance/service.cjs", *script, *kept_files),
        kept_scripts={"test:acceptance": "playwright test", **(kept_scripts or {})},
        entrypoint=entrypoint,
        required_exports=dict(required_exports or {}),
        relative_import_extension=relative_import_extension,
        typecheck=typecheck,
        smoke_files={smoke_unit[0]: smoke_unit[1], "acceptance/scaffold-smoke.spec.js": SMOKE_ACCEPTANCE},
        guide=f"{guide}\n{DATA_GUIDE}",
        data_store=DATA_GUIDE,
        acceptance_guide=f"{ACCEPTANCE_GUIDE}\n{RESTART_GUIDE}",
        stack=stack,
        evidence_dir="test-results/evidence",
        test_bugs=js.TEST_BUGS,
        module_system_mismatch=js.module_system_mismatch,
        unawaited_helpers=js.unawaited_helpers,
        assertion_names=js.playwright_assertions,
        code_runs_in="node",
        ci_setup=(*ci_setup, *js.CI_SETUP),
        release_files=release_files,
        server_wait_ms=server_timeout_ms,
    )
