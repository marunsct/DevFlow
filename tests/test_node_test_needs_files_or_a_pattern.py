"""`node --test` given a directory runs nothing on the Node the image runs.

Measured in the run image on Node 24.21: `node --test ./` stops at "Could not
find './'", and `node --test tests/` loads the directory as a module and
reports one failed test, ERR_UNSUPPORTED_DIR_IMPORT - none of the suite's own
tests run. Node 20 searched the directory, and the harness's own JavaScript
packs named `tests/` until the image moved to Node 24, when each of them
failed its smoke test exactly that way. The command can never work, so it is
refused with the form that does: the files, or a pattern Node expands itself.
"""

from __future__ import annotations

import pytest

from app.tools.sandbox import CommandNotAllowed, validate_command


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / ".project-directory").write_text("app\n")
    (tmp_path / "app" / "tests").mkdir(parents=True)
    (tmp_path / "app" / "spec").mkdir()
    (tmp_path / "app" / "tests" / "a.test.js").write_text("")
    return tmp_path


@pytest.mark.parametrize("directory, pattern", [
    ("tests/", "tests/**/*.test.js"),
    ("./tests/", "tests/**/*.test.js"),
    ("./", "**/*.test.js"),
    (".", "**/*.test.js"),
    ("tests", "tests/**/*.test.js"),
])
def test_a_directory_is_refused_with_a_pattern_in_its_place(workspace, directory, pattern):
    with pytest.raises(CommandNotAllowed) as refused:
        validate_command(["node", "--test", directory], "testing_specialist", workspace)

    message = str(refused.value)
    assert "ERR_UNSUPPORTED_DIR_IMPORT" in message
    assert repr(["node", "--test", pattern]) in message
    assert f"node --test '{pattern}'" in message, "a package.json script needs the pattern quoted"


def test_the_flags_before_it_are_kept_in_the_command_it_gives(workspace):
    argv = ["node", "--import", "./test-setup.mjs", "--test", "tests/"]

    with pytest.raises(CommandNotAllowed) as refused:
        validate_command(argv, "testing_specialist", workspace)

    assert repr(["node", "--import", "./test-setup.mjs", "--test", "tests/**/*.test.js"]) in str(refused.value)


@pytest.mark.parametrize("argv", [
    ["node", "--test"],
    ["node", "--test", "tests/a.test.js"],
    ["node", "--test", "tests/**/*.test.js"],
    ["node", "--test", "tests/**/{test,test-*,*[._-]test}.{js,mjs,cjs}"],
    ["node", "--test", "--test-reporter", "spec", "tests/a.test.js"],
    ["node", "--test", "--test-name-pattern", "tests", "tests/a.test.js"],
    ["node", "tests/a.test.js"],
])
def test_files_patterns_and_flag_values_run(workspace, argv):
    """`spec` is a directory in the project, and here it is only a reporter's name."""
    assert validate_command(argv, "testing_specialist", workspace) == argv
