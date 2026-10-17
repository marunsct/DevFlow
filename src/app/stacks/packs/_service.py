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

DATA_GUIDE = """A service that stores data keeps it under the directory in the `DATA_DIR`
environment variable (default `data/`), never in memory only; one meant for a
database server reads its address from `DATABASE_URL` and, when that is unset,
keeps a file database under `DATA_DIR`, which is what every test runs on. The
service listens on the port in `PORT` and the interface in `HOST`. Never start
it yourself: the acceptance suite's configuration builds and starts it."""

GITIGNORE = js.GITIGNORE


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
) -> StackPack:
    """A pack for an HTTP service in its own language, accepted through Playwright's `request` fixture."""
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
            "playwright.config.js": js.playwright_config(start, "/health", server_timeout_ms=server_timeout_ms),
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
        kept_files=("playwright.config.js", *kept_files),
        kept_scripts={"test:acceptance": "playwright test", **(kept_scripts or {})},
        entrypoint=entrypoint,
        smoke_files={smoke_unit[0]: smoke_unit[1], "acceptance/scaffold-smoke.spec.js": SMOKE_ACCEPTANCE},
        guide=f"{guide}\n{DATA_GUIDE}",
        acceptance_guide=ACCEPTANCE_GUIDE,
        stack=stack,
        evidence_dir="test-results/evidence",
        test_bugs=js.TEST_BUGS,
        module_system_mismatch=js.module_system_mismatch,
        unawaited_helpers=js.unawaited_helpers,
        assertion_names=js.playwright_assertions,
        code_runs_in="node",
        ci_setup=(*ci_setup, *js.CI_SETUP),
        release_files=release_files,
    )
