"""The acceptance review answers without reasoning only behind `REVIEWS_WITHOUT_REASONING`, off until measured.

Measured: 68-74% of each run's output tokens were reasoning, and the acceptance review's were all reasoning. The
switch is an efficiency change, so it starts off and is kept only with no loss in quality on its on/off pairs.
"""
from __future__ import annotations

import inspect

from langchain_openai import ChatOpenAI

from app import switches
from app.agents import reviews_without_reasoning
from app.graph import acceptance_nodes
from app.observability import provenance


def _model():
    return ChatOpenAI(model="local-model", base_url="http://localhost:9/v1", api_key="x")


def test_off_by_default_and_listed_as_an_efficiency_switch(monkeypatch):
    monkeypatch.delenv("REVIEWS_WITHOUT_REASONING", raising=False)
    assert reviews_without_reasoning.ON_BY_DEFAULT is False
    assert switches.group_of("REVIEWS_WITHOUT_REASONING") == "Efficiency"
    assert "REVIEWS_WITHOUT_REASONING" not in switches.EXPERIMENTS_ON


def test_off_leaves_the_model_as_it_is(monkeypatch):
    monkeypatch.setenv("REVIEWS_WITHOUT_REASONING", "off")
    model = _model()
    assert reviews_without_reasoning.the_review_model(model) is model


def test_on_sends_the_reasoning_switch(monkeypatch):
    monkeypatch.setenv("REVIEWS_WITHOUT_REASONING", "on")
    from app.agents import thinking

    monkeypatch.setattr(thinking, "least_reasoning_effort", lambda model: "none")
    reviewed = reviews_without_reasoning.the_review_model(_model())
    assert reviewed.extra_body["chat_template_kwargs"]["enable_thinking"] is False
    assert reviewed.extra_body["reasoning_effort"] == "none"


def test_the_acceptance_review_takes_its_model_through_the_switch():
    assert "model=the_review_model(ctx.judgement_model)" in inspect.getsource(acceptance_nodes)


def test_on_with_no_judgement_model_builds_the_default_one_without_reasoning(monkeypatch):
    # Measured on the switch's first run: the judgement model was None, the switch returned it unchanged, and the
    # review reasoned as configured.
    monkeypatch.setenv("REVIEWS_WITHOUT_REASONING", "on")
    from app import models
    from app.agents import thinking

    monkeypatch.setattr(models, "build_default_chat_model", _model)
    monkeypatch.setattr(thinking, "least_reasoning_effort", lambda model: "none")
    reviewed = reviews_without_reasoning.the_review_model(None)
    assert reviewed is not None
    assert reviewed.extra_body["chat_template_kwargs"]["enable_thinking"] is False


def test_off_with_no_judgement_model_leaves_it_to_the_stage(monkeypatch):
    monkeypatch.setenv("REVIEWS_WITHOUT_REASONING", "off")
    assert reviews_without_reasoning.the_review_model(None) is None
