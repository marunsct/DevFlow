"""Scope inflation compounds down the chain, so the rule is stated at each step.

Measured on run-c4f17841 (brief_medium). Its brief names FastAPI or Express,
React or Vue, JWT, migrations and Docker, and contains the words Helm,
Kubernetes, Prometheus, Grafana, Redis, Celery and encryption zero times.

  1. The stack selector added "Celery with Redis" and "Prometheus + Grafana",
     for "future features like notifications" and observability.
  2. The architect, given that stack, wrote ADRs for Helm deployment
     artefacts, Prometheus middleware and pgcrypto encryption at rest.
  3. The architecture reviewer raised three BLOCKING findings because the Helm
     charts, the `/metrics` middleware and the pgcrypto migrations were absent.

By step 3 a task dashboard could not proceed without Kubernetes deployment
artefacts. No step was unreasonable given its input, which is why fixing only
the first one is not enough.
"""

from __future__ import annotations

import pytest

#: Every stage that can add scope, or refuse to proceed for its absence.
STAGES = [
    # The stage that decides which sprints exist at all. It was missed on the
    # first pass: run-64df2b20's plan allocated "Sprint 6 - Observability &
    # Health Checks" for a brief that never mentions observability, even though
    # the technical lead downstream had the rule.
    "scrum_master",
    "architecture_reviewer",
    "milestone_reviewer",
    "principal_architect",
    "security_reviewer",
    "technical_lead",
]


def _prompt(stage: str) -> str:
    module = __import__(f"app.agents.{stage}", fromlist=["_SYSTEM_PROMPT"])
    return module._SYSTEM_PROMPT


@pytest.mark.parametrize("stage", STAGES)
def test_every_scope_bearing_stage_carries_the_rule(stage):
    assert "the brief is the boundary" in _prompt(stage)


@pytest.mark.parametrize("stage", STAGES)
def test_the_rule_is_interpolated_not_left_as_a_placeholder(stage):
    """An f-string that was never made one leaves `{SCOPE_DISCIPLINE}` in place."""
    assert "{SCOPE_DISCIPLINE}" not in _prompt(stage)


@pytest.mark.parametrize("stage", STAGES)
def test_the_rule_says_an_unasked_for_omission_cannot_block(stage):
    prompt = _prompt(stage)

    assert "never as a blocking or major finding" in prompt
    assert "ideas do" in prompt and "not block" in prompt


def test_the_rule_keeps_the_observation_without_naming_a_run_or_a_stack():
    """What the rule needs is the shape of the failure, not its run id.

    It also does not need the brand names. The observation was "a brief naming
    FastAPI, React, JWT ... demanding Helm charts, a Prometheus metrics endpoint
    and pgcrypto encryption at rest" - five products from one JavaScript and
    Python run, in a rule that has to hold for a run in any language. Stated as
    roles rather than products it says the same thing to a run building in
    anything.
    """
    import re

    from app.agents.scope_discipline import SCOPE_DISCIPLINE

    flat = " ".join(SCOPE_DISCIPLINE.split())

    assert "three blocking findings" in flat
    assert "cluster deployment charts" in flat, "the shape of the over-reach is still named"
    assert "The brief mentions none of those words" in flat
    assert not re.search(r"run-[0-9a-f]{6,}", flat)


def test_missing_impossible_evidence_is_not_a_blocking_finding():
    """The architecture reviewer on a medium brief raised three *blocking*
    findings for absent Helm charts, a /metrics endpoint and pgcrypto
    migrations - artefacts nothing in this environment could have produced or
    verified. A task dashboard could not proceed until it shipped Kubernetes
    deployment artefacts.

    `brief_medium` asks for Docker containerization and PostgreSQL migrations,
    and neither can be built or applied here. The files are the deliverable;
    the build is not available.
    """
    from app.agents.scope_discipline import SCOPE_DISCIPLINE

    flat = " ".join(SCOPE_DISCIPLINE.split())

    assert "Evidence that cannot exist here is not a missing deliverable" in flat
    assert "the image was not built" in flat
    assert "never block a sprint for the absence of the rest" in flat


def test_every_scope_bearing_stage_gets_that_rule():
    """The reviewers are the stages that block, so reaching the planners only
    would leave the blocking behaviour unchanged."""
    from app.agents.architecture_reviewer import _SYSTEM_PROMPT as arch
    from app.agents.milestone_reviewer import _SYSTEM_PROMPT as milestone
    from app.agents.security_reviewer import _SYSTEM_PROMPT as security

    for name, prompt in (("architecture", arch), ("milestone", milestone), ("security", security)):
        assert "Evidence that cannot exist here" in prompt, name
