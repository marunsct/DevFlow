"""How much a model reasons on replayed stage requests at each effort and budget sets its effort, budget and reply cap
per kind of call (DX.7).

Measured before it: design replies ran 30,000-44,000 tokens until a budget worked, about three hours a run; the
diagnosis's reasoning probe was one small puzzle (145 tokens as served, under its 200-token floor), so it kept
nothing, though the chat template reasons at 0.9 when nothing is sent.
"""
from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from app import models
from app.models import CompatibleChatOpenAI, capabilities, server_profile, steering_job
from tests.diagnosis_fakes import Everything, ToolChecks, completion, call, model

ADDRESS = "http://model-server:2001/v1"
NAME = "a-model.gguf"
READS = [{"type": "function", "function": {"name": name, "description": "Read.", "parameters": {
    "type": "object", "properties": {"file_path": {"type": "string"}}, "required": []}}}
    for name in ("read_file", "AnAnswer")]
#: The replay requests' reply caps: the quick tier's and a stage's.
CAPS = (4_000, 32_000)


class _Reasoning(ToolChecks):
    """A model whose reasoning on a stage request is 30,000 tokens as served and 1,500 at a low effort, held to a
    budget where one is sent; its replies call a tool it was offered. Its server enforces a budget: the small budget
    questions reason 225 tokens each, so they show the budget enforced and nothing of its use."""

    def __init__(self, as_served: int = 30_000, low: int = 1_500):
        super().__init__()
        self.as_served, self.low = as_served, low
        self.caps: list[int] = []

    def create(self, **payload):
        extra = payload.get("extra_body") or {}
        budget = extra.get("reasoning_budget_tokens")
        asked = str(payload["messages"][-1].get("content") or "")
        if "digits of every whole number" in asked and not payload.get("tools"):
            reasons = 225 if budget is None else min(budget, 225)
            ended = extra.get("reasoning_budget_message", "") if budget is not None else ""
            right = "330" if "1 to 50" in asked else "1902" if "1 to 200" in asked else "13501"
            return completion(right, reasoning="x" * 4 * reasons + ended, tokens=reasons + 10)
        if payload.get("max_tokens") not in CAPS or len(payload["messages"]) < 3:
            return super().create(**payload)
        self.caps.append(payload["max_tokens"])
        effort = payload.get("reasoning_effort") or (extra.get("chat_template_kwargs") or {}).get("reasoning_effort")
        reasons = self.low if effort in ("none", "minimal", "low") else self.as_served
        if isinstance(budget, int):
            reasons = min(reasons, budget)
        if reasons + 200 > payload["max_tokens"]:
            return completion("", reasoning="x" * 4 * payload["max_tokens"], finish="length",
                              tokens=payload["max_tokens"])
        return completion(calls=call("read_file", {"file_path": "README.md"}), reasoning="x" * 4 * reasons,
                          finish="tool_calls", tokens=reasons + 200)


@pytest.fixture(autouse=True)
def _a_fresh_deployment(tmp_path, monkeypatch):
    from app import models as app_models
    from app.models import named_answer, reasoning_budget

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MODEL_CALL_GATE_DIR", str(tmp_path / "gate"))
    monkeypatch.setenv("OPENAI_BASE_URL", ADDRESS)
    monkeypatch.setenv("MODEL_NAME", NAME)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("REASONING_BUDGET", "on")
    monkeypatch.setenv("PROFILE_FROM_DIAGNOSIS", "on")
    monkeypatch.setattr(app_models, "_NAMED_CHOICE_BECOMES_REQUIRED", set())
    monkeypatch.setattr(app_models, "_NO_FORCED_TOOL_WHILE_THINKING", set())
    monkeypatch.setattr(named_answer, "HONOURED", set())
    monkeypatch.setattr(reasoning_budget, "ENFORCED", set())
    monkeypatch.setattr(reasoning_budget, "OFF_BUDGETS", {})
    # The model card lookups reach the internet; they are not what is measured here.
    monkeypatch.setattr(capabilities, "fill", lambda *a, **k: {})
    found = server_profile.ServerProfile(slots=2, model=NAME, reasoning_effort_levels=("low", "medium", "high"),
                                         template_default_effort="0.9")
    monkeypatch.setattr(server_profile, "read", lambda *args, **kwargs: found)
    server_profile.forget()
    yield
    server_profile.forget()
    try:
        from app.models import diagnosis_profile

        diagnosis_profile.forget()
    except ImportError:
        pass


def _diagnosed(monkeypatch, server, full: bool = False) -> None:
    monkeypatch.setattr(models, "build_default_chat_model", lambda *a, **k: model(Everything(tools=server),
                                                                                  name=NAME, base=ADDRESS))
    steering_job.run(full=full) if full else steering_job.run()
    assert steering_job.status()["status"] == "idle", steering_job.status()


