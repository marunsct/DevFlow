"""Tests for breaking infinite jump_to_model loops, uncapped output tokens, and focused revision context."""

import re
import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from app.agents.settled_answer import build_settled_answer_middleware, BUDGET_STOP_MARKER
from app.models import CompatibleChatOpenAI
from app.agents.principal_architect import build_architecture_revision_request
from app.state import RepositoryContext
from app.documents import DocumentContent

BANNED_WORDS = re.compile(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", re.IGNORECASE)


class DummyOutput(BaseModel):
    summary: str = ""


def test_settled_answer_breaks_infinite_jump_to_model_loop():
    """Consecutive truncated replies must not loop jump_to=model indefinitely; must end the stage."""
    middleware = build_settled_answer_middleware(DummyOutput, "principal_architect")
    
    # Simulate a truncated reply with finish_reason='length' and empty content/tool_calls
    truncated_msg = AIMessage(
        content="",
        response_metadata={"finish_reason": "length"},
        id="m1",
    )
    
    # 3 consecutive truncated replies in messages
    state = {
        "messages": [
            HumanMessage(content="write specification"),
            truncated_msg,
            truncated_msg,
            truncated_msg,
        ]
    }
    
    decision = middleware.after_model(state, None)
    assert decision is not None
    # Must NOT keep jumping to model endlessly
    assert decision.get("jump_to") == "end"
    assert decision["messages"][0].additional_kwargs.get(BUDGET_STOP_MARKER) is True


def test_compatible_chat_openai_omits_max_tokens_when_uncapped():
    """When max_tokens is 0 or None, request payload must not include max_tokens or max_completion_tokens."""
    client = CompatibleChatOpenAI(
        model="qwen3.8-flash-next-coder-iq1_m",
        api_key="test-key",
        max_tokens=0,
    )
    payload = client._get_request_payload([HumanMessage(content="hi")])
    assert "max_tokens" not in payload
    assert "max_completion_tokens" not in payload


def test_build_architecture_revision_request_slims_context_and_has_no_banned_words():
    """Revision request should not bloat the prompt with 170k characters of duplicate text, and must have no banned words."""
    huge_spec = "{\n  \"field\": \"" + ("x" * 150_000) + "\"\n}"
    repo = RepositoryContext(branch="master", commit="1234567", root_path="/", status="clean")
    doc = DocumentContent(source_path="brief.md", source_type="markdown", text="Some constraints", truncated=False)
    
    req = build_architecture_revision_request(
        previous_specification_text=huge_spec,
        required_changes=["In data_contracts, change citation to UT-25."],
        product_intake_text="Product intake text",
        tools_and_models_text="Tools and models text",
        stack_selection_text="Stack text",
        repository=repo,
        document=doc,
    )
    content = req["messages"][-1]["content"]
    
    # Must not contain the full 150k dump
    assert len(content) < 50_000
    
    # Must contain the required change
    assert "UT-25" in content
    
    # Must ban prohibited words
    matches = BANNED_WORDS.findall(content)
    assert not matches, f"Found banned words in revision prompt: {matches}"
