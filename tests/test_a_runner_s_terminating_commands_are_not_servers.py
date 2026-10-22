"""A program that is a server only with one subcommand runs its others.

`_SERVER_SUBCOMMANDS` says `rails` is a server with `server` or `s`, `ng` with
`serve`, `flask` with `run` - and the word list that follows caught each by its
name alone, so `rails test`, `ng test` and `flask db upgrade` were refused as
servers that "run until they are stopped". Measured when the Rails pack was
scaffolded: its own unit test command, `bundle exec rails test`, was refused
twice and the scaffold could not be proven.
"""

from __future__ import annotations

import pytest

from app.tools.sandbox import _starts_a_server


@pytest.mark.parametrize("argv", [
    ["bundle", "exec", "rails", "test"],
    ["bundle", "exec", "rails", "db:migrate"],
    ["bundle", "exec", "rails", "generate", "model", "Item", "title:string"],
    ["rails"],
    ["ng", "test"],
    ["ng", "build"],
    ["flask", "--app", "shop.app", "routes"],
    ["python", "manage.py", "migrate"],
])
def test_a_command_that_finishes_is_run(argv):
    assert _starts_a_server(argv) is None


@pytest.mark.parametrize("argv, server", [
    (["bundle", "exec", "rails", "server"], "rails server"),
    (["rails", "s"], "rails s"),
    (["ng", "serve"], "ng serve"),
    (["flask", "run"], "flask run"),
    (["python", "manage.py", "runserver"], "manage.py runserver"),
    (["npx", "vite"], "vite"),
    (["npm", "start"], "npm start"),
])
def test_a_server_is_still_refused(argv, server):
    assert _starts_a_server(argv) == server
