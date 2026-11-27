"""A model's diagnosis says what the model did, not what its server did or what the questions' wording did (DX.1-DX.5).

Read from the eleven kept diagnoses (2026-11-27 diagnosis design, section 2.3): one local diagnosis lost 27 of 36
tries to 503s ("server_draining") and dropped connections and was scored "weak" at 0.139; a hosted model's 413s made
it "weak" at 0.583; a guide was kept when three tries rose by one, which a line with no effect does about one time
in three, and kept lines took other checks from 3/3 to 0/3 and stayed on; two checks failed on nearly every model, so
the best score ever kept was 0.806 and no model could be "strong"; a reasoning budget was kept "usable" with no reply
to show it; and a record was served to any server answering to the model's name, whatever template it ran.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import openai
import pytest
from langchain_core.messages import HumanMessage

from app.models import CompatibleChatOpenAI, deep_diagnosis, diagnostics, guidance, server_profile
from tests.diagnosis_fakes import StageChecks, ToolChecks, model, told

CAPTURED = Path(__file__).parent / "captured"
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
ADDRESS = "http://model-server:2001/v1"


@pytest.fixture(autouse=True)
def _a_fresh_data_dir(tmp_path, monkeypatch):
    from app import models
    from app.models import named_answer, reasoning_budget

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("REASONING_BUDGET", "on")
    monkeypatch.setattr(models, "_NAMED_CHOICE_BECOMES_REQUIRED", set())
    monkeypatch.setattr(models, "_NO_FORCED_TOOL_WHILE_THINKING", set())
    monkeypatch.setattr(named_answer, "HONOURED", set())
    monkeypatch.setattr(reasoning_budget, "ENFORCED", set())
    monkeypatch.setattr(reasoning_budget, "OFF_BUDGETS", {})
    server_profile.forget()
    yield
    server_profile.forget()


def _status_error(cls, status: int, text: str) -> Exception:
    response = httpx.Response(status, request=httpx.Request("POST", ADDRESS + "/chat/completions"))
    return cls(text, response=response, body=None)


#: Server errors as the kept diagnoses recorded them (their notes, cut where the record cut them).
SERVER_ERRORS = {
    "503 server draining": lambda: _status_error(
        openai.InternalServerError, 503, "Error code: 503 - {'error': {'type': 'server_error', 'code': 'server_draining', "),
    "dropped connection": lambda: openai.APIConnectionError(request=httpx.Request("POST", ADDRESS)),
    "413 request too large": lambda: _status_error(
        openai.APIStatusError, 413, "Error code: 413 - {'error': {'message': 'Request too large for model `openai/gpt"),
    "proxy timeout": lambda: _status_error(
        openai.InternalServerError, 500, "Proxy error: request timeout after 30.0s - server timeout of 600.0s exceeded"),
}


@pytest.mark.parametrize("error", list(SERVER_ERRORS))
def test_a_check_the_server_failed_is_not_measured_and_sets_no_tier(error):
    """Every try met the server's error: no failed tries, no verdict, no tier, no guide."""
    raised = SERVER_ERRORS[error]
    server = StageChecks({name: (lambda _s, _n: raised()) for name in deep_diagnosis.CHECKS})

    diagnosis = deep_diagnosis.diagnose(model(server), "a-model.gguf", workers=1)
    profile = guidance.chosen_by(diagnosis)

    assert all(r.tries == 0 and r.passed == 0 and r.unmeasured == deep_diagnosis.TRIES for r in diagnosis.baseline)
    assert profile.tier == "" and profile.score is None
    assert not any(profile.chosen.values()) and not profile.tail_reminder


def test_the_tries_the_server_answered_still_score_the_model():
    """A hosted model's long requests met 413s; it passed every other scored check, so it is strong, not weak."""
    too_large = SERVER_ERRORS["413 request too large"]
    server = StageChecks({"a rule kept after a long request": lambda _s, _n: too_large(),
                          "an answer within a stage's reply": lambda _s, _n: too_large()})

    profile = guidance.chosen_by(deep_diagnosis.diagnose(model(server), "a-model.gguf", workers=1))

    assert profile.tier == "strong" and profile.score == 1.0


