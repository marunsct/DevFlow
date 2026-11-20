"""With `SUMMARISE_LATER_WITH_HEADROOM` on, a stage's conversation is rewritten later, never past the window.

Measured on a testing stage of a Java product served with a 91,776-token window: the summariser fired at 50,265
tokens and rewrote the conversation every two to five model calls, so files just read were read again.
"""

from __future__ import annotations

import json

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import HumanMessage

from app.agents.context_budget import ContextBudget

WINDOW = 91_776
USUAL = 50_265
CEILING = 62_832


@pytest.fixture
def stage(monkeypatch, tmp_path):
    """A stage's summariser built for a model with a 91,776-token window."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", str(WINDOW))
    monkeypatch.delenv("CTX_SOFT_TRIGGER_RATIO", raising=False)
    monkeypatch.setattr("app.agents.context_budget.context_window", lambda environment=None: WINDOW)
    monkeypatch.setattr("app.agents.role_agent.build_default_chat_model", lambda *a, **k: GenericFakeChatModel(messages=iter([])))

    def build(switch: str):
        monkeypatch.setenv("SUMMARISE_LATER_WITH_HEADROOM", switch)
        from app.agents.role_agent import _compaction_middleware

        (middleware,) = _compaction_middleware("specialist_testing")
        return middleware

    return build


def test_the_window_gives_the_stage_the_ceiling_this_test_is_written_for():
    assert ContextBudget.from_window(WINDOW).input_ceiling_tokens == CEILING


MESSAGES = [HumanMessage(content="hello")]


def _first_token_count_rewritten(middleware) -> int:
    """The smallest request, in tokens, at which the stage's conversation is rewritten."""
    low, high = 1, WINDOW
    while low < high:
        middle = (low + high) // 2
        if middleware._should_summarize(MESSAGES, middle):
            high = middle
        else:
            low = middle + 1
    return low


def test_with_the_switch_off_the_conversation_is_rewritten_at_the_usual_trigger(stage):
    assert _first_token_count_rewritten(stage("off")) == USUAL


def test_with_the_switch_on_the_conversation_is_rewritten_later(stage):
    assert _first_token_count_rewritten(stage("on")) == 59_690


def test_the_later_trigger_leaves_the_reply_s_room_in_the_window(stage):
    budget = ContextBudget.from_window(WINDOW)

    assert _first_token_count_rewritten(stage("on")) + budget.max_output_tokens < WINDOW


def test_a_trigger_already_past_the_later_one_is_left_as_it_was(stage, monkeypatch):
    monkeypatch.setenv("CTX_SOFT_TRIGGER_RATIO", "0.95")
    usual = _first_token_count_rewritten(stage("off"))

    assert _first_token_count_rewritten(stage("on")) == usual


def test_a_window_with_no_room_beyond_the_usual_trigger_is_not_changed(monkeypatch):
    from app.agents import summarise_later

    monkeypatch.setenv("SUMMARISE_LATER_WITH_HEADROOM", "on")

    assert summarise_later.trigger_tokens(usual=1_000, input_ceiling=1_000) == 1_000


def test_the_stage_is_noted_once_when_a_request_passes_the_usual_trigger_and_is_kept_whole(stage, monkeypatch, tmp_path):
    monkeypatch.setattr("app.models.model_pin.current_run_id", lambda: "run-x")
    monkeypatch.setattr("app.observability.transcript._stage_from_config", lambda fallback: "specialist_testing_5")
    middleware = stage("on")
    messages = [HumanMessage(content="hello")]

    for tokens in (USUAL + 1, USUAL + 2_000, 59_000):
        assert middleware._should_summarize(messages, tokens) is False
    records = [json.loads(line) for line in (tmp_path / "transcripts" / "run-x.jsonl").read_text().splitlines()]

    assert [(r["kind"], r["stage"]) for r in records] == [("summarised_later", "specialist_testing_5")]


def test_no_note_is_made_below_the_usual_trigger_or_with_the_switch_off(stage, monkeypatch, tmp_path):
    monkeypatch.setattr("app.models.model_pin.current_run_id", lambda: "run-y")
    messages = [HumanMessage(content="hello")]

    stage("on")._should_summarize(messages, USUAL - 1)
    stage("off")._should_summarize(messages, USUAL + 1_000)

    assert not (tmp_path / "transcripts" / "run-y.jsonl").exists()


def test_the_note_is_read_as_the_switch_having_acted(stage, monkeypatch, tmp_path):
    from app.observability import switch_firing

    monkeypatch.setattr("app.models.model_pin.current_run_id", lambda: "run-z")
    stage("on")._should_summarize([HumanMessage(content="hello")], USUAL + 1)
    line = (tmp_path / "transcripts" / "run-z.jsonl").read_text().splitlines()[0]

    assert switch_firing.fired([json.loads(line)]) == ["SUMMARISE_LATER_WITH_HEADROOM"]
