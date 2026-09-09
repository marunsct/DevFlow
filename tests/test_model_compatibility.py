"""Wire-format compatibility with OpenAI-*compatible* servers.

LangChain serializes a message's `name` onto the request for `system`, `user`
and `assistant` roles. The OpenAI API tolerates it; several compatible servers
(LM Studio among them) apply the stricter reading and reject the entire
request:

    400 - messages.2: Value error, "name" is only valid on role="tool" messages.

That is fatal, not cosmetic - the request never reaches the model, so the whole
stage fails. deepagents sets `name` to the agent's own name as bookkeeping and
no prompt here addresses a named participant, so dropping it costs nothing.
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from app.models import CompatibleChatOpenAI


@pytest.fixture
def model():
    return CompatibleChatOpenAI(
        base_url="http://example.invalid/v1", api_key="test-key", model="test-model"
    )


def _payload(model, messages):
    return model._get_request_payload(messages)["messages"]


@pytest.mark.parametrize(
    "message",
    [
        SystemMessage("s", name="product_manager"),
        HumanMessage("h", name="product_manager"),
        AIMessage("a", name="product_manager"),
    ],
)
def test_name_is_dropped_from_every_non_tool_role(model, message):
    (sent,) = _payload(model, [message])

    assert "name" not in sent


def test_the_stock_client_would_have_sent_it():
    """Guards the premise: if LangChain stops emitting `name`, this override is
    dead weight and should be removed rather than left to rot."""
    stock = ChatOpenAI(base_url="http://example.invalid/v1", api_key="k", model="m")

    (sent,) = _payload(stock, [HumanMessage("h", name="product_manager")])

    assert sent["name"] == "product_manager"


def test_everything_else_about_the_message_survives(model):
    (sent,) = _payload(model, [HumanMessage("the actual content", name="pm")])

    assert sent["role"] == "user"
    assert sent["content"] == "the actual content"


def test_a_message_without_a_name_is_untouched(model):
    (sent,) = _payload(model, [HumanMessage("plain")])

    assert sent == {"role": "user", "content": "plain"}


def test_a_tool_result_keeps_what_identifies_it(model):
    """LangChain identifies tool results by `tool_call_id`, not `name`, so there
    is nothing to strip - but the filter must not damage them either."""
    (sent,) = _payload(model, [ToolMessage("result", tool_call_id="call-1", name="read_file")])

    assert sent["role"] == "tool"
    assert sent["tool_call_id"] == "call-1"
    assert sent["content"] == "result"


def test_a_whole_conversation_is_cleaned(model):
    sent = _payload(model, [
        SystemMessage("s", name="a"),
        HumanMessage("h", name="a"),
        AIMessage("a", name="a"),
        ToolMessage("t", tool_call_id="c1"),
    ])

    assert [m["role"] for m in sent] == ["system", "user", "assistant", "tool"]
    assert not any("name" in m for m in sent)


def test_tool_calls_still_reach_the_model(model):
    """The override rebuilds nothing; it only removes one key."""
    ai = AIMessage(
        content="",
        tool_calls=[{"name": "read_file", "args": {"path": "a.py"}, "id": "call-1"}],
        name="backend_specialist",
    )

    (sent,) = _payload(model, [ai])

    assert "name" not in sent
    assert sent["tool_calls"][0]["function"]["name"] == "read_file"


def test_the_factory_builds_the_compatible_client(monkeypatch):
    """A stock ChatOpenAI anywhere in the factory reintroduces the failure."""
    from app.config import load_settings
    from app.models import build_default_chat_model

    settings = load_settings({
        "LLM_PROVIDER": "local",
        "OPENAI_BASE_URL": "http://example.invalid/v1",
        "OPENAI_API_KEY": "k",
        "OPENAI_MODEL": "m",
    })

    built = build_default_chat_model(settings)

    # The router may wrap it, so check the concrete clients it was given.
    from app.models.router import ModelRouter

    clients = [
        entry["model"]
        for router in ModelRouter.all_routers().values()
        for entry in router._models
    ]
    openai_clients = [c for c in clients if isinstance(c, ChatOpenAI)]
    assert openai_clients, "no OpenAI client was constructed"
    assert all(isinstance(c, CompatibleChatOpenAI) for c in openai_clients)
    assert built is not None