def test_a_tool_choice_the_server_failed_keeps_the_default_form():
    """503s on every forced or required request say nothing of forcing: structured answers stay forced."""
    draining = SERVER_ERRORS["503 server draining"]
    server = ToolChecks(fail=lambda payload: draining() if payload.get("tool_choice") else None)

    diagnosis = diagnostics.diagnose(model(server), "a-model.gguf")
    named = next(c for c in diagnosis.checks if c.name == "one tool named")

    assert named.tries == 0 and named.unmeasured == diagnostics.TRIES
    assert diagnosis.settings.structured_answers == "forced"
    assert any("not measured" in line for line in diagnosis.settings.advice)


def test_a_guide_that_raised_three_tries_by_one_is_not_kept():
    """1 of 3 without the line, 2 of 3 with it: what a line with no effect shows about one time in three."""
    def plan_in_schema(system, n):
        return n < (2 if told(system, "answer_in_schema") else 1)

    diagnosis = deep_diagnosis.diagnose(model(StageChecks({"a plan answered in its schema": plan_in_schema})),
                                        "a-model.gguf", workers=1)

    assert "answer_in_schema" not in diagnosis.helped
    assert not guidance.chosen_by(diagnosis).chosen["answer_in_schema"]


def test_a_guide_that_takes_another_check_down_is_dropped():
    """The plan check rises from 1/3 to 3/3 with the schema line, but the long list falls from 3/3 to 0/3 with it, as
    one kept profile's did; the line is dropped and not given to the model."""
    def plan_in_schema(system, n):
        return told(system, "answer_in_schema") or n < 1

    def long_list(system, _n):
        return not told(system, "answer_in_schema")

    server = StageChecks({"a plan answered in its schema": plan_in_schema,
                          "a long list without repeating itself": long_list})
    diagnosis = deep_diagnosis.diagnose(model(server), "a-model.gguf", workers=1)

    assert "answer_in_schema" in diagnosis.helped
    assert not guidance.chosen_by(diagnosis).chosen["answer_in_schema"]
    assert not diagnosis.kept
    assert diagnosis.harmful == ("answer_in_schema",)


def test_a_model_that_passes_every_scored_check_is_strong_though_the_calibrating_checks_fail():
    """Ten checks at 3/3 and the two that nearly every model fails at 0/3: 0.833 counted over all of them."""
    def never(_system, _n):
        return False

    server = StageChecks({"the answer as a call, not as text": never, "a refusal heeded": never})

    diagnosis = deep_diagnosis.diagnose(model(server), "a-model.gguf", workers=1)
    profile = guidance.chosen_by(diagnosis)

    assert profile.tier == "strong" and profile.score == 1.0
    assert not profile.chosen["heed_refusals"] and not profile.chosen["answer_in_schema"]


class _BudgetServer:
    """A server that enforces a per-request reasoning budget; the budget questions reason `reasons[i]` tokens
    unbounded (question i, the first being the one of 1 to 50) and answer right when held to at least `needs`."""

    def __init__(self, reasons: list[int], needs: int):
        self.reasons, self.needs = reasons, needs
        self.asked: list[tuple[int, int | None]] = []
        self.questions: list[str] = []
        self.tools = ToolChecks()

    def create(self, **payload):
        asked = payload["messages"][-1]["content"]
        if payload.get("tools") or "digits of every whole number" not in asked:
            return self.tools.create(**payload)
        rung = 0 if "1 to 50" in asked else 1 if "1 to 200" in asked else 2
        right = {0: "330", 1: "1902", 2: "13501"}[rung]
        budget = (payload.get("extra_body") or {}).get("reasoning_budget_tokens")
        self.asked.append((rung, budget))
        self.questions.append(asked)
        reasons = self.reasons[rung]
        if budget is None or budget >= reasons:
            return {"choices": [{"finish_reason": "stop", "message": {"content": right, "reasoning_content": "x" * 4 * reasons}}],
                    "usage": {"completion_tokens": reasons + 2}}
        ended = payload["extra_body"]["reasoning_budget_message"]
        return {"choices": [{"finish_reason": "stop", "message": {
            "content": right if budget >= self.needs else "12", "reasoning_content": "x" * 4 * budget + ended}}],
            "usage": {"completion_tokens": budget + 24}}


