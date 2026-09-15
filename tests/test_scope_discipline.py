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


def test_the_rule_names_the_run_it_came_from():
    """Provenance, so a later reader can check whether it still applies."""
    from app.agents.scope_discipline import SCOPE_DISCIPLINE

    assert "run-c4f17841" in SCOPE_DISCIPLINE
    assert "Helm" in SCOPE_DISCIPLINE
