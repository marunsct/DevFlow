"""A server in a product whose own stack says there is none.

One run chose "Vanilla JavaScript" with "Web LocalStorage" and wrote its
own rationale: "Web LocalStorage meets this requirement without any server or
additional libraries ... the application runs entirely in the browser". A
specialist then wrote a 3,696-byte `server.js` - `createServer` from
`node:http`, persisting to `data.json`, with its own test file - and a second
data layer the page never talks to.

`describe_stack` tells every specialist not to introduce a different language,
framework, database or test runner. A server is none of those four, so nothing
said no.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.analysis.integration_checks import (
    _a_server_in_a_browser_only_product,
    _severity_of,
    _source_files,
)

BROWSER = SimpleNamespace(
    language="JavaScript", framework="Vanilla JavaScript",
    database="Web LocalStorage", testing_framework="Node Built-in Test",
    additional_tools=[],
)
SERVED = SimpleNamespace(
    language="Python", framework="FastAPI", database="PostgreSQL",
    testing_framework="pytest", additional_tools=[],
)

SERVER = (
    'import { createServer } from "http";\n'
    'const server = createServer((req, res) => res.end("ok"));\n'
    "server.listen(3000);\n"
)


def _check(tmp_path: Path, files: dict[str, str], stack) -> list[str]:
    project = tmp_path / "app"
    project.mkdir()
    for name, body in files.items():
        (project / name).write_text(body, encoding="utf-8")
    return _a_server_in_a_browser_only_product(_source_files(tmp_path), tmp_path, stack)


def test_the_measured_server_is_reported(tmp_path: Path) -> None:
    (problem,) = _check(tmp_path, {"server.js": SERVER}, BROWSER)

    assert "starts an HTTP server" in problem
    assert "Web LocalStorage" in problem
    assert _severity_of(problem) == "BREAKS"


@pytest.mark.parametrize(
    "body",
    [
        'import express from "express";\nconst app = express();\napp.listen(3000);\n',
        "Deno.serve((req) => new Response('ok'));\n",
        "Bun.serve({ port: 3000, fetch: () => new Response('ok') });\n",
    ],
)
def test_the_other_ways_to_start_one(tmp_path: Path, body: str) -> None:
    assert _check(tmp_path, {"server.js": body}, BROWSER)


def test_a_product_with_a_real_database_is_left_alone(tmp_path: Path) -> None:
    """A server is what that stack is for; this must not say a word about it."""
    assert _check(tmp_path, {"server.js": SERVER}, SERVED) == []


def test_a_run_with_no_recorded_stack_is_left_alone(tmp_path: Path) -> None:
    assert _check(tmp_path, {"server.js": SERVER}, None) == []


def test_browser_code_is_not_a_server(tmp_path: Path) -> None:
    body = (
        "export function addTask(t) { localStorage.setItem('t', JSON.stringify(t)); }\n"
        "document.getElementById('form').addEventListener('submit', addTask);\n"
    )

    assert _check(tmp_path, {"app.js": body}, BROWSER) == []


def test_a_test_file_that_spins_one_up_is_not_the_product(tmp_path: Path) -> None:
    """A test may start a listener to exercise something; that is not a second
    data layer shipped with the product."""
    assert _check(tmp_path, {"app.test.mjs": SERVER}, BROWSER) == []


@pytest.mark.parametrize("database", ["localStorage", "IndexedDB", "sessionStorage", "Web Storage"])
def test_every_browser_storage_counts(tmp_path: Path, database: str) -> None:
    stack = SimpleNamespace(
        language="JavaScript", framework="Vanilla", database=database,
        testing_framework="node --test", additional_tools=[],
    )

    assert _check(tmp_path, {"server.js": SERVER}, stack)