def _a_reading_call(effort: str | None = None) -> dict:
    client = CompatibleChatOpenAI(model=NAME, base_url=ADDRESS, api_key="k", max_retries=0, max_tokens=32_000,
                                  **({"reasoning_effort": effort} if effort else {}))
    return client._get_request_payload([HumanMessage(content="review the design")], tools=READS)


def _effort_sent(payload: dict) -> str | None:
    template = (payload.get("extra_body") or {}).get("chat_template_kwargs") or {}
    return template.get("reasoning_effort") or payload.get("reasoning_effort")


def test_a_model_that_reasons_past_its_reply_as_served_is_sent_the_effort_that_answers(monkeypatch):
    """As served the replayed requests reason past the 4,000-token reply and answer nothing; at the least listed
    effort they reason 1,500 and call a tool they were offered: that effort is sent, by the template's own argument."""
    _diagnosed(monkeypatch, _Reasoning())

    assert _effort_sent(_a_reading_call()) == "low"


def test_the_owner_s_run_effort_is_never_replaced(monkeypatch):
    _diagnosed(monkeypatch, _Reasoning())

    payload = _a_reading_call(effort="high")

    assert payload.get("reasoning_effort") == "high"
    assert not ((payload.get("extra_body") or {}).get("chat_template_kwargs") or {}).get("reasoning_effort")


def test_with_the_switch_off_no_effort_is_sent(monkeypatch):
    monkeypatch.setenv("PROFILE_FROM_DIAGNOSIS", "off")
    _diagnosed(monkeypatch, _Reasoning())

    assert _effort_sent(_a_reading_call()) is None


def test_a_budget_that_held_stage_requests_answering_sends_stage_calls_a_budget(monkeypatch):
    """The small budget questions showed the budget enforced and nothing of its use (DX.4); replayed stage requests
    held to it still called their tools, so a stage call is sent one."""
    _diagnosed(monkeypatch, _Reasoning())

    assert (_a_reading_call().get("extra_body") or {}).get("reasoning_budget_tokens") == 20_000


def test_the_full_tier_starts_only_from_the_settings_page(monkeypatch):
    from app.models import diagnosis_pool, dose_response

    server = _Reasoning()
    dose_response.measure_if_new(diagnosis_pool.handle(model(Everything(tools=server), name=NAME, base=ADDRESS)))
    assert set(server.caps) == {4_000}

    _diagnosed(monkeypatch, server, full=True)
    assert 32_000 in server.caps


def test_the_full_tier_sets_the_effort_and_a_budget_and_cap_from_stage_sized_replies(monkeypatch):
    """At a stage's cap the requests reason 30,000 tokens as served and 1,500 at low, all answering: low, and a budget
    and cap from the low replies."""
    from app.models import diagnosis_profile

    _diagnosed(monkeypatch, _Reasoning(), full=True)
    fields = diagnosis_profile.recorded(NAME)["fields"]

    assert fields["effort.reading"]["value"] == "low"
    assert fields["budget.reading"]["value"] == 2_000
    assert fields["cap.reading"]["value"] == 3_000
    payload = _a_reading_call()
    assert (payload.get("max_tokens") or payload.get("max_completion_tokens")) == 3_000
    assert payload["extra_body"]["reasoning_budget_tokens"] <= 2_000


def _replies(arm: str, reasoning: list[int], passed: list[bool], answer: int = 1_000) -> list[dict]:
    return [{"arm": arm, "measured": True, "passed": ok, "reasoning": r, "output": r + answer}
            for r, ok in zip(reasoning, passed)]


def test_the_rules_take_the_least_effort_that_answers_as_well_and_size_the_budget_from_its_replies():
    """The design's case: 30,000 tokens as served and 6,000 at low, every answer valid."""
    from app.models.dose_response import choose

    fields = choose(_replies("as served", [30_000, 30_500, 29_800], [True] * 3)
                    + _replies("effort low", [6_000, 6_100, 5_900], [True] * 3)
                    + _replies("effort medium", [18_000, 17_500, 18_200], [True] * 3), 32_000, True)

    assert fields["effort"]["value"] == "low"
    assert fields["budget"]["value"] == 7_000
    assert fields["cap"]["value"] == 9_000


def test_a_lower_effort_whose_answers_fail_more_is_not_taken():
    from app.models.dose_response import choose

    fields = choose(_replies("as served", [30_000] * 3, [True] * 3)
                    + _replies("effort low", [6_000] * 3, [True, False, False]), 32_000, True)

    assert "effort" not in fields
    # As served it answers: its budget is its own reasoning, never above the stage cap less its answer room.
    assert fields["budget"]["value"] == 20_000


def test_an_effort_the_model_ignores_is_not_taken():
    """Low reasoned 90% of as served: not a control that works."""
    from app.models.dose_response import choose

    fields = choose(_replies("as served", [10_000] * 3, [True] * 3)
                    + _replies("effort low", [9_000] * 3, [True] * 3), 32_000, False)

    assert fields == {}
