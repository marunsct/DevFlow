"""With `REPLY_ROOM_SIZED_PER_ROLE` on, the input room a stage holds back for its reply follows the role's measured replies.

Measured: one number (32,000 tokens on a 91,776-token window) was held back for every role, though a specialist's
replies run to 1,657 tokens at the 90th percentile, so its conversation was rewritten at 43,020 tokens.
"""

from __future__ import annotations

import json

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import HumanMessage

from app.agents.context_budget import ContextBudget

WINDOW = 91_776
MESSAGES = [HumanMessage(content="hello")]


@pytest.fixture
def stage(monkeypatch, tmp_path):
    """A role's summariser built for a model with a 91,776-token window and a 32,000-token reply ceiling."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", str(WINDOW))
    monkeypatch.setenv("MODEL_MAX_OUTPUT_TOKENS", "32000")
    monkeypatch.delenv("CTX_SOFT_TRIGGER_RATIO", raising=False)
    monkeypatch.delenv("CTX_MAX_TOKENS", raising=False)
    monkeypatch.delenv("SUMMARISE_LATER_WITH_HEADROOM", raising=False)
    monkeypatch.setattr("app.agents.context_budget.context_window", lambda environment=None: WINDOW)
    monkeypatch.setattr("app.agents.role_agent.build_default_chat_model", lambda *a, **k: GenericFakeChatModel(messages=iter([])))

    def build(role: str, switch: str):
        monkeypatch.setenv("REPLY_ROOM_SIZED_PER_ROLE", switch)
        from app.agents.role_agent import _compaction_middleware

        (middleware,) = _compaction_middleware(role)
        return middleware

    return build


def _rewritten_at(middleware) -> int:
    low, high = 1, WINDOW
    while low < high:
        middle = (low + high) // 2
        if middleware._should_summarize(MESSAGES, middle):
            high = middle
        else:
            low = middle + 1
    return low


def test_the_reply_ceiling_this_test_is_written_for_is_32000():
    assert ContextBudget.from_window(WINDOW, max_output_tokens=32_000).input_ceiling_tokens == 53_776


def test_with_the_switch_off_a_specialist_is_rewritten_where_it_was(stage):
    assert _rewritten_at(stage("specialist_testing", "off")) == 43_020


@pytest.mark.parametrize("role, reserved", [
    ("specialist_testing", 9_000),
    ("security_advisor", 17_000),
    ("scrum_master", 25_000),
    ("principal_architect", 30_000),
])
def test_with_the_switch_on_a_role_holds_back_what_its_replies_need(stage, role, reserved):
    ceiling = 53_776 + 32_000 - reserved

    assert _rewritten_at(stage(role, "on")) == int(ceiling * 0.8)


@pytest.mark.parametrize("role", ["technical_lead", "acceptance_reviewer", "a_role_with_no_row"])
def test_a_role_whose_reply_needs_the_whole_reservation_or_has_no_data_is_unchanged(stage, role):
    assert _rewritten_at(stage(role, "on")) == _rewritten_at(stage(role, "off"))


def test_the_model_s_reply_ceiling_is_not_lowered(stage, monkeypatch):
    stage("specialist_testing", "on")

    assert ContextBudget.resolve().max_output_tokens == 32_000


def test_a_set_input_ceiling_is_not_moved(stage, monkeypatch):
    monkeypatch.setenv("CTX_MAX_TOKENS", "40000")

    assert _rewritten_at(stage("specialist_testing", "on")) == 32_000


def test_the_stage_is_noted_once_with_the_reservation_used(stage, monkeypatch, tmp_path):
    monkeypatch.setattr("app.models.model_pin.current_run_id", lambda: "run-r")
    monkeypatch.setattr("app.observability.transcript._stage_from_config", lambda fallback: "specialist_testing_5")
    middleware = stage("specialist_testing", "on")

    for tokens in (10, 20, 30):
        middleware._should_summarize(MESSAGES, tokens)
    records = [json.loads(line) for line in (tmp_path / "transcripts" / "run-r.jsonl").read_text().splitlines()]

    assert [(r["kind"], r["stage"], r["reserved_tokens"]) for r in records] == [("reply_room", "specialist_testing_5", 9_000)]


def test_the_note_is_read_as_the_switch_having_acted(stage, monkeypatch, tmp_path):
    from app.observability import switch_firing

    monkeypatch.setattr("app.models.model_pin.current_run_id", lambda: "run-s")
    stage("specialist_testing", "on")._should_summarize(MESSAGES, 10)
    line = (tmp_path / "transcripts" / "run-s.jsonl").read_text().splitlines()[0]

    assert switch_firing.fired([json.loads(line)]) == ["REPLY_ROOM_SIZED_PER_ROLE"]


def test_with_the_switch_off_nothing_is_noted(stage, monkeypatch, tmp_path):
    monkeypatch.setattr("app.models.model_pin.current_run_id", lambda: "run-t")
    stage("specialist_testing", "off")._should_summarize(MESSAGES, 10)

    assert not (tmp_path / "transcripts" / "run-t.jsonl").exists()
