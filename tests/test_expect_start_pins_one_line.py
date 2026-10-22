"""`expect_start` pins one line, and a caller that sends two must not be lied to.

`replace_lines` compares `expect_start` against one line of the file. A caller
that sends two cannot match anything, and the refusal that follows reads:

    Line 1 of 'package.json' is not what you expected, so the numbering has
    moved since you read it.
      you expected: {
        "name": "simple-to-do-list-app"
      line 1 is:  {
    That line is not in the file at all now - it may have been changed or
    removed since you read it. Read the file again.

Three statements that contradict each other. It prints the line, prints the same
line back, then says the line is not in the file. Nothing in it could lead a
reader to the newline that caused it.

Measured on one run's `specialist_ui_ux_0`, which sent exactly that, twice
in the same second, on a `package.json` whose line 1 really was `{`. The call was
right about where the line was and was refused for the shape of an argument.

Forgiven rather than refused, which is what this module already does with every
other unambiguous transcription fault - line numbers, doubled backslashes, JSON
escaping, indentation and blank lines are all forgiven here. The first line is
not a guess at what was meant: it is what the parameter is defined to carry.
"""

from __future__ import annotations

import pytest

from app.tools.repository import (
    RepositoryToolError,
    _the_one_line_it_pins,
    replace_approved_lines,
)

A_MANIFEST = '{\n  "name": "simple-to-do-list-app",\n  "version": "1.0.0"\n}\n'

#: What one run actually sent as `expect_start`.
TWO_LINES = '{\n  "name": "simple-to-do-list-app"'


@pytest.fixture
def a_project(tmp_path):
    (tmp_path / "package.json").write_text(A_MANIFEST)
    return tmp_path


class TestReducingItToTheLineItPins:
    @pytest.mark.parametrize("sent, expected", [
        (TWO_LINES, "{"),
        ("const a = 1;", "const a = 1;"),
        ("\n\n  const a = 1;\n  const b = 2;", "  const a = 1;"),
        ("", ""),
        ("\n\n", "\n\n"),
    ])
    def test_the_first_line_with_anything_on_it(self, sent, expected):
        assert _the_one_line_it_pins(sent) == expected

    def test_indentation_is_kept_because_the_comparison_strips_it_later(self):
        """Stripping here would lose the line the message prints back."""
        assert _the_one_line_it_pins("    indented();\nsecond();") == "    indented();"


class TestTheCallThatWasRefusedTwice:
    def test_it_now_succeeds(self, a_project):
        result = replace_approved_lines(
            a_project, "package.json", 1, 4,
            '{\n  "name": "app"\n}\n',
            expect_start=TWO_LINES,
        )

        assert result["status"] == "edited"
        assert (a_project / "package.json").read_text() == '{\n  "name": "app"\n}\n'

    def test_the_contract_is_taught_without_a_failure(self, a_project):
        """The agent should learn the rule, and not by losing a call to it."""
        result = replace_approved_lines(
            a_project, "package.json", 1, 4,
            '{\n  "name": "app"\n}\n',
            expect_start=TWO_LINES,
        )

        assert "pins one line" in result["detail"]
        assert "sent 2" in result["detail"]

    def test_one_line_is_not_remarked_on(self, a_project):
        """A correct call must not be told about a rule it kept."""
        result = replace_approved_lines(
            a_project, "package.json", 2, 2,
            '  "name": "renamed",\n', expect_start='  "name": "simple-to-do-list-app",',
        )

        assert "pins one line" not in result.get("detail", "")


class TestStillRefusingWhatItShould:
    def test_a_genuine_mismatch_is_still_refused(self, a_project):
        """Forgiving the shape must not forgive the content."""
        with pytest.raises(RepositoryToolError) as refused:
            replace_approved_lines(
                a_project, "package.json", 1, 2, "x\n",
                expect_start='"not in this file at all"\n  "second line"',
            )

        assert "is not what you expected" in str(refused.value)

    def test_the_refusal_now_compares_one_line_with_one_line(self, a_project):
        """What made the old message unreadable was the blob against the line."""
        with pytest.raises(RepositoryToolError) as refused:
            replace_approved_lines(
                a_project, "package.json", 1, 2, "x\n",
                expect_start='"gone"\n  "also gone"',
            )

        message = str(refused.value)
        assert "also gone" not in message, "only the pinned line belongs in the report"

    def test_a_drifted_range_with_both_ends_sent_as_pairs_still_relocates(self, tmp_path):
        """`expect_end` takes the same treatment, or the relocation path breaks.

        Both ends pinned is what lets a drifted edit be applied rather than
        reported, and it compares `expect_end` the same way.
        """
        (tmp_path / "app.js").write_text(
            "// added header\n// another\nconst a = 1;\nconst b = 2;\nconst c = 3;\n"
        )

        result = replace_approved_lines(
            tmp_path, "app.js", 1, 2, "const a = 9;\nconst b = 8;\n",
            expect_start="const a = 1;\nconst b = 2;",
            expect_end="const b = 2;\nconst c = 3;",
        )

        assert result["status"] == "edited"
        assert "const a = 9;" in (tmp_path / "app.js").read_text()
        assert "// added header" in (tmp_path / "app.js").read_text(), (
            "the header must survive; the range moved rather than being overwritten"
        )
