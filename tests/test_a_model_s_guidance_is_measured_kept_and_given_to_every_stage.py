"""A model is steered by general guidance - each item its own switch - chosen for it by measurement, and as much as its tier needs.

One model measured in four runs answered plans as near misses of their schema,
wrote answers as text, looped on one phrase for 107,596 tokens and wrote
product code from the acceptance writer; another chained shell commands and
read `/workspace/...` for a path it was given. The deep diagnosis asks a model
questions shaped like those stages, tries each catalogue item where it fell
short, and keeps a steering profile against the model: its tier, the items
chosen for it, the owner's overrides, and whether it is reminded at the end of
every request.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest

from app.models import deep_diagnosis, guidance, model_guidance

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.fixture(autouse=True)
def _data(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MODEL_GUIDANCE", "on")
    for guide in guidance.GUIDES:
        monkeypatch.setenv(guide.switch, "on")  # each is on in compose
    rows: dict[str, str] = {}
    store = SimpleNamespace(update_instructions=lambda key, text: rows.__setitem__(key, text),
                            get_instructions=lambda key: rows.get(key))
    from app.server.plugin_store import PluginStore

    monkeypatch.setattr(PluginStore, "shared", classmethod(lambda cls: store))
    monkeypatch.setattr(model_guidance, "served_now", lambda: "new-model")
    return rows


def _completion(content="", calls=None, finish="stop"):
    return {"choices": [{"finish_reason": finish, "message": {"content": content, "tool_calls": calls}}],
            "usage": {"completion_tokens": 10}}


def _call(name, args):
    return [{"function": {"name": name, "arguments": json.dumps(args)}}]


class _Obeys_only_when_told:
    """Writes product code from the acceptance role unless told to keep to its role; loops unless told not to;
    chains commands always (so its guide is chosen only when the tier is weak)."""

    def __init__(self):
        self.sent = []

    def create(self, **payload):
        self.sent.append(payload)
        system = payload["messages"][0]["content"]
        user = next((m["content"] for m in reversed(payload["messages"]) if m["role"] == "user"), "")
        names = [t["function"]["name"] for t in payload.get("tools") or []]
        if "acceptance test author" in system:
            if "never write or change another part's files" in system:
                return _completion("The fault is another role's.")
            return _completion(calls=_call("write_artifact", {"relative_path": "app/routes.py", "content": "201"}))
        if "List 40" in user:
            if "Never write the same line" in system:
                return _completion("\n".join(f"case {n}" for n in range(40)))
            return _completion("case - " * 2_000, finish="length")
        if "first lines of tasks-api/app.py" in user:
            return _completion(calls=_call("run_terminal_command", {"command": ["ls tasks-api && head tasks-api/app.py"]}))
        if "Read the project's app.py" in user:
            return _completion(calls=_call("read_file", {"file_path": "tasks-api/app.py"}))
        if "notes.txt" in user:
            return _completion(calls=_call("write_artifact", {"relative_path": "tasks-api/notes.txt", "content": "hello"}))
        if "give_answer" in names:
            return _completion(calls=_call("give_answer", {"value": "{'value': 7}, 200"}))
        if "edit_artifact" in names:
            return _completion(calls=_call("edit_artifact", {"relative_path": "tasks-api/app.py", "find": "200", "replace": "201"}))
        if "SprintPlanOutput" in names:
            return _completion(calls=_call("SprintPlanOutput", {"sprints": []}))
        return _completion(calls=_call("SpecialistOutput", {"changed_files": ["app/routes.py"]}))


def _model(server):
    return SimpleNamespace(model_name="new-model", openai_api_base="http://server/v1",
                           root_client=SimpleNamespace(chat=SimpleNamespace(completions=server)))


def _diagnosed():
    diagnosis = deep_diagnosis.diagnose(_model(_Obeys_only_when_told()), "new-model", workers=1)
    deep_diagnosis.keep(diagnosis)
    return diagnosis


def test_the_guides_measured_to_help_are_chosen_for_the_model():
    diagnosis = _diagnosed()
    profile = guidance.recorded("new-model")

    assert {"keep_to_role", "no_repetition"} <= set(diagnosis.helped)
    assert profile.chosen["keep_to_role"] and profile.chosen["no_repetition"]
    assert not profile.chosen["stop_when_done"]  # it already stopped: nothing to help
    assert diagnosis.reply_ceiling == deep_diagnosis.LOOPING_MODEL_CEILING


def test_a_standard_model_gets_only_what_helped_and_a_weak_one_every_guide_for_where_it_fell_short():
    baseline = (deep_diagnosis.Result("one program a command", 3, 0), deep_diagnosis.Result("a role kept", 3, 3),
                deep_diagnosis.Result("paths as given", 3, 3), deep_diagnosis.Result("exact argument names", 3, 3))
    standard = SimpleNamespace(model="m", baseline=baseline, helped=(), reminder_helped=False, measured_at="")
    assert guidance.tier_of(0.75) == "standard"
    assert not guidance.chosen_by(standard).chosen["one_program_a_command"]

    weak = SimpleNamespace(model="m", baseline=(*baseline[:1], deep_diagnosis.Result("a role kept", 3, 0)),
                           helped=(), reminder_helped=False, measured_at="")
    profile = guidance.chosen_by(weak)
    assert profile.tier == "weak" and profile.chosen["one_program_a_command"] and profile.tail_reminder


def test_the_active_guides_reach_every_stage_as_general_rows(_data):
    _diagnosed()

    keys = model_guidance.guidance_key()
    assert "guide:keep_to_role" in keys and "guide:no_repetition" in keys
    from app.plugins.registry import get_plugin_instructions

    text = get_plugin_instructions(["python", *keys])
    assert "Never write the same line" in text
    assert "model:" not in "".join(_data)  # nothing per model in the table: the lines are general


def test_each_guide_has_its_own_switch(monkeypatch):
    _diagnosed()
    monkeypatch.setenv("GUIDE_NO_REPETITION", "off")

    keys = model_guidance.guidance_key()
    assert "guide:no_repetition" not in keys and "guide:keep_to_role" in keys


def test_the_owner_s_override_wins_and_survives_a_new_diagnosis():
    _diagnosed()
    guidance.set_override("new-model", "keep_to_role", False)
    guidance.set_override("new-model", "paths_as_given", True)
    _diagnosed()

    keys = model_guidance.guidance_key()
    assert "guide:keep_to_role" not in keys and "guide:paths_as_given" in keys
    guidance.set_override("new-model", "keep_to_role", None)
    assert "guide:keep_to_role" in model_guidance.guidance_key()


def test_a_weak_model_is_reminded_at_the_end_of_every_request():
    guidance.keep(guidance.Profile(model="new-model", tier="weak", chosen={"one_program_a_command": True},
                                   tail_reminder=True))
    text = model_guidance.reminder()
    assert text.startswith("Before you reply, keep to these:") and "no shell" in text
    guidance.keep(guidance.Profile(model="new-model", tier="strong"))
    assert model_guidance.reminder() == ""


def test_no_guidance_with_the_switch_off(monkeypatch):
    _diagnosed()
    monkeypatch.setenv("MODEL_GUIDANCE", "off")
    assert model_guidance.guidance_key() == [] and model_guidance.reminder() == ""
    assert model_guidance.ceiling_for(("http://server/v1", "new-model")) is None


def test_the_chosen_ceiling_reaches_a_request_the_deployment_leaves_uncapped():
    from langchain_core.messages import HumanMessage

    from app.models import CompatibleChatOpenAI

    client = CompatibleChatOpenAI(model="new-model", base_url="http://server/v1", api_key="x", max_retries=0)
    model_guidance.set_ceiling(("http://server/v1", "new-model"), 40_000)
    try:
        payload = client._get_request_payload([HumanMessage(content="hi")])
    finally:
        model_guidance.set_ceiling(("http://server/v1", "new-model"), None)
    assert payload["max_tokens"] == 40_000


def test_every_guide_and_check_prompt_uses_none_of_the_banned_words():
    for guide in guidance.GUIDES:
        assert not BANNED.search(guide.line), guide.id
        assert set(guide.checks) <= set(deep_diagnosis.CHECKS), guide.id
    assert not BANNED.search(deep_diagnosis._SPEC) and not BANNED.search(deep_diagnosis._THE_RULE)
