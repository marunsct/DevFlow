"""Asking a package manager about a package is not starting a server, whatever the package is called.

Measured on a gate run: `python -m pip show fastapi starlette` was refused
twice as a server that "runs until it is stopped" - `fastapi` is also the name
of a server command, and the check matched it as a word.
"""
from __future__ import annotations

import pytest

from app.tools.sandbox import _starts_a_server


@pytest.mark.parametrize("argv", [
    [".venv/bin/python", "-m", "pip", "show", "fastapi", "starlette"],
    ["cd", "tasks-api", ".venv/bin/python", "-m", "pip", "show", "uvicorn"],
    ["pip", "list"],
    ["npm", "ls", "serve"],
    ["npm", "view", "vite", "version"],
    ["cargo", "tree"],
])
def test_a_lookup_is_not_a_server(argv):
    assert _starts_a_server(argv) is None


@pytest.mark.parametrize("argv,server", [
    ([".venv/bin/python", "-m", "uvicorn", "app.main:app"], "uvicorn"),
    (["fastapi", "dev", "app/main.py"], "fastapi"),
    (["npx", "serve", "dist"], "serve"),
])
def test_a_server_is_still_a_server(argv, server):
    assert _starts_a_server(argv) == server
