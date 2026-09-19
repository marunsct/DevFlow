"""A long-running server must be recognised in every ecosystem, not just one.

`_SERVER_COMMANDS` held seven names, all JavaScript, plus two Python modules.
Every other way of starting a server - `rails server`, `flask run`,
`uvicorn`, `dotnet run`, `php -S`, `mix phx.server`, `ng serve` - ran until
the timeout and returned nothing, and the agent then retried it. That is the
pattern that cost run-e9e7f48f.

The timeout scaling added the same day made it cost more: on a Rust or Java
stack an undetected server now waits several times as long before the harness
says anything. A fix in one place made an old gap more expensive, which is
worth recording on its own.
"""

from __future__ import annotations

import pytest

from app.tools.sandbox import _starts_a_server

SERVERS = [
    ["rails", "server"],
    ["bundle", "exec", "rails", "s"],
    ["flask", "run"],
    ["python3", "-m", "uvicorn", "main:app"],
    ["python3", "-m", "http.server"],
    ["gunicorn", "app:app"],
    ["dotnet", "run"],
    ["dotnet", "watch"],
    ["php", "-S", "localhost:8000"],
    ["mix", "phx.server"],
    ["ng", "serve"],
    ["npm", "start"],
    ["npm", "run", "dev"],
    ["npx", "serve"],
    ["vite"],
    ["nodemon", "server.js"],
    ["python3", "manage.py", "runserver"],
    ["deno", "task", "dev"],
]

NOT_SERVERS = [
    ["npm", "test"],
    ["npm", "install"],
    ["npm", "run", "build"],
    ["go", "build"],
    ["go", "test", "./..."],
    ["vite", "build"],
    ["node", "--test"],
    ["pytest", "-q"],
    ["cargo", "build"],
    ["cargo", "test"],
    ["dotnet", "build"],
    ["python3", "app.py"],
    ["git", "status"],
    ["ls", "-la"],
    ["webpack-dev-server", "--help"],
]


@pytest.mark.parametrize("command", SERVERS, ids=lambda c: " ".join(c)[:28])
def test_a_server_is_recognised(command):
    assert _starts_a_server(command), (
        f"`{' '.join(command)}` runs until the timeout and returns nothing"
    )


@pytest.mark.parametrize("command", NOT_SERVERS, ids=lambda c: " ".join(c)[:28])
def test_a_command_that_terminates_is_not_called_a_server(command):
    assert _starts_a_server(command) is None, (
        f"`{' '.join(command)}` finishes on its own and must be allowed to run"
    )


def test_a_generic_word_alone_is_not_a_server():
    """`dev`, `start` and `watch` only count behind a runner that has them."""
    assert _starts_a_server(["start"]) is None
    assert _starts_a_server(["./dev"]) is None
    assert _starts_a_server(["npm", "start"])


def test_a_module_name_counts_only_behind_dash_m():
    """`uvicorn` as a bare word is the executable; as `-m uvicorn` it is a module."""
    assert _starts_a_server(["python3", "-m", "uvicorn", "app:app"])
    # A file that merely happens to be called `flask.py` is not a server.
    assert _starts_a_server(["python3", "somewhere/gunicorn_config.py"]) is None


def test_every_language_the_stack_can_choose_has_a_server_form():
    """The set rule: a stack whose server nothing recognises hangs silently."""
    from app.tools.sandbox import _SERVER_COMMANDS, _SERVER_SUBCOMMANDS

    known = _SERVER_COMMANDS | set(_SERVER_SUBCOMMANDS)
    for expected in ("rails", "flask", "uvicorn", "dotnet", "php", "mix", "ng", "vite"):
        assert expected in known, f"no way to recognise a {expected} server"
