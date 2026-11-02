"""An agent is built on a chat model; a model with fallbacks hands over its primary.

Measured live: once a fallback model was configured, the default model became a `RunnableWithFallbacks`, the agent
library read it as a model name, and every new run failed at its first stage with `'CompatibleChatOpenAI' object has
no attribute 'count'`.
"""
from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.agents.role_agent import a_chat_model


def test_a_model_with_fallbacks_hands_over_its_primary():
    primary = FakeListChatModel(responses=["a"])
    chain = primary.with_fallbacks([FakeListChatModel(responses=["b"])])

    assert not isinstance(chain, BaseChatModel)
    assert a_chat_model(chain) is primary


def test_a_chat_model_is_given_as_it_is():
    primary = FakeListChatModel(responses=["a"])

    assert a_chat_model(primary) is primary


def test_the_agent_builder_uses_it():
    from pathlib import Path

    from app.agents import role_agent

    text = Path(role_agent.__file__).read_text()
    assert "model=a_chat_model(selected_model)" in text
