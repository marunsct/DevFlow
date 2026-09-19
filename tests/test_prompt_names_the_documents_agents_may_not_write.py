"""Specialists are told which `docs/` names the workflow owns.

The writing rules tell every agent to put its reports in `docs/`. The workflow
owns nine files there, renders each from the structured response of the stage
that produces it, and rewrites it whole every time - so an agent that writes
one is refused. Nothing had told them which names were taken.

Measured across runs 60-67: 31 such calls from 13 different stages - every kind
of specialist plus two test rounds. Not one stage's mistake.
"""

from app.agents.role_agent import _READ_ONLY_RULES, _WRITING_RULES
from app.tools.repository import WORKFLOW_DOCUMENTS


def test_every_document_the_workflow_owns_is_named():
    for name in WORKFLOW_DOCUMENTS:
        assert f"`{name}`" in _WRITING_RULES, f"{name} is refused but never named"


def test_the_rule_says_what_to_do_instead():
    """A prohibition with no alternative is how the run-db3a4a0b stall started.

    The rule now refuses the whole of `docs/`, not only the nine names, so it
    has two alternatives to give and must give both: the structured response
    for anything a later stage needs, and the project directory for
    documentation that ships with the product.
    """
    assert "structured response" in _WRITING_RULES
    assert "WORKFLOW's directory" in _WRITING_RULES
    assert "project folder beside the code" in _WRITING_RULES


def test_a_read_only_agent_is_not_given_write_rules():
    """It has no `write_artifact`, so a list of paths it may not write is noise."""
    assert "WORKFLOW's directory" not in _READ_ONLY_RULES


def test_the_list_is_derived_rather_than_restated():
    """A hand-copied list drifts from the refusal; this must not be copyable."""
    import inspect

    from app.agents import role_agent

    source = inspect.getsource(role_agent)
    assert "WORKFLOW_DOCUMENTS" in source, "the prompt must read the same set the tool refuses"
    for name in WORKFLOW_DOCUMENTS:
        assert source.count(f'"{name}"') == 0, (
            f"{name} appears as a literal in role_agent; it should come from WORKFLOW_DOCUMENTS"
        )
