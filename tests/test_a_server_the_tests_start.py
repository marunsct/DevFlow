"""The harness asked for this server and then blocked the sprint for it.

`TESTABILITY_RULE` tells the model, in these words, to "let Playwright manage
the server itself - declare a `webServer` in `playwright.config.ts`".
One run's model did exactly that, with `command: 'node server.mjs'`, and
two checks reported `server.mjs` as blocking:

  task-manager/server.mjs starts an HTTP server, and this run's stack declares
  its storage as 'Browser localStorage' ... the product it describes has no
  server
  task-manager/server.mjs is never loaded by a page or imported by another
  module. Nothing runs it.

Playwright ran it on every test. Both findings are about a file the harness
itself ordered into existence.

Two separate causes, fixed separately and tested separately here:

* `_orphaned_scripts` knew two kinds of caller, a `<script>` tag and an
  `import`. A command that runs the file is a third, and it is written down in
  a config, a Dockerfile, a CI workflow, a Procfile or a README in every
  language. None were counted.
* `_a_server_in_a_browser_only_product` could not tell a product server from
  test infrastructure. A server a test runner starts ships to nobody.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.integration_checks import (
    _a_server_in_a_browser_only_product,
    _files_a_command_launches,
    _servers_started_by_a_test_runner,
    _source_files,
    _unreferenced_scripts,
)

SERVER = """\
import { createServer } from 'node:http';
createServer((req, res) => res.end('ok')).listen(3000);
"""

CONFIG = """\
import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: '.',
  webServer: { command: 'node server.mjs', url: 'http://localhost:3000' },
});
"""

PAGE = "<!doctype html><html><body><script src='app.js'></script></body></html>"


def _project(root: Path, **files: str) -> list[Path]:
    for name, text in files.items():
        path = root / name.replace("__", ".")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return _source_files(root)


class _Stack:
    database = "Browser localStorage"


# --- the command is a caller, in every language ----------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("webServer: { command: 'node server.mjs' }", "server.mjs"),
        ('CMD ["python", "-u", "app.py"]', "app.py"),
        ('ENTRYPOINT ["dotnet", "Api.dll"]', "Api.dll"),
        ("run: deno run --allow-net main.ts", "main.ts"),
        ("web: ruby bin/worker.rb", "worker.rb"),
        ("\tjava -jar target/app.jar", "app.jar"),
        ("Run it with `node server.mjs`.", "server.mjs"),
        ("command: bun --watch start.ts", "start.ts"),
        ("php public/index.php", "index.php"),
    ],
)
def test_a_runtime_handed_a_file_is_a_caller(text: str, expected: str):
    assert expected in _files_a_command_launches(text)


def test_a_word_that_merely_reads_like_a_runtime_is_not_a_launch():
    assert _files_a_command_launches("const port = node.address().port;") == set()


# --- the orphan check ------------------------------------------------------


def test_a_server_a_config_starts_is_not_an_orphan(tmp_path: Path):
    files = _project(
        tmp_path,
        server__mjs=SERVER,
        playwright__config__ts=CONFIG,
        index__html=PAGE,
        app__js="export const go = () => 1;",
    )
    assert _unreferenced_scripts(files, tmp_path) == []


def test_a_file_nothing_runs_is_still_an_orphan(tmp_path: Path):
    """The exemption must not switch the check off."""
    files = _project(
        tmp_path,
        server__mjs=SERVER,
        playwright__config__ts=CONFIG,
        index__html=PAGE,
        app__js="export const go = () => 1;",
        stranded__js="export const never = () => 2;",
    )
    problems = _unreferenced_scripts(files, tmp_path)
    assert len(problems) == 1
    assert "stranded.js" in problems[0]


def test_a_dockerfile_command_counts_too(tmp_path: Path):
    """Deliberately not a test-runner rule: any command that runs it counts."""
    files = _project(
        tmp_path,
        server__mjs=SERVER,
        index__html=PAGE,
        app__js="export const go = () => 1;",
        Dockerfile='FROM node:22\nCMD ["node", "server.mjs"]\n',
    )
    assert _unreferenced_scripts(files, tmp_path) == []


# --- the browser-only-storage check ---------------------------------------


def test_a_server_the_test_runner_starts_is_not_a_second_data_layer(tmp_path: Path):
    files = _project(
        tmp_path, server__mjs=SERVER, playwright__config__ts=CONFIG, index__html=PAGE
    )
    assert _a_server_in_a_browser_only_product(files, tmp_path, _Stack()) == []


def test_a_server_no_runner_starts_is_still_reported(tmp_path: Path):
    files = _project(tmp_path, server__mjs=SERVER, index__html=PAGE)
    problems = _a_server_in_a_browser_only_product(files, tmp_path, _Stack())
    assert len(problems) == 1
    assert "server.mjs" in problems[0]


@pytest.mark.parametrize(
    "config_name",
    ["cypress.config.js", "wdio.conf.ts", "karma.conf.js", "nightwatch.conf.js"],
)
def test_every_browser_runner_declares_it_the_same_way(tmp_path: Path, config_name: str):
    files = _project(
        tmp_path,
        server__mjs=SERVER,
        index__html=PAGE,
        **{config_name.replace(".", "__"): "module.exports = { command: 'node server.mjs' };"},
    )
    assert _a_server_in_a_browser_only_product(files, tmp_path, _Stack()) == []


def test_an_ordinary_config_does_not_exempt_a_server(tmp_path: Path):
    """`vite.config.js` is a build tool, not a test runner starting a harness."""
    files = _project(
        tmp_path,
        server__mjs=SERVER,
        index__html=PAGE,
        vite__config__js="export default { command: 'node server.mjs' };",
    )
    assert _servers_started_by_a_test_runner(files, tmp_path) == set()
    assert _a_server_in_a_browser_only_product(files, tmp_path, _Stack()) != []
