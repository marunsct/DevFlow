"""A runner that waits on a port its own server never listens on.

One run's `playwright.config.js` declared
`webServer: { command: 'node e2e/server.js', port: 3002 }`, and `e2e/server.js`
had `const port = 3000`. Playwright started the server, waited for 3002 and
timed out before a single test ran; a fix stage then edited the config's port,
the half that was not wrong.
"""

from __future__ import annotations

import pytest

from app.analysis.integration_checks import (
    _a_test_server_on_another_port,
    _source_files,
    summarise_integration,
)

CONFIG = """import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: 'e2e',
  webServer: {
    command: 'node e2e/server.js',
    port: 3002,
  },
  use: { baseURL: 'http://localhost:3002' },
});
"""

SERVER = """import { createServer } from 'node:http';
const server = createServer((req, res) => res.end('ok'));
const port = {port};
server.listen(port, () => console.log('listening'));
"""


def _project(tmp_path, server: str):
    app = tmp_path / "app"
    (app / "e2e").mkdir(parents=True)
    (app / "playwright.config.js").write_text(CONFIG, encoding="utf-8")
    (app / "e2e" / "server.js").write_text(server, encoding="utf-8")
    (app / "e2e" / "app.spec.js").write_text(
        "import { test } from '@playwright/test';\ntest('x', async ({ page }) => { await page.goto('/'); });\n",
        encoding="utf-8",
    )
    return tmp_path


def test_the_two_ports_are_named(tmp_path) -> None:
    root = _project(tmp_path, SERVER.replace("{port}", "3000"))

    problems = _a_test_server_on_another_port(_source_files(root), root)

    assert len(problems) == 1
    assert "waits for it on port 3002" in problems[0]
    assert "listens on 3000" in problems[0]


def test_it_blocks(tmp_path) -> None:
    root = _project(tmp_path, SERVER.replace("{port}", "3000"))

    summary = summarise_integration(root)

    assert "listens on 3000" in summary.split("DOES NOT WORK")[1].split("untidy")[0]


@pytest.mark.parametrize("server", [
    SERVER.replace("{port}", "3002"),
    SERVER.replace("const port = {port};", "const port = process.env.PORT || 3000;"),
    SERVER.replace("const port = {port};\nserver.listen(port", "server.listen(Number(process.argv[2])"),
])
def test_a_server_that_agrees_or_takes_its_port_from_outside_is_left_alone(tmp_path, server: str) -> None:
    root = _project(tmp_path, server)

    assert _a_test_server_on_another_port(_source_files(root), root) == []
