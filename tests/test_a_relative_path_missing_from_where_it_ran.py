"""A relative path reported missing is placed: where it was looked for, and where it is.

One run's `specialist_ui_ux_0` wrote `todo-list/validate.mjs` reading
`./style.css`, and ran it from the workspace root, then from `todo-list` with
the script still named from the root, then flipped the path between
`./style.css` and `todo-list/style.css` four times. ENOENT every time, about a
dozen calls, and no result named the directory the path was looked for in.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.sandbox import _a_relative_path_missing_from_where_it_ran as note

NODE_ENOENT = (
    "node:fs:448\n    return binding.readFileUtf8(path, stringToFlags(options.flag));\n\n"
    "Error: ENOENT: no such file or directory, open './style.css'\n"
    "    at readFileSync (node:fs:448:20)\n  code: 'ENOENT',\n  path: './style.css'\n}\n"
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "todo-list").mkdir()
    (tmp_path / "todo-list" / "style.css").write_text("body{}\n")
    (tmp_path / "todo-list" / "validate.mjs").write_text("x\n")
    return tmp_path


class TestTheMeasuredCase:
    def test_it_names_where_it_ran_and_where_the_file_is(self, workspace):
        message = note({"stderr": NODE_ENOENT, "returncode": "1"}, workspace, None)

        assert "the workspace root" in message
        assert "It is at 'todo-list/style.css'" in message
        assert "Run with working_directory 'todo-list'" in message

    def test_it_explains_what_a_relative_path_resolves_from(self, workspace):
        message = note({"stderr": NODE_ENOENT}, workspace, None)

        assert "resolves from the working directory, not from the file that names it" in message

    def test_a_script_named_from_the_wrong_place(self, workspace):
        stderr = "Error: Cannot find module 'validate.mjs'\n    at Module._resolveFilename\n"

        message = note({"stderr": stderr}, workspace, None)

        assert "It is at 'todo-list/validate.mjs'" in message

    def test_a_path_doubled_by_the_working_directory(self, workspace):
        stderr = "Error: ENOENT: no such file or directory, open 'todo-list/style.css'\n"

        message = note({"stderr": stderr}, workspace, "todo-list")

        assert "'todo-list'" in message
        assert "It is at 'todo-list/style.css'" in message
        assert "Run with no working_directory" in message


class TestOtherRuntimes:
    def test_python(self, workspace):
        stderr = "FileNotFoundError: [Errno 2] No such file or directory: 'style.css'\n"

        assert "It is at 'todo-list/style.css'" in note({"stderr": stderr}, workspace, None)

    def test_the_shell(self, workspace):
        stderr = "cat: style.css: No such file or directory\n"

        assert "It is at 'todo-list/style.css'" in note({"stderr": stderr}, workspace, None)


class TestItStaysQuiet:
    def test_a_file_that_is_where_it_was_looked_for(self, workspace):
        """Then something else is wrong, and this would mislead."""
        assert note({"stderr": NODE_ENOENT}, workspace, "todo-list") == ""

    def test_a_file_that_exists_nowhere(self, workspace):
        stderr = "Error: ENOENT: no such file or directory, open './missing.css'\n"

        assert note({"stderr": stderr}, workspace, None) == ""

    def test_two_candidates(self, workspace):
        (workspace / "other").mkdir()
        (workspace / "other" / "style.css").write_text("x\n")

        assert note({"stderr": NODE_ENOENT}, workspace, None) == ""

    def test_a_package_is_not_a_path(self, workspace):
        stderr = "Error: Cannot find module 'express'\n"

        assert note({"stderr": stderr}, workspace, None) == ""

    def test_nothing_printed(self, workspace):
        assert note({"stdout": "", "stderr": ""}, workspace, None) == ""

    def test_a_dependency_directory_is_not_offered(self, workspace):
        hidden = workspace / "todo-list" / "node_modules" / "pkg"
        hidden.mkdir(parents=True)
        (hidden / "theme.css").write_text("x\n")
        stderr = "Error: ENOENT: no such file or directory, open 'theme.css'\n"

        assert note({"stderr": stderr}, workspace, None) == ""


def test_it_is_attached_to_a_command_s_result():
    """Defined and called: a note nothing calls helps nobody."""
    import inspect

    from app.tools import sandbox

    assert inspect.getsource(sandbox).count("_a_relative_path_missing_from_where_it_ran(") == 2
