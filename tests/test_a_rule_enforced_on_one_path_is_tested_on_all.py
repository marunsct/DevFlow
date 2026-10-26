"""The test round is told to try the edit path with what the create path refuses.

One run shipped, through two test rounds, a security review and two milestone
reviews, a product whose add form refused an empty title and whose inline edit
saved one. Every suite tested edit with a new non-empty value.
"""

from app.agents.specialists import build_test_run_request


def _text(root) -> str:
    # An empty project, not "/": the request reads what the project's files already prove, and from "/" that walked the
    # whole filesystem (minutes on a host with large mounted folders).
    return build_test_run_request("Users can add and edit tasks", ["app/app.js"], str(root))["messages"][0]["content"]


def test_the_rule_is_in_the_test_round_s_instructions(tmp_path):
    text = " ".join(_text(tmp_path).split())

    assert "A rule the product enforces on one path must hold on every path" in text
    assert "send that value through every other way the product changes it" in text
