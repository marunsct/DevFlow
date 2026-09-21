"""A drifted `replace_lines` range is applied when both ends are pinned.

`_where_that_line_went` explains why a drifted edit is *reported* rather than
applied: `expect_start` pins only the first line, so shifting the whole range by
the same offset would delete whatever now sits at the other end. That reasoning
is right, and it names its own remedy - pin the other end too.

Measured on the run of 2026-09-21: six of its twelve costly tool failures were
this refusal, all on `task-manager/app.js`, every one recoverable and every one
costing a model call to recover. Two of them::

    start_line 267, end_line 274   expected "// Filter button click handlers"
    start_line 7,   end_line 9     expected " *   toggleTask, setFilter, ..."

With `expect_end` supplied the range is identified by its two ends rather than
by where it sits, so the drift stops mattering. Without it, nothing changes.
"""

from __future__ import annotations

import pytest

from app.tools.repository import RepositoryToolError, replace_approved_lines


@pytest.fixture
def project(tmp_path):
    (tmp_path / "app.js").write_text(
        "// header\n"          # 1
        "// blank\n"           # 2
        "const a = 1;\n"       # 3
        "const b = 2;\n"       # 4
        "const c = 3;\n"       # 5
        "// tail\n"            # 6
    )
    return tmp_path


class TestBothEndsPinnedSurvivesDrift:
    def test_a_range_that_moved_down_is_applied_there(self, project):
        (project / "app.js").write_text(
            "// new line one\n"
            "// new line two\n"
            "// header\n// blank\nconst a = 1;\nconst b = 2;\nconst c = 3;\n// tail\n"
        )
        result = replace_approved_lines(
            str(project), "app.js",
            start_line=3, end_line=5,
            content="const a = 10;\nconst b = 20;\nconst c = 30;\n",
            expect_start="const a = 1;", expect_end="const c = 3;",
        )
        assert "error" not in result
        text = (project / "app.js").read_text()
        assert "const a = 10;" in text and "const c = 30;" in text
        assert "const a = 1;" not in text
        assert "// new line one" in text, "content outside the range was preserved"

    def test_the_note_says_the_range_moved(self, project):
        (project / "app.js").write_text("// extra\n" + (project / "app.js").read_text())
        result = replace_approved_lines(
            str(project), "app.js",
            start_line=3, end_line=5, content="X\nY\nZ\n",
            expect_start="const a = 1;", expect_end="const c = 3;",
        )
        assert "numbering had moved" in result.get("detail", "")
        assert "further down" in result["detail"]

    def test_a_range_that_moved_up_is_applied_there(self, project):
        # "// blank" removed, so the range that was 3-5 is now 2-4.
        (project / "app.js").write_text(
            "// header\nconst a = 1;\nconst b = 2;\nconst c = 3;\n// tail\n"
        )
        result = replace_approved_lines(
            str(project), "app.js",
            start_line=3, end_line=5, content="X\nY\nZ\n",
            expect_start="const a = 1;", expect_end="const c = 3;",
        )
        assert "error" not in result
        assert "further up" in result.get("detail", "")


class TestItStillRefusesWhenItCannotBeSure:
    def test_only_expect_start_keeps_the_old_behaviour(self, project):
        """One line cannot say where the range now ends."""
        (project / "app.js").write_text("// extra\n" + (project / "app.js").read_text())
        with pytest.raises(RepositoryToolError) as caught:
            replace_approved_lines(
                str(project), "app.js",
                start_line=3, end_line=5, content="X\n",
                expect_start="const a = 1;",
            )
        assert "numbering has moved" in str(caught.value)

    def test_a_range_that_changed_size_is_refused(self, project):
        """The caller's replacement was written against a range that is gone.

        The start must genuinely have moved, or the first-line guard never
        fires and this is an ordinary in-place replace.
        """
        (project / "app.js").write_text(
            "// pad\n// header\n// blank\nconst a = 1;\nINSERTED\nconst b = 2;\n"
            "const c = 3;\n// tail\n"
        )
        with pytest.raises(RepositoryToolError):
            replace_approved_lines(
                str(project), "app.js",
                start_line=3, end_line=5, content="X\n",
                expect_start="const a = 1;", expect_end="const c = 3;",
            )

    def test_an_ambiguous_end_is_refused(self, project):
        """Two candidates for the last line is a guess, and guesses are expensive."""
        (project / "app.js").write_text(
            "// pad\n// header\n// blank\nconst a = 1;\nconst b = 2;\n"
            "const c = 3;\nconst c = 3;\n"
        )
        with pytest.raises(RepositoryToolError):
            replace_approved_lines(
                str(project), "app.js",
                start_line=3, end_line=5, content="X\n",
                expect_start="const a = 1;", expect_end="const c = 3;",
            )

    def test_a_missing_start_is_refused(self, project):
        with pytest.raises(RepositoryToolError) as caught:
            replace_approved_lines(
                str(project), "app.js",
                start_line=3, end_line=5, content="X\n",
                expect_start="this line never existed", expect_end="// tail",
            )
        assert "not in the file at all" in str(caught.value)


class TestTheUnmovedCaseIsUnaffected:
    def test_correct_line_numbers_still_work(self, project):
        result = replace_approved_lines(
            str(project), "app.js",
            start_line=3, end_line=5, content="X\nY\nZ\n",
            expect_start="const a = 1;", expect_end="const c = 3;",
        )
        assert "error" not in result
        assert "numbering had moved" not in result.get("detail", "")

    def test_no_expectations_at_all_still_work(self, project):
        result = replace_approved_lines(
            str(project), "app.js", start_line=3, end_line=3, content="Z\n",
        )
        assert "error" not in result


class TestTheAgentCanActuallySendIt:
    def test_the_tool_wrapper_accepts_expect_end(self):
        import inspect

        from app.tools import agent_toolkit

        source = inspect.getsource(agent_toolkit)
        assert "expect_end: str = \"\"" in source, "agents cannot pass what the tool omits"

    def test_the_prompt_tells_the_agent_to_send_it(self):
        import inspect

        from app.agents import role_agent

        assert "expect_end" in inspect.getsource(role_agent)
