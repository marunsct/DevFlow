"""A model that does not do as stages ask is given guidance - only the lines measured to help - in every stage's prompt.

One model measured in four runs answered plans as near misses of their schema,
wrote answers as text, looped on one phrase for 107,596 tokens and wrote
product code from the acceptance writer by a shell command. The deep diagnosis
asks the model questions shaped like those stages, tries each candidate line
where it fell short, and keeps the lines that raised its pass count, as the
model's row of the plugin-instruction table.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest

from app.models import deep_diagnosis, model_guidance

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.fixture(autouse=True)
def _data(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MODEL_GUIDANCE", "on")


def _completion(content="", calls=None, finish="stop"):
    return {"choices": [{"finish_reason": finish, "message": {"content": content, "tool_calls": calls}}],
            "usage": {"completion_tokens": 10}}


def _call(name, args):
    return [{"function": {"name": name, "arguments": json.dumps(args)}}]


class _Obeys_only_when_told:
    """Writes product code from the acceptance role unless told to keep to its role; loops unless told not to."""

    def __init__(self):
        self.sent = []

    def create(self, **payload):
        self.sent.append(payload)
        system = payload["messages"][0]["content"]
        user = payload["messages"][-1]["content"] if payload["messages"][-1]["role"] == "user" else ""
        names = [t["function"]["name"] for t in payload.get("tools") or []]
        if "acceptance test author" in system:
            if "never write or change another part's files" in system:
                return _completion("The fault is in app/routes.py, another role's file.")
            return _completion(calls=_call("write_artifact", {"relative_path": "app/routes.py", "content": "201"}))
        if "List 40" in user:
            if "Never write the same line" in system:
                return _completion("\n".join(f"case {n}" for n in range(40)))
            return _completion("case - " * 2_000, finish="length")
        if "SprintPlanOutput" in names:
            return _completion(calls=_call("SprintPlanOutput", {"sprints": []}))
        answer = next((n for n in names if n == "SpecialistOutput"), None)
        return _completion(calls=_call(answer, {"changed_files": ["app/routes.py"]}))


def _model(server):
    return SimpleNamespace(model_name="new-model", openai_api_base="http://server/v1",
                           root_client=SimpleNamespace(chat=SimpleNamespace(completions=server)))


def test_only_the_lines_that_helped_are_kept(monkeypatch):
    diagnosis = deep_diagnosis.diagnose(_model(_Obeys_only_when_told()), "new-model", workers=1)
    before = {r.check: r.passed for r in diagnosis.baseline}

    assert before["a role kept"] == 0 and before["a long list without repeating itself"] == 0
    kept = " ".join(diagnosis.kept)
    assert "never write or change another part's files" in kept and "Never write the same line" in kept
    assert "stop and give your answer straight away" not in kept  # it already stopped: nothing to help
    after = {r.check: r.passed for r in diagnosis.with_guidance}
    assert after["a role kept"] == deep_diagnosis.TRIES
    assert diagnosis.reply_ceiling == deep_diagnosis.LOOPING_MODEL_CEILING


def test_the_kept_lines_are_the_model_s_row_and_reach_every_stage(monkeypatch):
    from app.server.plugin_store import PluginStore

    rows: dict[str, str] = {}
    store = SimpleNamespace(update_instructions=lambda key, text: rows.__setitem__(key, text),
                            get_instructions=lambda key: rows.get(key))
    monkeypatch.setattr(PluginStore, "shared", classmethod(lambda cls: store))
    monkeypatch.setattr(model_guidance, "served_now", lambda: "new-model")

    deep_diagnosis.keep(deep_diagnosis.diagnose(_model(_Obeys_only_when_told()), "new-model", workers=1))

    assert model_guidance.guidance_key() == ["model:new-model"]
    from app.plugins.registry import get_plugin_instructions

    assert "Never write the same line" in get_plugin_instructions(["python", *model_guidance.guidance_key()])


def test_no_guidance_key_with_the_switch_off(monkeypatch):
    monkeypatch.setenv("MODEL_GUIDANCE", "off")
    assert model_guidance.guidance_key() == []
    assert model_guidance.ceiling_for(("http://server/v1", "new-model")) is None


def test_the_chosen_ceiling_reaches_a_request_the_deployment_leaves_uncapped(monkeypatch):
    from langchain_core.messages import HumanMessage

    from app.models import CompatibleChatOpenAI

    client = CompatibleChatOpenAI(model="new-model", base_url="http://server/v1", api_key="x", max_retries=0)
    model_guidance.set_ceiling(("http://server/v1", "new-model"), 40_000)
    try:
        payload = client._get_request_payload([HumanMessage(content="hi")])
    finally:
        model_guidance.set_ceiling(("http://server/v1", "new-model"), None)
    assert payload["max_tokens"] == 40_000


def test_every_candidate_line_and_check_prompt_uses_none_of_the_banned_words():
    for _label, line, _targets in deep_diagnosis.CANDIDATES:
        assert not BANNED.search(line), line
    assert not BANNED.search(deep_diagnosis._SPEC)
