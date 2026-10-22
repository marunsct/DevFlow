"""A block comment ended early by a comment written inside it is named as such.

One run's `defect_fix_1_4` put an example in a JSDoc block:

    /**
     * Tests replace them by reassigning:
     *   storageAdapter.set = (key, value) => { /* mock */ };
     */

The inner `*/` ends the JSDoc. Node stopped on the `}` after it, the message
said a brace "closes something that was never opened - look at the block that
should contain it", and the stage rewrote the whole file four times: no block
was wrong, and to the eye the line was still a comment.
"""

from __future__ import annotations

from app.analysis.javascript_parse import _a_comment_that_ended_early, _the_other_half

RUN_S_FILE = """\
/**
 * task-manager/app.js
 */

/**
 * Storage adapter - abstracts localStorage access so tests can provide a mock.
 *
 * Tests replace them with no-op or in-memory implementations by reassigning:
 *   storageAdapter.set = (key, value) => { /* mock */ };
 *   storageAdapter.get = (key) => { /* mock */ };
 */
export const storageAdapter = {};
"""


class TestFindingIt:
    def test_the_run_s_file(self) -> None:
        assert _a_comment_that_ended_early(RUN_S_FILE) == (5, 9)

    def test_ordinary_comments_are_not_it(self) -> None:
        source = "/** a */\nconst x = 1; /* b */\n// c /* d\nconst y = 2;\n"

        assert _a_comment_that_ended_early(source) is None

    def test_a_comment_opener_inside_a_string_is_not_one(self) -> None:
        source = "const glob = '/* all */';\n/** doc */\nconst z = `a /* b`;\n"

        assert _a_comment_that_ended_early(source) is None

    def test_one_inside_a_line_comment_is_not_one(self) -> None:
        assert _a_comment_that_ended_early("// see /* this */\n/** ok */\n") is None


class TestTheMessage:
    def test_it_names_both_lines_and_the_rule(self) -> None:
        note = _the_other_half("SyntaxError: Unexpected token '}'", RUN_S_FILE, None, "9")

        assert "line 5" in note and "line 9" in note
        assert "do not nest" in note
        assert "brackets do not balance" not in note

    def test_it_says_nothing_about_a_failure_before_the_comment_closed(self) -> None:
        """Then the comment was intact and the fault is elsewhere."""
        note = _the_other_half("SyntaxError: Unexpected token '}'", RUN_S_FILE, None, "2")

        assert "do not nest" not in note
