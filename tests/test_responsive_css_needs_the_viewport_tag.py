"""Width media queries on a page with no viewport meta tag are dead code.

A mobile browser renders a page with no `<meta name="viewport">` into a virtual
window about 980 CSS pixels wide and scales the picture down. Every `max-width`
query written for a phone evaluates against 980, never fires, and the responsive
stylesheet does nothing. Nothing throws; the page just looks like a shrunken
desktop.

Found in the completed run of 2026-09-21, against a brief whose acceptance
criteria included "Responsive design for mobile and desktop".
`specialist_ui_ux_0` wrote the tag. `specialist_ui_ux_1` then ran::

    replace_lines(relative_path="task-manager/index.html",
                  start_line=5, end_line=5,
                  content='  <meta http-equiv="Content-Security-Policy" ...>')

with no `expect_start`. Line 5 was the viewport tag, so the CSP tag replaced it
instead of joining it. The stylesheet kept three width queries, two below 360px,
which could never match again.

It shipped: 47 Playwright end-to-end tests passed (Playwright's default viewport
is desktop-sized), a security review passed, and five milestone reviews passed.
"""

from __future__ import annotations

import pytest

from app.analysis.integration_checks import (
    _responsive_css_the_page_cannot_use,
    _source_files,
)


def _problems(root):
    return _responsive_css_the_page_cannot_use(_source_files(root), root)


@pytest.fixture
def site(tmp_path):
    (tmp_path / "style.css").write_text(
        "body { margin: 0 }\n"
        "@media (max-width: 320px) { .container { padding: 0 } }\n"
        "@media (max-width: 359px) { .edit-btn { display: none } }\n"
    )
    return tmp_path


def _page(root, head_extra=""):
    (root / "index.html").write_text(
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        '  <meta charset="UTF-8">\n'
        f"{head_extra}"
        '  <link rel="stylesheet" href="style.css">\n'
        "</head>\n<body><main></main></body>\n</html>\n"
    )


class TestItCatchesTheRealDefect:
    def test_a_page_without_the_tag_is_reported(self, site):
        _page(site)
        found = _problems(site)
        assert found, "the defect that shipped was not caught"
        assert "viewport" in found[0]

    def test_it_counts_the_queries_that_are_dead(self, site):
        _page(site)
        assert "2 width-based media queries" in _problems(site)[0]

    def test_it_names_both_files(self, site):
        _page(site)
        message = _problems(site)[0]
        assert "index.html" in message and "style.css" in message

    def test_it_says_what_to_add(self, site):
        _page(site)
        assert 'content="width=device-width' in _problems(site)[0]

    def test_it_says_why_the_suite_did_not_catch_it(self, site):
        """An agent told only "add a tag" will wonder why its tests were green."""
        _page(site)
        assert "end-to-end run cannot see this" in _problems(site)[0]


class TestItStaysQuietWhenItShould:
    def test_a_page_with_the_tag_is_fine(self, site):
        _page(site, '  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n')
        assert _problems(site) == []

    @pytest.mark.parametrize("spelling", [
        "<meta name='viewport' content='width=device-width'>",
        '<META NAME="VIEWPORT" CONTENT="width=device-width">',
        '<meta charset="utf-8"><meta name="viewport" content="width=device-width">',
    ])
    def test_every_spelling_of_the_tag_counts(self, site, spelling):
        _page(site, "  " + spelling + "\n")
        assert _problems(site) == []

    def test_a_stylesheet_with_no_width_queries_is_fine(self, tmp_path):
        """`prefers-color-scheme` and `print` do not depend on the tag."""
        (tmp_path / "style.css").write_text(
            "@media (prefers-color-scheme: dark) { body { color: #fff } }\n"
            "@media print { .no-print { display: none } }\n"
        )
        _page(tmp_path)
        assert _problems(tmp_path) == []

    def test_a_page_that_does_not_load_the_sheet_is_fine(self, site):
        """Only a page that actually loads the responsive stylesheet."""
        (site / "index.html").write_text(
            "<!DOCTYPE html>\n<html><head><meta charset='utf-8'></head>"
            "<body>no stylesheet here</body></html>\n"
        )
        assert _problems(site) == []

    def test_no_stylesheet_at_all_is_fine(self, tmp_path):
        _page(tmp_path)
        assert _problems(tmp_path) == []

    def test_no_page_at_all_is_fine(self, site):
        assert _problems(site) == []


class TestItIsRegistered:
    def test_the_check_runs_in_the_summary(self):
        from app.analysis.integration_checks import _CHECKS

        assert any("viewport" in describe for describe, _ in _CHECKS), (
            "a check nothing calls is the defect this module exists to prevent"
        )