def _stage_budget(diagnosis) -> int | None:
    client = CompatibleChatOpenAI(model="a-model.gguf", base_url=ADDRESS, api_key="k", max_retries=0, max_tokens=32_000)
    diagnostics.apply(client, diagnosis)
    payload = client._get_request_payload([HumanMessage(content="write the specification")])
    return (payload.get("extra_body") or {}).get("reasoning_budget_tokens")


def test_a_budget_no_reply_showed_usable_is_not_measured_and_holds_no_stage_call():
    """The budget questions reason about 225 tokens however long: no reply was ever held to the moderate budget."""
    server = _BudgetServer(reasons=[225, 230, 240], needs=100)

    diagnosis = diagnostics.diagnose(model(server, base=ADDRESS), "a-model.gguf")

    assert diagnosis.settings.reasoning_budget
    assert diagnosis.settings.reasoning_budget_usable is None
    assert _stage_budget(diagnosis) is None


def test_the_budget_question_climbs_until_a_reply_shows_the_budget_usable():
    """The first question reasons 225 tokens, the second 1,900: the moderate budget is asked on the second."""
    server = _BudgetServer(reasons=[225, 1_900, 6_000], needs=1_000)

    diagnosis = diagnostics.diagnose(model(server, base=ADDRESS), "a-model.gguf")

    assert server.asked == [(0, None), (0, 64), (0, 0), (1, None), (1, 1_280)]
    assert diagnosis.settings.reasoning_budget_usable is True
    assert _stage_budget(diagnosis) == 20_000


def test_the_longer_budget_questions_use_none_of_the_banned_words():
    server = _BudgetServer(reasons=[225, 230, 240], needs=100)

    diagnostics.diagnose(model(server, base=ADDRESS), "a-model.gguf")

    assert len(set(server.questions)) == 3
    assert not any(BANNED.search(question) for question in server.questions)


def _serve(monkeypatch, props: dict) -> None:
    """The model server answers `/props` with `props`, and nothing else of itself."""
    monkeypatch.setenv("OPENAI_BASE_URL", ADDRESS)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setattr(server_profile, "read", lambda *args, **kwargs: server_profile.from_props(props))
    server_profile.forget()
    server_profile.record()


def test_a_record_measured_on_another_chat_template_is_not_served(monkeypatch):
    captured = json.loads((CAPTURED / "llama-cpp-props-one-slot-behind-a-balancer.json").read_text(encoding="utf-8"))
    name = "Inkling-2-Mini-UD-Q4_K_M.gguf"
    _serve(monkeypatch, captured)
    diagnostics.keep(diagnostics.diagnose(model(ToolChecks(), name=name, base=ADDRESS), name))
    deep_diagnosis.keep(deep_diagnosis.diagnose(model(StageChecks(), name=name, base=ADDRESS), name, workers=1))
    assert diagnostics.recorded(name) is not None and deep_diagnosis.recorded(name) is not None

    _serve(monkeypatch, {**captured, "chat_template": captured["chat_template"] + "{# another revision #}"})

    assert diagnostics.recorded(name) is None
    assert deep_diagnosis.recorded(name) is None


def test_a_record_kept_on_the_same_model_and_template_is_served_though_the_slots_changed(monkeypatch):
    """A balancer whose second instance is back reads twice the slots: the model's habits are the same."""
    captured = json.loads((CAPTURED / "llama-cpp-props-one-slot-behind-a-balancer.json").read_text(encoding="utf-8"))
    name = "Inkling-2-Mini-UD-Q4_K_M.gguf"
    _serve(monkeypatch, captured)
    diagnostics.keep(diagnostics.diagnose(model(ToolChecks(), name=name, base=ADDRESS), name))

    _serve(monkeypatch, {**captured, "total_slots": 2})

    assert diagnostics.recorded(name) is not None
