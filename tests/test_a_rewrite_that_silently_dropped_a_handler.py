"""Nothing compared a whole-file write against the file it replaces.

A rewrite that dropped a function removed it silently - no note, no refusal - and
the next stage to look found the behaviour missing with no record of where it went.
In parallel mode that is not hypothetical: six specialists were writing one
`app.js` in run-f05d8d47, and 17 of 25 stored sprint plans assign one file to
more than one specialist.

Measured on run-6e50b630, which failed at the milestone revision limit. Its
`todo-app/app.js`, by successful whole-file write, paired strictly by
`tool_call_id` (1,098 calls, none unpaired):

    16:42:39  specialist_ui_ux_1     4748B  18 definitions
    16:53:43  defect_fix_1_0         6906B  28
    16:59:45  defect_fix_1_2         8101B  33
    21:26:29  specialist_backend_0   5322B  28   deleteTask, handleTaskActions gone

2,779 bytes and five definitions removed by one write from a different stage,
among them `handleTaskActions` - the event-delegation handler - and `deleteTask`.
The reviewer then reported, three times until the run died:

    [blocking] correctness: Checkbox toggle handler is missing from init()'s
    event delegation block ... clicking them has no effect
    [blocking] correctness: Filter functionality is entirely missing despite UI
    elements existing

Two rungs, as elsewhere in this module: the loss is named on the first write and
the second is refused. A rewrite that drops a definition is sometimes a deliberate
refactor, and twice is enough to show it was not a slip.
"""

from __future__ import annotations

import pytest

from app.tools.repository import (
    LOSSES_BEFORE_REFUSING_A_REWRITE,
    RepositoryToolError,
    _what_a_file_defines,
    write_approved_artifact,
)

#: run-6e50b630's shape, reduced to the definitions that disappeared.
WITH_THE_HANDLERS = """export function loadTasks() { return []; }
export function saveTasks(tasks) { return tasks; }
export function deleteTask(id) { return id; }
export function handleTaskActions(event) { return event; }
export function init() { return 1; }
"""

WITHOUT_THEM = """export function loadTasks() { return []; }
export function saveTasks(tasks) { return tasks; }
export function init() { return 1; }
"""


@pytest.fixture(autouse=True)
def a_clean_tally():
    from app.agents import stage_memory
    from app.tools import repository

    stage_memory.forget_everything()
    repository._LOSSES_OUTSIDE_A_RUN.clear()
    yield
    stage_memory.forget_everything()
    repository._LOSSES_OUTSIDE_A_RUN.clear()


@pytest.fixture
def a_project(tmp_path):
    (tmp_path / "todo-app").mkdir()
    write_approved_artifact(str(tmp_path), "todo-app/app.js", WITH_THE_HANDLERS)
    return tmp_path


class TestTheWriteThatCostRun6e50b630:
    def test_the_lost_handlers_are_named(self, a_project):
        result = write_approved_artifact(str(a_project), "todo-app/app.js", WITHOUT_THEM)

        note = result.get("note") or ""
        assert "`deleteTask`" in note
        assert "`handleTaskActions`" in note

    def test_it_says_another_task_may_own_it(self, a_project):
        """Which is the case parallel mode creates and nothing else mentions."""
        result = write_approved_artifact(str(a_project), "todo-app/app.js", WITHOUT_THEM)

        assert "another task may own that code" in (result.get("note") or "")

    def test_it_says_nothing_else_will_report_it(self, a_project):
        result = write_approved_artifact(str(a_project), "todo-app/app.js", WITHOUT_THEM)

        assert "Nothing else in this pipeline will tell you it is gone" in (
            result.get("note") or ""
        )

    def test_the_write_still_lands(self, a_project):
        """The first one is a note, not a refusal: a refactor must be possible."""
        result = write_approved_artifact(str(a_project), "todo-app/app.js", WITHOUT_THEM)

        assert result["status"] == "written"
        assert "deleteTask" not in (a_project / "todo-app" / "app.js").read_text()

    def test_a_second_such_rewrite_is_refused(self, a_project):
        write_approved_artifact(str(a_project), "todo-app/app.js", WITHOUT_THEM)
        write_approved_artifact(str(a_project), "todo-app/app.js", WITH_THE_HANDLERS)

        with pytest.raises(RepositoryToolError) as raised:
            write_approved_artifact(str(a_project), "todo-app/app.js", WITHOUT_THEM)

        assert "Refusing to write" in str(raised.value)
        assert "`deleteTask`" in str(raised.value)

    def test_the_refusal_offers_a_targeted_change(self, a_project):
        write_approved_artifact(str(a_project), "todo-app/app.js", WITHOUT_THEM)
        write_approved_artifact(str(a_project), "todo-app/app.js", WITH_THE_HANDLERS)

        with pytest.raises(RepositoryToolError) as raised:
            write_approved_artifact(str(a_project), "todo-app/app.js", WITHOUT_THEM)

        assert "`edit_artifact`" in str(raised.value)
        assert "structured response" in str(raised.value)

    def test_the_refused_write_does_not_land(self, a_project):
        write_approved_artifact(str(a_project), "todo-app/app.js", WITHOUT_THEM)
        write_approved_artifact(str(a_project), "todo-app/app.js", WITH_THE_HANDLERS)

        with pytest.raises(RepositoryToolError):
            write_approved_artifact(str(a_project), "todo-app/app.js", WITHOUT_THEM)

        assert "deleteTask" in (a_project / "todo-app" / "app.js").read_text()

    def test_the_threshold_is_two(self):
        assert LOSSES_BEFORE_REFUSING_A_REWRITE == 2


