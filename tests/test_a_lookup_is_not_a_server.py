"""`which serve` asks where a server is. It does not start one.

`_starts_a_server` matches on the *argument* rather than the executable, on
purpose: these commands arrive as `npx serve` and `npx --yes serve`, never as
`serve` alone. The cost is that a server's name reads as a server wherever it
appears, including as the subject of a command that only looks things up.

Measured on the stored runs, both refused with "it runs until it is stopped, and
nothing here will stop it":

    which serve
    ls -la node_modules/serve

said about a path lookup and a directory listing. `grep serve package.json` and
`npx which serve` do the same.

`which serve` was live in run-1a0d3610's `test_round_1`, which was checking
whether the server binary it needed was installed - the refusal answered a
question about availability by describing a process lifetime.

This is the same shape as the install carve-out already in that function:
`npm install -D serve` names `serve` as a package to add, and was refused twice
on run-ed05e20e before that was fixed. A program that only inspects is the other
half.

`tail` is deliberately not on the list, because `tail -f` does run until it is
stopped.
"""

from __future__ import annotations

import pytest

from app.tools.sandbox import _ONLY_INSPECTS, _starts_a_server


class TestTheLookupsThatWereRefused:
    @pytest.mark.parametrize(
        "command",
        [
            ["which", "serve"],
            ["ls", "-la", "node_modules/serve"],
            ["grep", "serve", "package.json"],
            ["npx", "which", "serve"],
            ["find", ".", "-name", "serve"],
            ["type", "serve"],
            ["whereis", "serve"],
            ["stat", "node_modules/serve"],
            ["wc", "-l", "serve"],
            ["echo", "serve"],
            ["realpath", "node_modules/serve"],
        ],
    )
    def test_it_is_not_a_server(self, command):
        assert _starts_a_server(command) is None, command

    def test_a_delegating_runner_is_looked_past(self):
        """`npx which serve` runs `which`, and `which` cannot run forever."""
        assert _starts_a_server(["npx", "which", "serve"]) is None
        assert _starts_a_server(["npx", "--yes", "which", "serve"]) is None

    def test_the_inspectors_do_not_include_tail(self):
        """`tail -f` really does run until it is stopped."""
        assert "tail" not in _ONLY_INSPECTS
        assert _starts_a_server(["tail", "-f", "serve"]) == "serve"


class TestTheServersStillRefused:
    @pytest.mark.parametrize(
        "command,named",
        [
            (["npx", "serve", "todo-app", "-p", "3000"], "serve"),
            (["serve", "."], "serve"),
            (["npm", "run", "dev"], "dev"),
            (["python3", "-m", "http.server"], "http.server"),
        ],
    )
    def test_a_real_server_is_still_caught(self, command, named):
        assert _starts_a_server(command) == named

    def test_a_delegated_server_is_still_caught(self):
        """Looking past the runner must not look past a server behind it."""
        assert _starts_a_server(["npx", "vite", "dev"]) is not None

    def test_a_build_still_terminates(self):
        assert _starts_a_server(["vite", "build"]) is None

    def test_installing_a_server_is_still_not_running_one(self):
        """The carve-out this one is modelled on, and it must keep working."""
        assert _starts_a_server(["npm", "install", "-D", "serve"]) is None


class TestItDoesNotFallOver:
    def test_an_empty_command(self):
        assert _starts_a_server([]) is None

    def test_a_single_word(self):
        assert _starts_a_server(["ls"]) is None

    def test_only_flags(self):
        assert _starts_a_server(["-la"]) is None

    def test_an_absolute_path_to_an_inspector(self):
        """The basename is what identifies the program."""
        assert _starts_a_server(["/usr/bin/which", "serve"]) is None
