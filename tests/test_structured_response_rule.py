"""Every agent that owes a structured response must be told how to finish.

A model that has done its work sometimes writes the answer into the
conversation instead of returning it through the schema. The text often *is*
the right JSON - but nothing downstream sees it, because the workflow reads
`structured_response`, not the last message.

Measured twice in one afternoon, on two different agents, in one run:

    product_manager:       "**Product intake complete.** Here is the structured
                           summary:" -> next stage died on
                           KeyError: 'product_intake'
    architecture_reviewer: printed {"status": "approved", ...} as a message,
                           wrote its document again, printed again - five
                           times, until the repeat guard stopped the stage

Both already had some form of "return your structured response". Neither had
the part that matters: that a response written into the conversation is not
returned. The models were not ignoring the instruction; they believed they had
followed it.
"""

from __future__ import annotations

import pytest

#: Every agent with a `response_format`. A new one belongs here too.
AGENTS = [
    "product_manager",
    "tools_models",
    "stack_selector",
    "principal_architect",
    "architecture_reviewer",
    "scrum_master",
    "technical_lead",
    "security_reviewer",
    "milestone_reviewer",
    "specialists",
]


def _prompt(name: str) -> str:
    module = __import__(f"app.agents.{name}", fromlist=["_SYSTEM_PROMPT"])
    if name == "specialists":
        # One prompt per role, built from a template. Any role exercises it.
        return module._system_prompt("backend")
    return module._SYSTEM_PROMPT


@pytest.mark.parametrize("agent", AGENTS)
def test_every_agent_is_told_prose_is_not_a_response(agent):
    flat = " ".join(_prompt(agent).split())

    assert "a response written into the conversation is not returned" in flat.lower()


@pytest.mark.parametrize("agent", AGENTS)
def test_the_rule_is_interpolated_not_left_as_a_placeholder(agent):
    """A prompt that was never made an f-string keeps the literal braces."""
    assert "{STRUCTURED_RESPONSE_RULE}" not in _prompt(agent)


@pytest.mark.parametrize("agent", AGENTS)
def test_the_rule_closes_the_prompt(agent):
    """A closing instruction carries the most weight, and this one is about
    how to stop."""
    tail = " ".join(_prompt(agent).split())[-400:]

    assert "Return it." in tail or "not returned" in tail


@pytest.mark.parametrize("agent", AGENTS)
def test_re_sending_is_discouraged(agent):
    """The architecture reviewer re-wrote the same document five times."""
    flat = " ".join(_prompt(agent).split())

    assert "does not confirm it landed" in flat


def test_the_rule_records_where_it_came_from():
    from app.agents import structured_response

    # The failure it answers, in its own words; the run it happened on is in
    # the commit history, not the source.
    assert "KeyError: 'product_intake'" in structured_response.__doc__
    assert not __import__("re").search(r"run[- ][0-9a-f]{8}\b", structured_response.__doc__)


def test_every_agent_with_a_response_format_is_covered():
    """A new agent must not be able to miss this rule silently."""
    import pathlib
    import re

    directory = pathlib.Path(__file__).resolve().parent.parent / "src/app/agents"
    with_schema = {
        path.stem
        for path in directory.glob("*.py")
        if re.search(r"response_format\s*=", path.read_text())
    }

    # `role_agent` is the factory that *takes* a response_format, not an agent.
    with_schema.discard("role_agent")

    assert with_schema <= set(AGENTS), f"not covered by this test: {with_schema - set(AGENTS)}"
