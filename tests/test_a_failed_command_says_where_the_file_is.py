"""A command that cannot find a file must be told where the file is.

The harness already counts repeats and says so. What it said was advice about
the command, when the problem was the directory the command ran in - and the
workspace could answer that at the first failure.

Measured live on one run's `specialist_ui_ux_4`, five calls in 36 seconds:

    09:00:16  node --test main.test.js storage.test.js  wd=(none)      exit 1
    09:00:19  node --test main.test.js storage.test.js  wd=the project exit 1
    09:00:38  node --test main.test.js                  wd=(none)      exit 1
    09:00:44  node --test main.test.js                  wd=(none)      exit 1
    09:00:52  node --test main.test.js                  wd=(none)      exit 1

Every wd-less call answered `Could not find 'main.test.js'`. The repeat note
fired correctly on the last two - "already failed 1 time(s) ... change the
command, or change the file it runs" - and both of those moves are wrong: the
command was right and the file was fine. `main.test.js` was in the project
directory, which the 09:00:19 call had already used.

Read off the command's own arguments rather than the runner's error text, so no
runner is special: `node --test x.test.js`, `pytest tests/x.py`,
`go test ./x_test.go` and `javac Main.java` all name what they were looking for
the same way, as an argument.
"""

from __future__ import annotations

import pytest

from app.tools import sandbox
from app.tools.sandbox import (
    MAX_PLACES_NAMED,
    _where_the_files_it_named_actually_are,
)


@pytest.fixture
def a_workspace(tmp_path):
    """One run's shape: tests inside a project directory, one level down."""
    project = tmp_path / "simple-to-do-list-app"
    project.mkdir()
    (project / "main.test.js").write_text("// tests\n")
    (project / "storage.test.js").write_text("// tests\n")
    (project / "main.js").write_text("export const x = 1;\n")
    return tmp_path


class TestNamingWhereItIs:
    def test_the_call_that_wasted_four_retries(self, a_workspace):
        note = _where_the_files_it_named_actually_are(
            str(a_workspace), ["node", "--test", "main.test.js"], None
        )

        assert "simple-to-do-list-app/main.test.js" in note

    def test_every_missing_file_is_named_not_only_the_first(self, a_workspace):
        """The first call named two files and neither was found."""
        note = _where_the_files_it_named_actually_are(
            str(a_workspace),
            ["node", "--test", "main.test.js", "storage.test.js"],
            None,
        )

        assert "main.test.js" in note
        assert "storage.test.js" in note

    def test_it_says_what_to_do_about_it(self, a_workspace):
        note = _where_the_files_it_named_actually_are(
            str(a_workspace), ["node", "--test", "main.test.js"], None
        )

        assert "working_directory" in note

    @pytest.mark.parametrize("command", [
        ["pytest", "main.test.js"],
        ["go", "test", "main.test.js"],
        ["ruby", "main.test.js"],
        ["deno", "test", "main.test.js"],
    ])
    def test_no_runner_is_special(self, a_workspace, command):
        """The argument is the evidence, so every runner gets the same answer."""
        note = _where_the_files_it_named_actually_are(str(a_workspace), command, None)

        assert "simple-to-do-list-app/main.test.js" in note


