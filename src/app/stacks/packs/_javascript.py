"""What every JavaScript pack shares: node:test units and Playwright acceptance runs."""

from __future__ import annotations

#: The Playwright release whose browser build the image installs. A different
#: version looks for a browser build that is not there.
PLAYWRIGHT = "1.63.0"

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


def playwright_config(server_command: str, ready_path: str = "/", screenshot: str = "only-on-failure") -> str:
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
  outputDir: 'test-results/evidence',
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
""" % {"command": server_command, "ready": ready_path, "screenshot": screenshot}


UNIT_GUIDE = """Unit tests go in `tests/`, one file per module, named `<module>.test.js`, using
`node:test` and `node:assert/strict`, and import the product's modules directly.
Run them with `npm test`. Install a dependency with `npm install <name>` (add
`--save-dev` for one only tests use). Never start a server yourself."""

NAMING = """Each test's title starts with the id of the criterion it proves, in square
brackets: `test('[AC-3] a completed item stays completed after a reload', ...)`
(a test that proves two: `[AC-3][AC-4] ...`). A test with no criterion id in its
title proves nothing the harness can count."""


#: A Playwright failure raised by the spec's own code. Product code runs in the
#: page, where its errors surface through `page.evaluate` or as failed
#: expectations, so a bare TypeError or ReferenceError is the test's. One run's
#: locked suite called `addTask(page, ...)` on a helper declared
#: `addTask({ page }, ...)`: nine of eleven tests threw before touching the page.
TEST_BUGS = (
    r"^(?!.*\bevaluate\b).*\b(?:TypeError|ReferenceError|SyntaxError)\b",
    r"^(?!.*\bevaluate\b).*Cannot read propert(?:y|ies) of (?:undefined|null)",
    r"^(?!.*\bevaluate\b).*\bis not a function\b",
    r"^(?!.*\bevaluate\b).*\bis not defined\b",
)