class TestWhatMustStaySilent:
    def test_a_rewrite_that_adds_is_silent(self, a_project):
        more = WITH_THE_HANDLERS + "export function editTask(id) { return id; }\n"

        result = write_approved_artifact(str(a_project), "todo-app/app.js", more)

        assert "removes" not in (result.get("note") or "")

    def test_a_rewrite_that_keeps_everything_is_silent(self, a_project):
        reordered = "\n".join(reversed(WITH_THE_HANDLERS.strip().splitlines())) + "\n"

        result = write_approved_artifact(str(a_project), "todo-app/app.js", reordered)

        assert "removes" not in (result.get("note") or "")

    def test_a_new_file_is_silent(self, tmp_path):
        (tmp_path / "todo-app").mkdir()

        result = write_approved_artifact(
            str(tmp_path), "todo-app/app.js", WITHOUT_THEM
        )

        assert "removes" not in (result.get("note") or "")

    def test_an_empty_file_being_filled_is_silent(self, tmp_path):
        (tmp_path / "todo-app").mkdir()
        write_approved_artifact(str(tmp_path), "todo-app/app.js", "\n")

        result = write_approved_artifact(
            str(tmp_path), "todo-app/app.js", WITHOUT_THEM
        )

        assert "removes" not in (result.get("note") or "")

    def test_a_prose_file_is_silent(self, tmp_path):
        """A rewritten README defines nothing, and nothing is lost by rewriting it."""
        (tmp_path / "todo-app").mkdir()
        write_approved_artifact(str(tmp_path), "todo-app/NOTES.md", "# A\n\nsome text\n")

        result = write_approved_artifact(
            str(tmp_path), "todo-app/NOTES.md", "# B\n\nother text\n"
        )

        assert "removes" not in (result.get("note") or "")

    def test_a_different_file_has_its_own_tally(self, a_project):
        """The count is per file, so one rewrite does not arm another file's refusal."""
        write_approved_artifact(str(a_project), "todo-app/app.js", WITHOUT_THEM)
        write_approved_artifact(str(a_project), "todo-app/other.js", WITH_THE_HANDLERS)

        result = write_approved_artifact(
            str(a_project), "todo-app/other.js", WITHOUT_THEM
        )

        assert result["status"] == "written"


class TestWhatCountsAsADefinition:
    @pytest.mark.parametrize(
        "source,expected",
        [
            ("export function alpha() {}", "alpha"),
            ("async function beta() {}", "beta"),
            ("export const gamma = () => {};", "gamma"),
            ("let delta = 1;", "delta"),
            ("export class Epsilon {}", "Epsilon"),
            ("def zeta():\n    pass", "zeta"),
            ("pub fn eta() {}", "eta"),
            ("func theta() {}", "theta"),
        ],
    )
    def test_every_language_shape(self, source, expected):
        assert expected in _what_a_file_defines(source)

    def test_a_nested_definition_counts(self):
        """Deliberately, and the failure it was written for is why.

        run-6e50b630's blocking finding was "Checkbox toggle handler is missing
        from init()'s event delegation block" - the handlers live *inside*
        `init()`, so a reading that only saw the file's top level would have
        missed exactly the definitions that disappeared.

        The cost is that inlining a helper reads as a loss. That earns a note on
        the first write, which is the right weight for it.
        """
        assert "inner" in _what_a_file_defines(
            "function outer() {\n    function inner() {}\n}"
        )

    def test_a_commented_out_definition_is_not_one(self):
        """The patterns need the keyword first on the line, so `//` blocks them.

        Which is right: a file that only mentions a function in a comment does
        not define it, and a rewrite that removes the comment removes nothing.
        """
        assert _what_a_file_defines("// function ghost() {}\n") == set()
        assert _what_a_file_defines("  // function ghost() {}\n") == set()

    def test_nothing_is_defined_in_prose(self):
        assert _what_a_file_defines("# Title\n\nSome prose about functions.\n") == set()


class TestItNamesWhoHadIt:
    def test_the_note_can_name_the_writing_stage(self, a_project, monkeypatch):
        """In parallel mode "another task" is more useful as a name."""
        from app.analysis import project_memory

        monkeypatch.setattr(
            project_memory, "who_changed", lambda root, path: "specialist_testing_4"
        )

        result = write_approved_artifact(str(a_project), "todo-app/app.js", WITHOUT_THEM)

        assert "specialist_testing_4" in (result.get("note") or "")

    def test_an_unknown_writer_does_not_break_the_note(self, a_project, monkeypatch):
        from app.analysis import project_memory

        monkeypatch.setattr(project_memory, "who_changed", lambda root, path: "")

        assert "`deleteTask`" in (
            write_approved_artifact(str(a_project), "todo-app/app.js", WITHOUT_THEM).get("note") or ""
        )

    def test_a_raising_memory_does_not_fail_the_write(self, a_project, monkeypatch):
        from app.analysis import project_memory

        def _boom(root, path):
            raise RuntimeError("no memory")

        monkeypatch.setattr(project_memory, "who_changed", _boom)

        assert write_approved_artifact(
            str(a_project), "todo-app/app.js", WITHOUT_THEM
        )["status"] == "written"
