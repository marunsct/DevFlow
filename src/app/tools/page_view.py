"""Look at the product's page as it runs: what a person - and a test - would find on it.

A stage fixing a page had the test's failure message to go on and nothing
else: "locator getByRole('button', { name: 'Save' }) resolved to 0 elements"
says what was not there, never what was. It guessed, ran the suite, guessed
again - and the run whose fix stage spent its three attempts on one form was
lost that way.

This starts the product exactly as the acceptance suite does - the project's
own Playwright configuration and its server command, on a free port - opens one
path in a real browser and returns the page's accessibility tree (the roles and
names a test finds controls by), the errors the page itself raised, and the
requests that failed. Playwright's MCP server answers the same question; this
uses the browser and the server start the suite already proved, so the answer
is about the page the suite will see.

The overlay files live in the project's `test-results/`, which every pack
ignores, and are removed afterwards; the project's configuration, the locked
suite and their reports are not touched.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Callable, Sequence

logger = logging.getLogger(__name__)

#: Where the overlay is written, relative to the project.
OVERLAY_DIR = "test-results/page-view"
#: The longest accessibility tree returned.
MAX_TREE = 8_000
#: The most errors or failed requests returned.
MOST_LISTED = 15

_CONFIG_NAMES = ("playwright.config.js", "playwright.config.ts", "playwright.config.mjs", "playwright.config.mts", "playwright.config.cjs")

_VIEWPORTS = {"desktop": (1280, 800), "phone": (390, 844)}

OVERLAY_CONFIG = """import { fileURLToPath } from 'node:url';
import base from '../../%(config)s';

const project = fileURLToPath(new URL('../../', import.meta.url));

export default {
  ...base,
  testDir: '.',
  testMatch: 'look.spec.mjs',
  timeout: 60_000,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  outputDir: './out',
  globalSetup: undefined,
  globalTeardown: undefined,
  projects: undefined,
  use: { ...(base.use || {}), screenshot: 'off', trace: 'off', video: 'off' },
  webServer: base.webServer && (Array.isArray(base.webServer)
    ? base.webServer.map((server) => ({ cwd: project, ...server }))
    : { cwd: project, ...base.webServer }),
};
"""

LOOK_SPEC = """import { test } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';

const here = new URL('./', import.meta.url);
const wanted = JSON.parse(readFileSync(new URL('look.json', here), 'utf8'));

test('look', async ({ page }) => {
  const errors = [];
  const failed = [];
  page.on('pageerror', (error) => errors.push(String(error.message)));
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('requestfailed', (request) => failed.push(`${request.method()} ${request.url()} ${request.failure()?.errorText ?? ''}`));
  page.on('response', (response) => {
    if (response.status() >= 400) failed.push(`${response.status()} ${response.request().method()} ${response.url()}`);
  });
  await page.setViewportSize({ width: wanted.width, height: wanted.height });
  const response = await page.goto(wanted.path);
  await page.waitForLoadState('networkidle', { timeout: 5_000 }).catch(() => {});
  const tree = await page.locator('body').ariaSnapshot().catch((error) => `(no tree: ${error.message})`);
  const wide = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  writeFileSync(new URL('seen.json', here), JSON.stringify({
    status: response ? response.status() : null, url: page.url(), title: await page.title(),
    tree, errors, failed, wider_than_the_screen: wide,
  }));
});
"""

#: Runs one argv in the project: (argv, category, project) -> outcome.
Runner = Callable[[Sequence[str], str, str], dict]


def _the_config(project_root: Path) -> str | None:
    return next((name for name in _CONFIG_NAMES if (project_root / name).is_file()), None)


def available(repo_root: str | Path) -> bool:
    """Whether this run's product is a page the suite opens through Playwright."""
    try:
        from app.stacks import contract

        found = contract.the_pack(repo_root)
    except Exception:  # noqa: BLE001
        return False
    if found is None or found[0].kind not in {"browser_app", "fullstack"}:
        return False
    project = str(found[1].get("project") or "")
    root = Path(repo_root) / project
    return _the_config(root) is not None and (root / "node_modules" / "@playwright" / "test").is_dir()