class TestSayingNothing:
    def test_silent_when_the_file_is_where_the_command_ran(self, a_workspace):
        """The 09:00:19 call. It failed on test content, which is not this."""
        assert _where_the_files_it_named_actually_are(
            str(a_workspace),
            ["node", "--test", "main.test.js"],
            "simple-to-do-list-app",
        ) == ""

    def test_silent_when_the_command_names_no_file(self, a_workspace):
        assert _where_the_files_it_named_actually_are(
            str(a_workspace), ["npm", "test"], None
        ) == ""

    def test_a_flag_is_not_a_path(self, a_workspace):
        """`--reporter=line` and `-v` end in something that looks like a suffix."""
        assert _where_the_files_it_named_actually_are(
            str(a_workspace), ["npm", "test", "--reporter=line", "-v"], None
        ) == ""

    def test_silent_when_the_file_is_nowhere_at_all(self, a_workspace):
        """A genuinely missing file is a real failure, and saying nothing is right.

        Inventing a location would be worse than the generic advice this
        replaces.
        """
        assert _where_the_files_it_named_actually_are(
            str(a_workspace), ["node", "--test", "nothing-wrote-this.js"], None
        ) == ""

    def test_the_executable_is_not_searched_for(self, tmp_path):
        """`./build.sh` as argv[0] is the thing being run, not a thing it wants."""
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "build.sh").write_text("#!/bin/sh\n")

        assert _where_the_files_it_named_actually_are(
            str(tmp_path), ["build.sh"], None
        ) == ""

    def test_an_unreadable_workspace_says_nothing_rather_than_raising(self):
        """This runs while a command is already failing."""
        assert _where_the_files_it_named_actually_are(
            "/definitely/not/a/directory", ["node", "--test", "x.js"], None
        ) == ""


class TestWhereItLooks:
    def test_dependencies_are_not_offered_as_the_answer(self, a_workspace):
        """`node_modules` holds thousands of files with ordinary names.

        A note pointing an agent into its own dependencies is worse than no
        note, and walking that tree on every failure is the cost the pruning
        exists to avoid.
        """
        modules = a_workspace / "node_modules" / "some-package"
        modules.mkdir(parents=True)
        (modules / "index.test.js").write_text("// theirs\n")

        assert _where_the_files_it_named_actually_are(
            str(a_workspace), ["node", "--test", "index.test.js"], None
        ) == ""

    def test_runner_output_is_not_offered_as_the_answer(self, a_workspace):
        """A copy inside `test-results/` is a report, not the test."""
        results = a_workspace / "test-results"
        results.mkdir()
        (results / "report.test.js").write_text("// a copy\n")

        assert _where_the_files_it_named_actually_are(
            str(a_workspace), ["node", "--test", "report.test.js"], None
        ) == ""

    def test_the_number_of_places_named_is_capped(self, tmp_path):
        for index in range(MAX_PLACES_NAMED + 4):
            directory = tmp_path / f"copy{index}"
            directory.mkdir()
            (directory / "app.test.js").write_text("// one of many\n")

        note = _where_the_files_it_named_actually_are(
            str(tmp_path), ["node", "--test", "app.test.js"], None
        )

        assert note.count("app.test.js") == MAX_PLACES_NAMED + 1, note


class TestReachingTheAgent:
    def test_the_note_is_attached_to_a_failed_command(self, a_workspace, monkeypatch):
        """End to end: the agent has to actually receive it.

        On the first failure, not the third. The repeat note is where a wasted
        call is noticed and the most expensive place to learn the answer.
        """
        monkeypatch.setattr(sandbox, "execution_enabled", lambda: True)
        monkeypatch.setattr(sandbox.SandboxExecutor, "_run", staticmethod(
            lambda *args, **kwargs: {
                "stdout": "", "stderr": "Could not find 'main.test.js'\n",
                "returncode": "1",
            }
        ))

        result = sandbox.SandboxExecutor.execute(
            ["node", "--test", "main.test.js"], str(a_workspace),
            role_name="testing", category="test",
        )

        assert "simple-to-do-list-app/main.test.js" in result.get("note", "")

    def test_a_command_that_succeeded_gets_no_such_note(self, a_workspace, monkeypatch):
        """Only a failure is evidence that something was not found."""
        monkeypatch.setattr(sandbox, "execution_enabled", lambda: True)
        monkeypatch.setattr(sandbox.SandboxExecutor, "_run", staticmethod(
            lambda *args, **kwargs: {"stdout": "ok", "stderr": "", "returncode": "0"}
        ))

        result = sandbox.SandboxExecutor.execute(
            ["node", "--test", "main.test.js"], str(a_workspace),
            role_name="testing", category="test",
        )

        assert "is not in the directory this ran in" not in result.get("note", "")
