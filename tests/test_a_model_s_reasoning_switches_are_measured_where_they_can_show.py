"""A model's reasoning switches and forced tools are measured where a working one can show (IK.1, IK.2, IK.6).

Measured on one llama.cpp server: the diagnosis asked "What is 12 plus 30?" and the model answered in 47 tokens as
served, 48 with `reasoning_effort` "none", 40 with "low", 38 with the template switch off - nothing to remove, so it
kept "not honoured" for every switch. The server's chat template reads the effort as its own argument, and a
top-level "none" erases it (the template then reasons at its default 0.9). The same server reads a named tool choice
as `auto`: "one tool named" passed 3 of 3 by the model's own choice, while a stage-shaped structured answer forced
by name passed 0 of 3 and with `required` 3 of 3 - and the diagnosis kept "forced".
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage

from app.agents import thinking
from app.models import CompatibleChatOpenAI, diagnostics

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
ADDRESS = "http://model-server:2001/v1"
MODEL = "a-reasoning-model.gguf"


@pytest.fixture(autouse=True)
def _what_a_diagnosis_applies_is_this_test_s(monkeypatch):
    """`diagnostics.apply` keeps what it learnt per server for the process: each test starts with none of it."""
    import importlib

    from app import models
    from app.models import named_answer

    monkeypatch.setattr(models, "_NAMED_CHOICE_BECOMES_REQUIRED", set())
    monkeypatch.setattr(models, "_NO_FORCED_TOOL_WHILE_THINKING", set())
    monkeypatch.setattr(named_answer, "HONOURED", set())
    try:
        reasoning_budget = importlib.import_module("app.models.reasoning_budget")
    except ImportError:  # the code before the budget existed
        return
    monkeypatch.setattr(reasoning_budget, "ENFORCED", set())
    monkeypatch.setattr(reasoning_budget, "OFF_BUDGETS", {})


@pytest.fixture(autouse=True)
def _data(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def _completion(calls=None, content="", tokens=5):
    return {"choices": [{"finish_reason": "tool_calls" if calls else "stop",
                         "message": {"content": content, "tool_calls": calls}}],
            "usage": {"completion_tokens": tokens}}


def _call(name, arguments):
    return [{"function": {"name": name, "arguments": json.dumps(arguments)}}]


class _Server:
    """A llama.cpp-like server: `required` enforced, a named choice read as `auto`; the reasoning question costs
    what `cost(payload)` says."""

    def __init__(self, cost):
        self.cost = cost

    def create(self, **payload):
        tools = [t["function"]["name"] for t in payload.get("tools") or []]
        if not tools:
            return _completion(content="18", tokens=self.cost(payload))
        required = payload.get("tool_choice") == "required"
        if "SpecialistOutput" in tools:
            if required:
                return _completion(_call("SpecialistOutput", {"changed_files": ["app/routes.py"]}))
            return _completion(_call("run_terminal_command", {"argument": "pytest -q"}))
        if "write_artifact" in tools and len(tools) == 2:
            return _completion(_call("write_artifact", {"relative_path": "notes.txt", "content": "This is a final."}))
        if "glob" in tools:
            return _completion(_call("read_file", {"file_path": "app/main.py"}))
        return _completion(_call("get_weather", {"city": "Paris"}))


def _model(server):
    return SimpleNamespace(model_name=MODEL, openai_api_base=ADDRESS,
                           root_client=SimpleNamespace(chat=SimpleNamespace(completions=server)))


def _way(payload) -> str:
    extra = payload.get("extra_body") or {}
    template = extra.get("chat_template_kwargs") or {}
    if "reasoning_budget_tokens" in extra:
        return f"budget {extra['reasoning_budget_tokens']}"
    if "reasoning_effort" in template:
        return f"template effort {template['reasoning_effort']}"
    if template.get("enable_thinking") is False:
        return "template thinking off"
    if payload.get("reasoning_effort"):
        return f"effort {payload['reasoning_effort']}"
    return "as served"


def _costing(default: int = 47, **tokens):
    """A cost per way of asking, by `_way` label with spaces as underscores; `default` for any other."""
    return lambda payload: tokens.get(_way(payload).replace(" ", "_"), default)


def test_a_question_answered_in_a_few_dozen_tokens_says_the_switches_are_not_measurable():
    server = _Server(_costing(as_served=47, effort_none=48, effort_low=40, template_thinking_off=38))

    diagnosis = diagnostics.diagnose(_model(server), MODEL)
    diagnostics.apply(_model(server), diagnosis)

    assert any("not measurable" in line for line in diagnosis.settings.advice)
    assert not any("not honoured" in line for line in diagnosis.settings.advice)
    # Nothing kept for the switches: the per-process probe measures them in a run.
    assert (ADDRESS, MODEL) not in thinking._least_effort


def test_an_effort_that_reasons_clearly_less_is_kept():
    server = _Server(_costing(900, effort_none=880, effort_low=250, template_effort_none=870))

    diagnosis = diagnostics.diagnose(_model(server), MODEL)

    assert diagnosis.settings.least_reasoning_effort == "low"
    assert diagnosis.settings.effort_route == "field"


def _template_reads_the_effort():
    """The template reads the effort only as its own argument; a top-level "none" erases it (as served, 0.9)."""
    return _Server(_costing(900, effort_low=600, template_effort_none=120))


def test_the_effort_the_template_reads_is_sent_as_its_argument_and_the_client_s_own_is_not_sent():
    diagnosis = diagnostics.diagnose(_model(_template_reads_the_effort()), MODEL)
    client = CompatibleChatOpenAI(model=MODEL, base_url=ADDRESS, api_key="k", max_retries=0, reasoning_effort="medium",
                                  extra_body={"chat_template_kwargs": {"enable_thinking": True}})
    diagnostics.apply(client, diagnosis)

    payload = thinking.without_reasoning(client)._get_request_payload([HumanMessage(content="x")])

    assert payload["extra_body"]["chat_template_kwargs"]["reasoning_effort"] == "none"
    assert "reasoning_effort" not in payload and "reasoning_effort" not in payload["extra_body"]


def test_a_top_level_none_that_reasons_as_much_as_as_served_is_never_kept_for_the_field():
    diagnosis = diagnostics.diagnose(_model(_template_reads_the_effort()), MODEL)

    assert (diagnosis.settings.least_reasoning_effort, diagnosis.settings.effort_route) == ("none", "template")


def test_a_level_the_server_lists_below_low_is_tried(monkeypatch):
    from app.models import server_profile

    props = json.loads(open("tests/captured/llama-cpp-props-one-slot-behind-a-balancer.json").read())
    monkeypatch.setattr(server_profile, "read", lambda *args, **kwargs: server_profile.from_props(props))
    server = _Server(_costing(900, effort_low=600, template_effort_none=500,
                              template_effort_minimal=300))

    diagnosis = diagnostics.diagnose(_model(server), MODEL)

    assert (diagnosis.settings.least_reasoning_effort, diagnosis.settings.effort_route) == ("minimal", "template")
    assert any("own default (0.9)" in line for line in diagnosis.settings.advice)


#: The checks as measured on the llama.cpp server that reads a named choice as `auto`: (name, tries, passed).
MEASURED = [diagnostics.Check(name, tries, passed) for name, tries, passed in (
    ("tools offered", 3, 3), ("a tool required", 3, 3), ("one tool named", 3, 3),
    ("one tool named, thinking off", 3, 3), ("only offered names", 3, 3),
    ("a structured answer forced", 3, 0), ("forced after a long request", 2, 0),
    ("a structured answer, offered", 3, 0), ("a structured answer, required", 3, 3))]


def test_a_named_choice_that_fails_where_required_works_is_sent_as_required_and_not_named(monkeypatch):
    from app import models
    from app.models.named_answer import HONOURED

    monkeypatch.setattr(models, "_NAMED_CHOICE_BECOMES_REQUIRED", set())
    settings = diagnostics.settled(MEASURED, {})
    diagnostics.apply(_model(None), diagnostics.Diagnosis(MODEL, "2026-11-27T00:00:00+00:00", tuple(MEASURED), {},
                                                          settings))

    assert settings.structured_answers == "required"
    assert (ADDRESS, MODEL) in models._NAMED_CHOICE_BECOMES_REQUIRED
    assert (ADDRESS, MODEL) not in HONOURED


def test_a_server_that_reads_a_named_choice_as_auto_is_told_by_a_tool_the_request_does_not_fit():
    diagnosis = diagnostics.diagnose(_model(_Server(_costing())), MODEL)
    by = {c.name: c for c in diagnosis.checks}

    assert by["one tool named"].works and not by["a named tool the request does not fit"].works
    assert diagnosis.settings.structured_answers == "required"


def test_the_reasoning_question_uses_none_of_the_banned_words():
    from app.models.reply_salvage import ENOUGH

    for text in (diagnostics._QUESTION, ENOUGH):
        assert not BANNED.search(text)