def look(repo_root: str | Path, path: str = "/", viewport: str = "desktop", *, run: Runner | None = None) -> dict[str, Any]:
    """Start the product as the suite does, open `path`, and say what is on the page."""
    from app.stacks import contract

    found = contract.the_pack(repo_root)
    if found is None:
        return {"error": "This project has no test setup that starts its page."}
    project = str(found[1].get("project") or "")
    project_root = Path(repo_root) / project
    config = _the_config(project_root)
    if config is None:
        return {"error": "The project has no Playwright configuration to start its page with."}
    path = "/" + str(path or "/").strip().lstrip("/")
    if "://" in path or ".." in path:
        return {"error": "Give a path on the product's own server, such as / or /settings."}
    width, height = _VIEWPORTS.get(str(viewport).lower(), _VIEWPORTS["desktop"])
    overlay = project_root / OVERLAY_DIR
    shutil.rmtree(overlay, ignore_errors=True)
    overlay.mkdir(parents=True)
    try:
        (overlay / "playwright.config.mjs").write_text(OVERLAY_CONFIG % {"config": config}, encoding="utf-8")
        (overlay / "look.spec.mjs").write_text(LOOK_SPEC, encoding="utf-8")
        (overlay / "look.json").write_text(json.dumps({"path": path, "width": width, "height": height}), encoding="utf-8")
        if run is None:
            from app.stacks.scaffold import sandbox_runner

            run = sandbox_runner(repo_root)
        outcome = run(["npx", "playwright", "test", "--config", f"{OVERLAY_DIR}/playwright.config.mjs"], "test", project)
        try:
            seen = json.loads((overlay / "seen.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            output = f"{outcome.get('error') or ''}\n{outcome.get('stdout') or ''}\n{outcome.get('stderr') or ''}".strip()
            return {"error": "The page could not be opened. The browser run ended:\n" + output[-2_000:]}
    finally:
        shutil.rmtree(overlay, ignore_errors=True)
    tree = str(seen.get("tree") or "")
    return {
        "path": path,
        "viewport": f"{width}x{height}",
        "status": seen.get("status"),
        "title": seen.get("title"),
        "accessibility_tree": tree if len(tree) <= MAX_TREE else tree[:MAX_TREE] + "\n... (cut short)",
        "page_errors": list(dict.fromkeys(seen.get("errors") or []))[:MOST_LISTED],
        "failed_requests": list(dict.fromkeys(seen.get("failed") or []))[:MOST_LISTED],
        "wider_than_the_screen": bool(seen.get("wider_than_the_screen")),
    }


def build_page_view_tool(repo_root: str) -> Any:
    from langchain_core.tools import tool

    @tool
    def look_at_page(path: str = "/", viewport: str = "desktop") -> dict[str, Any]:
        """Open the product's page in a real browser and see what is on it.

        Starts the product the way the acceptance tests do and returns the
        page's accessibility tree - each element's role and accessible name,
        which is exactly what a test finds controls by - plus the errors the
        page raised and the requests that failed. Use it before changing a page
        to make a failing test pass: compare what the test looks for with what
        the page shows. It takes some seconds; it changes nothing.

        Args:
            path: the path on the product's server, e.g. "/" or "/settings".
            viewport: "desktop" (1280x800) or "phone" (390x844).
        """
        try:
            return look(repo_root, path, viewport)
        except Exception as exc:  # noqa: BLE001 - a look that fails is an answer, not a crash
            logger.warning("Could not look at the page", exc_info=True)
            return {"error": f"The page could not be opened ({type(exc).__name__}): {exc}"}

    return look_at_page


def page_view_tools(repo_root: str) -> list[Any]:
    """The tool, for a product whose page the suite opens; empty otherwise or when switched off."""
    import os

    if os.environ.get("PAGE_VIEW_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
        return []
    return [build_page_view_tool(repo_root)] if available(repo_root) else []
