"""A `replace_lines` without `expect_start` quotes the line it deleted.

`expect_start` is optional. The one time it was omitted in the completed run of
2026-09-21 it cost the product a requirement. `specialist_ui_ux_1` sent::

    replace_lines(relative_path="task-manager/index.html",
                  start_line=5, end_line=5,
                  content='  <meta http-equiv="Content-Security-Policy" ...>')

Line 5 was `<meta name="viewport" content="width=device-width, ...">`. The intent
was plainly to *add* a Content-Security-Policy tag; the effect was to replace
the viewport tag with it, and the stylesheet's three width media queries became
unreachable on every phone. The brief required "Responsive design for mobile and
desktop". Forty-seven end-to-end tests, a security review and five milestone
reviews passed afterwards.

The result said "Replaced lines 5-5 of 39" - true, and silent about the line
that was now gone.
"""

from __future__ import annotations

import pytest

from app.tools.repository import replace_approved_lines


@pytest.fixture
def page(tmp_path):
    (tmp_path / "index.html").write_text(
        "<!DOCTYPE html>\n"
        "<html>\n"
        "<head>\n"
        '  <meta charset="UTF-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        "  <title>T</title>\n"
        "</head>\n"
        "</html>\n"
    )
    return tmp_path


class TestTheExactCallThatBrokeRunOne:
    def test_it_names_what_was_removed(self, page):
        result = replace_approved_lines(
            str(page), "index.html", start_line=5, end_line=5,
            content='  <meta http-equiv="Content-Security-Policy" content="default-src self">\n',
        )
        detail = result["detail"]
        assert "No `expect_start` was sent" in detail
        assert "viewport" in detail, "the deleted line must be quoted"

    def test_it_suggests_the_guard(self, page):
        result = replace_approved_lines(
            str(page), "index.html", start_line=5, end_line=5,
            content='  <meta http-equiv="Content-Security-Policy" content="x">\n',
        )
        assert "pass\n`expect_start`" in result["detail"].replace(" `expect_start`", "\n`expect_start`") \
            or "`expect_start`" in result["detail"]

    def test_it_offers_insertion_as_the_likely_intent(self, page):
        result = replace_approved_lines(
            str(page), "index.html", start_line=5, end_line=5,
            content='  <meta http-equiv="Content-Security-Policy" content="x">\n',
        )
        detail = " ".join(result["detail"].split())
        assert "add lines rather than replace them, put what was removed back" in detail
        # It used to say "send it again as an insertion"; the tool has no such mode.
        assert "no insert mode" in detail
        assert "as an insertion" not in detail


class TestItStaysQuietWhenThereIsNoSurprise:
    def test_a_guarded_replacement_says_nothing_extra(self, page):
        """With `expect_start` the caller already said what it expected."""
        result = replace_approved_lines(
            str(page), "index.html", start_line=5, end_line=5,
            content='  <meta name="viewport" content="width=device-width">\n',
            expect_start='  <meta name="viewport" content="width=device-width, initial-scale=1.0">',
        )
        assert "No `expect_start` was sent" not in result["detail"]

    def test_an_edit_of_the_same_line_is_not_echoed_back(self, page):
        """Rewriting a line you are plainly editing is not a surprise."""
        result = replace_approved_lines(
            str(page), "index.html", start_line=5, end_line=5,
            content='  <meta name="viewport" content="width=device-width, initial-scale=2.0">\n',
        )
        assert "No `expect_start` was sent" not in result["detail"]

    def test_replacing_a_blank_line_says_nothing(self, tmp_path):
        (tmp_path / "f.txt").write_text("a\n\nc\n")
        result = replace_approved_lines(
            str(tmp_path), "f.txt", start_line=2, end_line=2, content="b\n"
        )
        assert "No `expect_start` was sent" not in result["detail"]


class TestItReportsAMultiLineRemoval:
    def test_the_count_of_further_lines_is_given(self, page):
        result = replace_approved_lines(
            str(page), "index.html", start_line=4, end_line=6,
            content="  <title>Replaced</title>\n",
        )
        detail = result["detail"]
        assert "No `expect_start` was sent" in detail
        assert "more line(s)" in detail
