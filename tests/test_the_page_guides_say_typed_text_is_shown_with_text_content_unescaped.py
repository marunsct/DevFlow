"""The page-bearing JavaScript guides say typed text is shown with `textContent`, unescaped.

Measured on two runs of one full-stack brief (bookmarks 3 and 4): the quality test "markup in a title is shown as text and
never run" failed both times; the page escaped the title (`escapeHtml`) and then set it with `textContent`, so a title
`<b>x</b>` read `&lt;b&gt;x&lt;/b&gt;` on the page instead of the markup shown as plain text.
"""
from __future__ import annotations

import re

import pytest

from app.stacks.packs import browser_javascript, fullstack_node


@pytest.mark.parametrize("guide", [fullstack_node.GUIDE, browser_javascript.GUIDE])
def test_the_guide_says_text_content_and_no_escaping(guide):
    assert "`textContent`" in guide and "do not escape it first" in guide


@pytest.mark.parametrize("guide", [fullstack_node.GUIDE, browser_javascript.GUIDE])
def test_the_added_words_use_none_of_the_banned_ones(guide):
    added = guide[guide.index("Show text a person typed"):]

    assert not re.search(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", added, re.I)
