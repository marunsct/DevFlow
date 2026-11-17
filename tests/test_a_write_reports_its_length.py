"""Every write and edit returns the file's line count.

Measured live on 2026-09-21 against `tests/brief_low.md`, whose constraints
include "Maximum 500 lines of code".

`test_round_0` checked and found 611 - `index.html(39) + style.css(270) +
app.js(302)` - and raised it as the run's only defect. Every one of the 48 unit
and end-to-end tests passed; the size was the single thing wrong.

`defect_fix_1_0` then ran

    wc -l task-manager/index.html task-manager/style.css task-manager/app.js

twenty times while compressing the files, once after each edit, because nothing
in a write result said how long the result was. The compression was real work.
The twenty round trips to measure it were not: the writer already has the
content in hand and can count it for nothing.

This is the same argument as `_where_it_landed`, which returns the surrounding
lines after an edit "so the next call is not a read of the whole file".
"""

from __future__ import annotations

import pytest

from app.tools.repository import _line_count


class TestItCountsTheWayWcDoes:
    @pytest.mark.parametrize(
        ("content", "expected"),
        [
            ("", 0),
            ("one", 1),
            ("one\n", 1),
            ("one\ntwo", 2),
            ("one\ntwo\n", 2),
            ("one\ntwo\nthree\n", 3),
            ("\n", 1),
            ("\n\n\n", 3),
        ],
    )
    def test_line_counts(self, content, expected):
        assert _line_count(content) == expected

    def test_a_file_without_a_final_newline_counts_its_last_line(self):
        """`wc -l` counts newlines and would report 2 here.

        Reporting 3 is the truthful answer for an agent asking "how long is this
        file", and the discrepancy only ever appears on a malformed file.
        """
        assert _line_count("a\nb\nc") == 3


class TestTheCountIsReturned:
    def test_a_write_returns_it(self, tmp_path):
        from app.tools.repository import write_approved_artifact

        result = write_approved_artifact(tmp_path, "notes/style.css", "a {}\nb {}\nc {}\n")

        assert result["lines"] == 3

    def test_an_edit_counts_the_file_not_the_replacement(self, tmp_path):
        """An edit changes part of a file; only the file knows the total.

        Counting `replace` would report the size of the patch and read as the
        size of the file, which is a wrong number presented as a measurement.
        """
        from app.tools.repository import edit_approved_artifact, write_approved_artifact

        write_approved_artifact(tmp_path, "notes/style.css", "a {}\nb {}\nc {}\n")

        result = edit_approved_artifact(tmp_path, "notes/style.css", "b {}\n", "b {}\nb2 {}\n")

        assert result["lines"] == 4
