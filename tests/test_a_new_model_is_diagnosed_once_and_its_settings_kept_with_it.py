"""A model not seen before is diagnosed - tools forced and offered, reasoning - and what it needs is kept with it and used.

The harness learnt that a server refuses a forced tool from a failed call in
the run, one process at a time; that a model writes a name never offered, from
refusals; how hard a model reasons, from a probe per process. A new model is
now asked a few small questions once, and the settings they call for are kept
beside its other measurements and applied when a run starts on it.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from app.models import diagnostics, registry, server_profile

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.fixture(autouse=True)
def _data(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def _completion(calls=None, content="", tokens=5):
    return {"choices": [{"finish_reason": "tool_calls" if calls else "stop",
                         "message": {"content": content, "tool_calls": calls}}],
            "usage": {"completion_tokens": tokens}}


def _call(name, arguments):
    return [{"function": {"name": name, "arguments": arguments}}]


class _Server:
    """A model that calls tools well when offered and writes nothing readable when forced."""

    def __init__(self):
        self.sent = []

    def create(self, **payload):
        self.sent.append(payload)
        if payload.get("tools"):
            names = [t["function"]["name"] for t in payload["tools"]]
            if payload.get("tool_choice") not in (None, "auto"):
                return _completion(content="<function=get_weather><parameter=city>")
            if "write_artifact" in names:
                return _completion(_call("edit_file", '{"path": "notes.txt"}'))
            return _completion(_call("get_weather", '{"city": "Paris"}'))
        thinking_off = (payload.get("extra_body") or {}).get("chat_template_kwargs", {}).get("enable_thinking") is False
        return _completion(tokens=8 if thinking_off or payload.get("reasoning_effort") == "none" else 400)


def _model(server):
    return SimpleNamespace(model_name="new-model", openai_api_base="http://server/v1",
                           root_client=SimpleNamespace(chat=SimpleNamespace(completions=server)))


def test_a_model_that_cannot_be_forced_has_its_structured_answers_offered():
    diagnosis = diagnostics.diagnose(_model(_Server()), "new-model")
    by = {c.name: c for c in diagnosis.checks}

    assert by["tools offered"].works
    assert not by["a tool required"].works and not by["one tool named"].works
    assert by["only offered names"].notes[0] == "called `edit_file`, not `write_artifact` (not offered)"
    assert diagnosis.settings.structured_answers == "offered"
    assert diagnosis.settings.least_reasoning_effort == "none"
    assert diagnosis.settings.template_thinking_switch


def test_the_diagnosis_is_kept_with_the_model_and_applied_from_it(monkeypatch):
    from app import models

    monkeypatch.setattr(models, "_NO_FORCED_TOOL_WHILE_THINKING", set())
    registry.record_edit_rates("new-model", {"whole": 1.0, "edit": 1.0})
    server = _Server()

    first = diagnostics.diagnose_if_new(_model(server))
    asked = len(server.sent)
    again = diagnostics.diagnose_if_new(_model(server))

    assert asked > 0 and len(server.sent) == asked  # diagnosed once
    assert again.settings == first.settings
    assert ("http://server/v1", "new-model") in models._NO_FORCED_TOOL_WHILE_THINKING
    assert registry.measured_edit_rates("new-model") == {"whole": 1.0, "edit": 1.0}


def test_a_model_forced_well_keeps_its_answers_forced():
    checks = [diagnostics.Check(n, 3, 3) for n in ("tools offered", "a tool required", "one tool named",
                                                   "one tool named, thinking off", "only offered names")]
    assert diagnostics.settled(checks, {}).structured_answers == "forced"


def test_a_coder_model_with_words_before_coder_is_its_family():
    assert registry.profile_for("qwen3.8-flash-next-coder-iq1_m").family == "qwen3-coder"
    assert registry.profile_for("Qwen3.6-35B-A3B").family == "qwen3"


def test_another_model_on_the_same_server_is_a_change():
    before = server_profile.ServerProfile(slots=1, slot_context=8192, model="a.gguf")
    after = server_profile.ServerProfile(slots=1, slot_context=8192, model="b.gguf")
    assert server_profile.what_changed(before, after) == ["model a.gguf -> b.gguf"]


def test_the_questions_use_none_of_the_banned_words():
    for text in (diagnostics._ASK_WEATHER, diagnostics._ASK_EDIT, diagnostics._QUESTION):
        assert not BANNED.search(text)


def test_the_measured_reasoning_switch_is_used_without_asking_again(monkeypatch):
    from app.agents import thinking

    monkeypatch.setattr(thinking, "_least_effort", {})
    diagnosis = diagnostics.diagnose(_model(_Server()), "new-model")
    diagnostics.apply(_model(_Server()), diagnosis)

    assert thinking._least_effort[("http://server/v1", "new-model")] == "none"


class _Reads_first(_Server):
    """Reads the file it is asked to change before writing it, as a careful model does."""

    def create(self, **payload):
        names = [t["function"]["name"] for t in payload.get("tools") or []]
        if "write_artifact" in names and "read_file" in names and len(names) == 2:
            self.sent.append(payload)
            return _completion(_call("read_file", '{"file_path": "notes.txt"}'))
        return super().create(**payload)


def test_calling_another_offered_tool_first_is_not_a_made_up_name():
    """LFM2.5 read the file before editing it; the advice said it called tools that were not offered."""
    diagnosis = diagnostics.diagnose(_model(_Reads_first()), "careful-model")
    by = {c.name: c for c in diagnosis.checks}

    assert by["only offered names"].works
    assert not any("not offered" in line for line in diagnosis.settings.advice)


def test_the_advice_names_which_stage_shaped_check_fell_short():
    checks = [diagnostics.Check(n, 3, 3) for n in ("tools offered", "a tool required", "one tool named",
                                                   "one tool named, thinking off", "only offered names",
                                                   "a structured answer forced")]
    checks += [diagnostics.Check("forced after a long request", 2, 1), diagnostics.Check("a structured answer, offered", 3, 0)]
    advice = " ".join(diagnostics.settled(checks, {}).advice)
    assert "forced after a long request 1/2" in advice and "alike" not in advice
