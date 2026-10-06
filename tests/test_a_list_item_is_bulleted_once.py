"""A list item a model wrote with its own bullet is rendered with one bullet, not two.

One run's specification rendered every interface-design item as "- - Layout: ...":
the model began each item with "- ", and the renderer added its own.
"""

from __future__ import annotations

from app.agents.artifact_document import _value_lines


def test_an_item_s_own_bullet_is_not_doubled() -> None:
    assert _value_lines(["- Layout: form above the list", "* Spacing: 8px", "• Palette: two colours"]) == [
        "- Layout: form above the list", "- Spacing: 8px", "- Palette: two colours",
    ]


def test_a_leading_minus_that_is_not_a_bullet_stays() -> None:
    assert _value_lines(["-1 is the first index", "plain"]) == ["- -1 is the first index", "- plain"]
