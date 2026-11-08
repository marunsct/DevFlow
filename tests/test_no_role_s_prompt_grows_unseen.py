"""Each role's rendered system prompt stays within a recorded size (Initiative X.4).

The prompt is paid for on a stage's first call and carried in every call's
prefix; it grew by accretion, one measured rule at a time, with the evidence
for each rule written into it. The ceilings are today's sizes with a margin:
growing past one is a decision, made by raising it here with the reason.
"""

from __future__ import annotations

import pytest

from tests.test_prompt_names_only_offered_tools import rendered  # noqa: F401 - the fixture

#: Characters, today's size plus about 5%. Lower one when a prompt shrinks.
CEILINGS = {
    "specialist": 13_400,
    # + the rule that the product ships every route, so none is added only for the tests (LF.757): a fixer added an
    # unauthenticated route that deletes every record, for a test's clean-up.
    "principal_architect": 12_500,
    "technical_lead": 10_800,
    "stack_selector": 10_100,
    "senior_architect_reviewer": 9_500,
    "milestone_reviewer": 8_400,
    "scrum_master": 6_000,
    # + the rule that a test never starts a running product itself (LF.159): one
    # such test hung a whole acceptance suite and its writer for 40 minutes.
    # + the rule that a test never reads a kept file's text (LF.647): two full-stack runs in a row reopened their
    # locked suite after the build for a test asserting the kept start script's lines.
    "acceptance_reviewer": 4_800,
}
OTHERWISE = 4_200


def _ceiling(name: str) -> int:
    for prefix, ceiling in CEILINGS.items():
        if name.startswith(prefix):
            return ceiling
    return OTHERWISE


def test_no_role_s_prompt_is_past_its_ceiling(rendered) -> None:  # noqa: F811
    over = {name: len(prompt) for name, (prompt, _) in rendered.items() if len(prompt) > _ceiling(name)}
    assert over == {}


def test_no_prompt_carries_the_evidence_for_its_rules(rendered) -> None:  # noqa: F811
    """The evidence belongs beside the code; the model needs the rule."""
    carrying = [name for name, (prompt, _) in rendered.items() if "Measured across the stored" in prompt]
    assert carrying == []
