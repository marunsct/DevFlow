"""`cd <dir> && ...` is dropped when <dir> is already the working directory.

Measured live on 2026-09-21, twice in one run, by two different roles::

    specialist_ui_ux_2   ["cd", "task-manager", "&&", "node", "--check", "app.js"]
                         working_directory: "task-manager"
    defect_fix_1_0       ["cd", "task-manager", "&&", "npx", "playwright", ...]
                         working_directory: "task-manager"

Both were refused with "`cd` is not a program. Pass `working_directory` to ..."
and both had already passed it, naming the directory the `cd` asks for. The
refusal is right about `cd` and useless about the situation: the agent did the
correct thing and belt-and-braced it, and paid a model call for the privilege.

Narrow on purpose. A `cd` to a *different* directory is a real disagreement
about where the command should run, and stays refused.
"""

from __future__ import annotations

import pytest

from app.tools.sandbox import strip_a_redundant_cd


class TestItDropsTheRedundantPrefix:
    def test_the_exact_case_from_the_run(self):
        argv, note = strip_a_redundant_cd(
            ["cd", "task-manager", "&&", "node", "--check", "app.js"], "task-manager"
        )
        assert argv == ["node", "--check", "app.js"]
        assert note and "task-manager" in note

    def test_a_longer_command_keeps_all_its_arguments(self):
        argv, _ = strip_a_redundant_cd(
            ["cd", "task-manager", "&&", "npx", "playwright", "test",
             "--reporter=line", "-g", "switching filters"],
            "task-manager",
        )
        assert argv == ["npx", "playwright", "test", "--reporter=line", "-g", "switching filters"]

    @pytest.mark.parametrize("target", ["task-manager", "task-manager/", "/task-manager"])
    def test_trailing_and_leading_slashes_still_match(self, target):
        argv, note = strip_a_redundant_cd(["cd", target, "&&", "npm", "test"], "task-manager")
        assert argv == ["npm", "test"] and note

    @pytest.mark.parametrize("here", ["task-manager", "task-manager/"])
    def test_the_working_directory_may_be_spelled_either_way(self, here):
        argv, note = strip_a_redundant_cd(["cd", "task-manager", "&&", "npm", "test"], here)
        assert argv == ["npm", "test"] and note

    def test_cd_dot_is_redundant_wherever_it_is(self):
        argv, note = strip_a_redundant_cd(["cd", ".", "&&", "npm", "test"], "task-manager")
        assert argv == ["npm", "test"] and note

    def test_the_note_says_what_happened_and_why(self):
        _, note = strip_a_redundant_cd(
            ["cd", "task-manager", "&&", "npm", "test"], "task-manager"
        )
        assert "working_directory is already" in note
        assert "no shell here" in note


class TestItLeavesEverythingElseAlone:
    def test_a_cd_somewhere_else_is_not_touched(self):
        """A real disagreement about where to run; guessing would be clever, not safe."""
        argv, note = strip_a_redundant_cd(
            ["cd", "other-project", "&&", "npm", "test"], "task-manager"
        )
        assert argv == ["cd", "other-project", "&&", "npm", "test"]
        assert note is None

    def test_a_cd_with_no_working_directory_is_not_touched(self):
        argv, note = strip_a_redundant_cd(["cd", "task-manager", "&&", "npm", "test"], None)
        assert argv[0] == "cd" and note is None

    def test_a_bare_cd_is_not_touched(self):
        """Nothing to run after it, so there is nothing to rewrite to."""
        argv, note = strip_a_redundant_cd(["cd", "task-manager"], "task-manager")
        assert argv == ["cd", "task-manager"] and note is None

    def test_a_cd_without_the_operator_is_not_touched(self):
        argv, note = strip_a_redundant_cd(
            ["cd", "task-manager", "npm", "test"], "task-manager"
        )
        assert argv[0] == "cd" and note is None

    def test_an_ordinary_command_passes_through(self):
        argv, note = strip_a_redundant_cd(["npm", "test"], "task-manager")
        assert argv == ["npm", "test"] and note is None

    def test_an_empty_command_is_not_a_crash(self):
        argv, note = strip_a_redundant_cd([], "task-manager")
        assert argv == [] and note is None

    def test_a_string_command_is_handed_on_whole(self):
        """`list()` on a string splits it into characters.

        The refusal downstream would then name a one-letter executable instead
        of explaining that commands must be lists. The neighbouring
        `strip_a_doubled_working_directory` carries this guard and documents
        exactly this failure; the first version of this function omitted it and
        `test_a_command_string_is_still_refused` caught it.
        """
        command, note = strip_a_redundant_cd("cd task-manager && npm test", "task-manager")
        assert command == "cd task-manager && npm test"
        assert note is None


class TestItIsWiredBeforeValidation:
    def test_the_executor_strips_before_it_validates(self):
        """After validation the command has already been refused."""
        import inspect

        from app.tools import sandbox

        source = inspect.getsource(sandbox)
        strip = source.index("command, redundant_cd = strip_a_redundant_cd(")
        run = source.index("outcome = cls._run(")
        assert strip < run

    def test_the_note_reaches_the_agent(self):
        import inspect

        from app.tools import sandbox

        source = inspect.getsource(sandbox)
        assert "notes = [n for n in (redundant_cd, doubled, redirected) if n]" in source
