"""`python -m pip install fastapi uvicorn[standard]` is an install, not a server.

Measured live: `["python3", "-m", "pip", "install", "fastapi", "uvicorn[standard]",
"pydantic[email]", ...]` was refused twice as "it runs until it is stopped, and
nothing here will stop it". The install carve-out knew `pip install` but not pip
driven as a module, and the module check took any server module after `-m` for
the one being run.
"""
from __future__ import annotations

import pytest

from app.tools.sandbox import _a_package_this_command_would_add, _starts_a_server


@pytest.mark.parametrize("argv", [
    ["python3", "-m", "pip", "install", "fastapi", "uvicorn[standard]", "pydantic[email]"],
    [".venv/bin/python", "-m", "pip", "install", "uvicorn"],
    ["python", "-m", "pip", "install", "flask", "gunicorn"],
])
def test_installing_through_pip_as_a_module_is_not_a_server(argv):
    assert _starts_a_server(argv) is None
    assert _a_package_this_command_would_add(argv)


@pytest.mark.parametrize("argv, server", [
    (["python", "-m", "uvicorn", "app:app"], "uvicorn"),
    ([".venv/bin/python", "-m", "http.server", "8000"], "http.server"),
    (["uvicorn", "app.main:app", "--reload"], "uvicorn"),
])
def test_running_a_server_is_still_one(argv, server):
    assert _starts_a_server(argv) == server
