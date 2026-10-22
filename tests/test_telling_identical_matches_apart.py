"""An ambiguity message must be able to tell the copies it found apart.

`edit_artifact` on text that appears more than once reports where each copy is
and what surrounds it, so the agent can extend its `find` or use
`replace_lines` instead. Both halves assumed one match per line.

Measured on one run, where two stages sent `find: "}"` against a 40-line
file and were answered:

    That text appears 12 times in 'simple-to-do-list-app/app.js', so it is
    ambiguous which one to change. It starts at lines 7, 12, 12, 12, 13, 15,
    21, 26, 29, 30, 34 and 40. Either add whichever of these surrounding lines
    differs between them to your `find` ... A position is never ambiguous, and
    the numbers are in the list above.

`12, 12, 12` is one line holding three matches printed three times. The message
then points at "the numbers in the list above" as the way to pick one, and a
repeated number picks nothing. The context blocks have the same fault from the
other side: three byte-identical quotes of the same surrounding lines, in the
helper whose stated purpose is to "show the lines that differ".

A third disagreement sits underneath both. The count is `str.count`, which does
not count overlapping matches, and the scan advanced one character at a time,
which does - so `find: "aa"` against `aaaa` reported "appears 2 times ... It
starts at lines 1, 1 and 1".

Nothing here is about any language. A duplicated brace, a repeated `end`, a
second `</div>`, two `pass` statements: the message is the same one, and it is
reached by copying text the file holds twice.
"""

from __future__ import annotations

import pytest

from app.tools.repository import (
    _what_sits_around_each_match,
    _where_each_match_starts,
)

#: One run's shape, reduced: one line holding three copies of the `find`,
#: and a fourth on a line of its own.
THREE_ON_ONE_LINE = (
    "function a() {\n"
    "  if (p) { x(); } else if (q) { y(); } else { z(); }\n"
    "}\n"
)


class TestCountingEachLineOnce:
    def test_a_line_holding_three_matches_is_named_once(self):
        """The whole rendering, because the exact shape is what the message quotes."""
        listed = _where_each_match_starts(THREE_ON_ONE_LINE, "}")

        assert listed == "lines 2 (3 times) and 3", listed

    def test_how_many_are_on_that_line_is_said(self):
        """Otherwise the count and the list disagree and neither can be trusted."""
        listed = _where_each_match_starts(THREE_ON_ONE_LINE, "}")

        assert "2 (3 times)" in listed or "line 2 (3 times)" in listed, listed

    def test_the_other_lines_are_still_listed(self):
        listed = _where_each_match_starts(THREE_ON_ONE_LINE, "}")

        assert "3" in listed

    def test_a_single_match_per_line_reads_as_it_always_did(self):
        text = "alpha\nbeta\nalpha\n"

        assert _where_each_match_starts(text, "alpha") == "lines 1 and 3"

    def test_one_match_reads_as_it_always_did(self):
        assert _where_each_match_starts("alpha\nbeta\n", "alpha") == "line 1"

    def test_every_match_on_one_line_says_only_that_line(self):
        assert _where_each_match_starts("a a a\n", "a") == "line 1 (3 times)"

    def test_no_match_is_still_described(self):
        assert _where_each_match_starts("alpha\n", "omega") == "several places"


class TestAgreeingWithTheCountTheMessageQuotes:
    @pytest.mark.parametrize(
        "text,find",
        [
            ("aaaa\n", "aa"),
            ("ababab\n", "abab"),
            ("....\n", ".."),
            ("xxx\n", "xx"),
        ],
    )
    def test_overlapping_matches_are_counted_as_the_message_counts_them(
        self, text, find
    ):
        """`str.count` is what the sentence quotes, so the list must use it too."""
        expected = text.count(find)
        listed = _where_each_match_starts(text, find)

        total = 0
        stripped = listed.replace("lines ", "").replace("line ", "")
        for part in stripped.replace(" and ", ",").split(","):
            part = part.strip()
            if not part:
                continue
            total += int(part.split("(")[1].split()[0]) if "(" in part else 1

        assert total == expected, f"{listed} describes {total}, message says {expected}"

    def test_a_non_overlapping_find_is_unaffected(self):
        assert _where_each_match_starts("ab\nab\n", "ab") == "lines 1 and 2"

    def test_an_empty_find_does_not_hang(self):
        """A degenerate input must return, not scan for ever."""
        assert _where_each_match_starts("abc\n", "") != ""


class TestContextThatActuallyDiffers:
    def test_identical_blocks_are_not_quoted_twice(self):
        """Three copies on line 2 got three byte-identical quotes of lines 1 and 3."""
        quoted = _what_sits_around_each_match(THREE_ON_ONE_LINE, "}")

        assert quoted.count("on line 2") == 1, quoted

    def test_a_line_with_several_matches_shows_the_line_itself(self):
        """The lines around it cannot tell three copies on one line apart."""
        quoted = _what_sits_around_each_match(THREE_ON_ONE_LINE, "}")

        assert "if (p) { x(); } else if (q) { y(); } else { z(); }" in quoted

    def test_it_says_the_surrounding_lines_cannot_separate_them(self):
        quoted = _what_sits_around_each_match(THREE_ON_ONE_LINE, "}")

        assert "3 times on this line" in quoted

    def test_copies_on_different_lines_are_quoted_as_before(self):
        text = "head\nalpha\ntail\nother\nalpha\nlast\n"
        quoted = _what_sits_around_each_match(text, "alpha")

        assert "the copy at line 2" in quoted
        assert "the copy at line 5" in quoted
        assert "head" in quoted and "other" in quoted

    def test_nothing_found_quotes_nothing(self):
        assert _what_sits_around_each_match("alpha\n", "omega") == ""


class TestTheMessageTheStageReceives:
    def test_the_list_and_the_count_agree_on_the_file_that_broke_the_run(
        self, tmp_path
    ):
        """End to end, through the tool, on one run's actual shape."""
        from app.tools.repository import RepositoryToolError, edit_approved_artifact

        root = tmp_path / "workspace"
        (root / "app").mkdir(parents=True)
        (root / "app" / "app.js").write_text(THREE_ON_ONE_LINE)

        with pytest.raises(RepositoryToolError) as raised:
            edit_approved_artifact(str(root), "app/app.js", "}", "};")

        message = str(raised.value)
        assert "appears 4 times" in message
        assert "12, 12" not in message
        assert "lines 2, 2" not in message

    def test_a_same_line_collision_is_told_line_numbers_will_not_settle_it(
        self, tmp_path
    ):
        """`replace_lines` takes a whole line, so it cannot pick one of three."""
        from app.tools.repository import RepositoryToolError, edit_approved_artifact

        root = tmp_path / "workspace"
        (root / "app").mkdir(parents=True)
        (root / "app" / "app.js").write_text(THREE_ON_ONE_LINE)

        with pytest.raises(RepositoryToolError) as raised:
            edit_approved_artifact(str(root), "app/app.js", "}", "};")

        assert "same line" in str(raised.value)

    def test_copies_on_separate_lines_still_get_the_position_advice(self, tmp_path):
        """Which is the right advice there, and must not be lost."""
        from app.tools.repository import RepositoryToolError, edit_approved_artifact

        root = tmp_path / "workspace"
        (root / "app").mkdir(parents=True)
        (root / "app" / "app.js").write_text("head\nalpha\ntail\nalpha\n")

        with pytest.raises(RepositoryToolError) as raised:
            edit_approved_artifact(str(root), "app/app.js", "alpha", "beta")

        assert "replace_lines" in str(raised.value)
