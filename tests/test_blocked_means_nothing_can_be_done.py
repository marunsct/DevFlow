"""`blocked` re-plans the sprint from nothing; `changes_required` fixes it. The schema says so.

The three statuses a milestone reviewer can return have wildly different
consequences - `accepted` continues the sprint, `changes_required` re-plans the
milestone and lets specialists fix every finding, `blocked` (which then ended
the run, and now records the sprint failed and plans it again from the start)
fixes none of them - and the field description said
only "Routing decision: accepted, changes required, or blocked."

One run died sixteen minutes in. Its review was good: `toggleTask` absent
so every checkbox did nothing, filter buttons with no handlers, and no tests
for either. Every finding carried a precise `required_remediation`. It chose
`blocked` because its findings were severity "blocking" - the natural reading -
and the run ended without one revision being attempted. One run's reviewer
called the same class of defect `changes_required` and got three revisions.

The prompt already said to use `changes_required` for a blocking finding, and
this reviewer read past it, which is class A of the hardening plan: guidance
loses, corrections win. So a finding that states how to remedy itself is
treated as remediable, and a status meaning "nothing can be done" cannot be
carried by a list of things to do.
"""

from __future__ import annotations

import pydantic
import pytest

from app.agents.milestone_reviewer import MilestoneReviewOutput

REMEDIABLE = {
    "severity": "blocking",
    "category": "correctness",
    "description": "toggleTask is absent, so every checkbox does nothing.",
    "affected_files": ["app.js"],
    "required_remediation": "Add toggleTask(id, tasks) and wire the change handler.",
}
UNFIXABLE = {
    "severity": "blocking",
    "category": "other",
    "description": "The upstream API this milestone depends on has been withdrawn.",
    "affected_files": [],
    "required_remediation": "",
}


def _review(status, findings):
    return MilestoneReviewOutput(
        status=status,
        findings=findings,
        acceptance_evidence="checked",
        documentation_reviewed=True,
        tests_reviewed=True,
    )


def test_blocked_is_refused_when_every_finding_says_how_to_fix_it():
    with pytest.raises(pydantic.ValidationError) as raised:
        _review("blocked", [REMEDIABLE])

    message = str(raised.value)
    assert "nothing will be fixed" in message
    assert "changes_required" in message


def test_the_refusal_says_what_to_use_instead(): 
    with pytest.raises(pydantic.ValidationError) as raised:
        _review("blocked", [REMEDIABLE, dict(REMEDIABLE)])
    assert "all 2 of your findings" in str(raised.value)


def test_changes_required_with_the_same_findings_is_accepted():
    """The status that gets them fixed must stay easy to return."""
    assert _review("changes_required", [REMEDIABLE]).status == "changes_required"


def test_a_genuinely_unfixable_finding_may_still_block():
    """`blocked` must remain reachable, or the status is a lie."""
    assert _review("blocked", [UNFIXABLE]).status == "blocked"


def test_a_mix_may_block_because_one_finding_cannot_be_remedied():
    assert _review("blocked", [REMEDIABLE, UNFIXABLE]).status == "blocked"


def test_blocked_with_no_findings_is_left_alone():
    """Another branch already refuses a decision that says nothing."""
    assert _review("blocked", []).status == "blocked"


def test_whitespace_is_not_a_remediation():
    finding = dict(REMEDIABLE, required_remediation="   ")
    assert _review("blocked", [finding]).status == "blocked"


def test_accepted_is_untouched():
    assert _review("accepted", []).status == "accepted"


def test_the_field_says_what_each_status_does():
    """The description was a tautology naming the three words back."""
    description = MilestoneReviewOutput.model_fields["status"].description
    assert "plans it again from the start" in description
    assert "the sprint continues" in description
    assert "re-plans" in description


def test_what_the_schema_says_blocked_does_is_what_the_workflow_does():
    """The schema said the run ENDS HERE; the workflow re-plans the sprint.
    A reviewer choosing by a consequence that never happens is choosing blind."""
    from app.agents.milestone_reviewer import BLOCKED_MEANS
    from app.graph.workflow import MILESTONE_REVIEW_NEXT_STAGE

    description = MilestoneReviewOutput.model_fields["status"].description
    assert BLOCKED_MEANS in description
    assert MILESTONE_REVIEW_NEXT_STAGE["blocked"] == "technical_lead"
    assert "Technical Lead plans it again" in BLOCKED_MEANS
    for claim in ("ENDS", "ends the run", "ends this run", "permanently"):
        assert claim not in description

    with pytest.raises(pydantic.ValidationError) as raised:
        _review("blocked", [REMEDIABLE])
    assert "ends this run" not in str(raised.value)
    assert BLOCKED_MEANS in str(raised.value)


def test_the_blocked_wording_avoids_the_banned_words():
    import re

    from app.agents.milestone_reviewer import BLOCKED_MEANS

    banned = {"task", "tasks", "to-do", "todo", "button", "click", "checkbox"}
    assert not set(re.findall(r"[\w-]+", BLOCKED_MEANS.lower())) & banned
