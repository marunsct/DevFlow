"""The doubled-directory guard could not decide a command that creates the path.

`strip_a_doubled_working_directory` drops a project directory an argument repeats
from `working_directory`, and rewrites "only when the path as given does NOT
exist and the stripped one DOES". That rule is what makes it safe: a project that
genuinely contains a directory of its own name resolves as written.

It cannot decide a command that *creates* the path, because then neither version
exists yet - and such a command succeeds, so no failure and no location hint ever
follows it.

Measured live on one run:

    06:29:00  test_round_0  wd='task-manager'  mkdir -p task-manager/e2e

which made `task-manager/task-manager/e2e`, an empty directory still in the
shipped workspace. The stage then wrote `task-manager/e2e/todo.spec.ts` -
`write_artifact` paths are workspace-relative - so the file landed in the right
place, the run carried a stray directory, and two later `ls /task-manager/e2e`
calls were answered with a hint pointing at the doubled path.

Across the 27 current-generation runs, 42 commands name a path repeating their
working directory. Most fail, and the existing failure hint names where the file
really is. These are the ones that silently succeed.
"""

from __future__ import annotations

import pytest

from app.tools.sandbox import strip_a_doubled_working_directory


@pytest.fixture
def a_project(tmp_path):
    (tmp_path / "task-manager").mkdir()
    return tmp_path


class TestTheCommandThatMadeTheStrayDirectory:
    def test_the_prefix_is_dropped(self, a_project):
        command, _ = strip_a_doubled_working_directory(
            ["mkdir", "-p", "task-manager/e2e"], str(a_project), "task-manager"
        )

        assert command == ["mkdir", "-p", "e2e"]

    def test_the_note_says_why(self, a_project):
        _, note = strip_a_doubled_working_directory(
            ["mkdir", "-p", "task-manager/e2e"], str(a_project), "task-manager"
        )

        assert "this command creates the path" in note
        assert "task-manager/task-manager/" in note

    def test_the_note_names_the_working_directory(self, a_project):
        _, note = strip_a_doubled_working_directory(
            ["mkdir", "-p", "task-manager/e2e"], str(a_project), "task-manager"
        )

        assert "the working directory is already 'task-manager'" in note

    @pytest.mark.parametrize(
        "argument", ["task-manager/e2e", "./task-manager/e2e", "/task-manager/e2e"]
    )
    def test_every_spelling_of_the_prefix(self, a_project, argument):
        command, _ = strip_a_doubled_working_directory(
            ["mkdir", "-p", argument], str(a_project), "task-manager"
        )

        assert command == ["mkdir", "-p", "e2e"]

    def test_install_d_is_the_same_intent(self, a_project):
        """`install -d` makes a directory too, spelled differently."""
        command, _ = strip_a_doubled_working_directory(
            ["install", "-d", "task-manager/e2e"], str(a_project), "task-manager"
        )

        assert command == ["install", "-d", "e2e"]

    def test_a_nested_path_keeps_its_tail(self, a_project):
        command, _ = strip_a_doubled_working_directory(
            ["mkdir", "-p", "task-manager/tests/e2e/fixtures"],
            str(a_project),
            "task-manager",
        )

        assert command == ["mkdir", "-p", "tests/e2e/fixtures"]


class TestWhatMustNotChange:
    def test_a_reading_command_is_left_alone_when_neither_path_exists(self, a_project):
        """The original rule: it cannot tell, so it does not guess.

        The failure that follows is answered by
        `_where_the_files_it_named_actually_are`, which names where the file is.
        """
        command, note = strip_a_doubled_working_directory(
            ["node", "--test", "task-manager/app.test.mjs"],
            str(a_project),
            "task-manager",
        )

        assert command == ["node", "--test", "task-manager/app.test.mjs"]
        assert note is None

    def test_the_original_rule_still_fires(self, a_project):
        """Path as given absent, stripped one present - unchanged behaviour."""
        (a_project / "task-manager" / "app.test.mjs").write_text("x")

        command, note = strip_a_doubled_working_directory(
            ["node", "--test", "task-manager/app.test.mjs"],
            str(a_project),
            "task-manager",
        )

        assert command == ["node", "--test", "app.test.mjs"]
        assert "the shortened one does" in note

    def test_a_path_that_does_not_repeat_the_directory(self, a_project):
        command, note = strip_a_doubled_working_directory(
            ["mkdir", "-p", "src/components"], str(a_project), "task-manager"
        )

        assert command == ["mkdir", "-p", "src/components"]
        assert note is None

    def test_no_working_directory_means_no_prefix_to_repeat(self, a_project):
        command, note = strip_a_doubled_working_directory(
            ["mkdir", "-p", "task-manager/e2e"], str(a_project), None
        )

        assert command == ["mkdir", "-p", "task-manager/e2e"]
        assert note is None

    def test_a_genuine_directory_of_the_same_name_is_respected(self, a_project):
        """`X/X` really existing is the case the original rule protects."""
        (a_project / "task-manager" / "task-manager").mkdir()

        command, note = strip_a_doubled_working_directory(
            ["mkdir", "-p", "task-manager/e2e"], str(a_project), "task-manager"
        )

        assert command == ["mkdir", "-p", "task-manager/e2e"]
        assert note is None

    def test_the_program_name_is_never_rewritten(self, a_project):
        """argv[0] is a program, not a path, even if it looks like one."""
        command, _ = strip_a_doubled_working_directory(
            ["mkdir", "task-manager/e2e"], str(a_project), "task-manager"
        )

        assert command[0] == "mkdir"

    def test_a_string_command_is_returned_untouched(self, a_project):
        """A string is refused downstream with a message that says so."""
        command, note = strip_a_doubled_working_directory(
            "mkdir -p task-manager/e2e", str(a_project), "task-manager"
        )

        assert command == "mkdir -p task-manager/e2e"
        assert note is None

    def test_an_unreadable_workspace_does_not_raise(self, tmp_path):
        command, _ = strip_a_doubled_working_directory(
            ["mkdir", "-p", "task-manager/e2e"], str(tmp_path / "gone"), "task-manager"
        )

        assert command[0] == "mkdir"


class TestItIsNotAboutAnyOneStack:
    @pytest.mark.parametrize(
        "project,made",
        [
            ("todo-app", "e2e"),
            ("my_service", "migrations"),
            ("backend", "internal/store"),
            ("crate-name", "benches"),
        ],
    )
    def test_any_project_name(self, tmp_path, project, made):
        (tmp_path / project).mkdir()

        command, _ = strip_a_doubled_working_directory(
            ["mkdir", "-p", f"{project}/{made}"], str(tmp_path), project
        )

        assert command == ["mkdir", "-p", made]
