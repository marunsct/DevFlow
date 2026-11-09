"""Sampling for three modes of a call is derived for any model, kept per model, and sent by each call's mode.

A reasoning model is called with its thinking on and with it off, and its model card gives each its own sampling
(Qwen3.6's: thinking general, thinking for precise coding, no thinking); one setting for every call fits neither.
Nothing is sent until the owner turns sampling by mode on (ADR-0008).
"""
from __future__ import annotations

import pytest

from app.models import sampling_modes as sm

#: The shape of the Qwen3.6 card's own sampling section.
CARD = """## Best Practices

- **Sampling Parameters**:
  - Thinking mode for general tasks:
    `temperature=1.0, top_p=0.95, top_k=20, min_p=0.0, presence_penalty=1.5, repetition_penalty=1.0`
  - Thinking mode for precise coding tasks (e.g. WebDev):
    `temperature=0.6, top_p=0.95, top_k=20, min_p=0.0, presence_penalty=0.0, repetition_penalty=1.0`
  - Instruct (or non-thinking) mode:
    `temperature=0.7, top_p=0.80, top_k=20, min_p=0.0, presence_penalty=1.5, repetition_penalty=1.0`
"""


@pytest.fixture
def store(tmp_path, monkeypatch):
    from app.models import registry

    monkeypatch.setattr(registry, "fitness_dir", lambda: tmp_path)
    sm.forget()
    yield tmp_path
    sm.forget()


def test_each_mode_is_read_from_the_card_s_own_words():
    derived = sm.derive("qwen3.6-35b-a3b", CARD)
    assert derived["thinking_general"]["values"]["temperature"] == 1.0
    assert derived["thinking_precise"]["values"] == {"temperature": 0.6, "top_p": 0.95, "top_k": 20, "min_p": 0.0,
                                                     "presence_penalty": 0.0, "repetition_penalty": 1.0}
    assert derived["no_thinking"]["values"]["top_p"] == 0.8
    assert all(derived[m]["source"] == "model card" for m in ("thinking_general", "thinking_precise", "no_thinking"))


def test_a_presence_penalty_is_taken_to_zero_where_code_is_written_and_said_so():
    derived = sm.derive("qwen3.6-35b-a3b", CARD)
    assert derived["no_thinking"]["values"]["presence_penalty"] == 0.0
    assert "presence penalty taken to 0 by the harness" in derived["no_thinking"]["note"]
    assert derived["thinking_general"]["values"]["presence_penalty"] == 1.5, "prose may keep it"


def test_with_no_card_the_family_s_values_are_used(store):
    derived = sm.derive("qwen3-30b-a3b", "")
    assert derived["thinking_precise"]["source"] == "model family"
    assert derived["thinking_precise"]["values"]["temperature"] == 0.6
    assert derived["no_thinking"]["values"]["temperature"] == 0.7


def test_an_unknown_model_with_no_card_is_unknown_not_guessed():
    derived = sm.derive("some-new-model-7b", "")
    assert {v["source"] for v in derived.values()} == {"unknown"}


def test_nothing_is_sent_until_the_owner_turns_it_on(store):
    sm.keep_found("m", sm.derive("qwen3.6", CARD))
    payload: dict = {}
    assert sm.with_the_mode_s_sampling(payload, "m") is False and payload == {}


def test_each_call_gets_its_mode_s_values_once_on(store):
    sm.keep_found("m", sm.derive("qwen3.6", CARD))
    sm.set_choices("m", send=True)
    sm.forget()
    thinking: dict = {}
    sm.with_the_mode_s_sampling(thinking, "m")
    assert thinking["temperature"] == 0.6 and thinking["extra_body"]["top_k"] == 20
    quiet = {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
    sm.with_the_mode_s_sampling(quiet, "m")
    assert quiet["temperature"] == 0.7 and quiet["top_p"] == 0.8
    assert quiet["extra_body"]["chat_template_kwargs"] == {"enable_thinking": False}, "the switch is kept"
    effort = {"reasoning_effort": "none"}
    sm.with_the_mode_s_sampling(effort, "m")
    assert effort["temperature"] == 0.7


def test_the_owner_s_values_and_choices_win(store):
    sm.keep_found("m", sm.derive("qwen3.6", CARD))
    sm.set_choices("m", send=True, thinking_calls="thinking_general")
    sm.set_owner("m", "no_thinking", {"temperature": 0.2, "top_k": ""})
    sm.forget()
    thinking: dict = {"temperature": 0.9}
    sm.with_the_mode_s_sampling(thinking, "m")
    assert thinking["temperature"] == 0.9, "a value the request carries wins"
    assert thinking["presence_penalty"] == 1.5, "the general mode was chosen for thinking calls"
    quiet = {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
    sm.with_the_mode_s_sampling(quiet, "m")
    assert quiet["temperature"] == 0.2 and "top_p" not in quiet
    view = sm.view("m")
    row = next(r for r in view["modes"] if r["id"] == "no_thinking")
    assert row["source"] == "owner" and row["derived"]["temperature"] == 0.7
    sm.set_owner("m", "no_thinking", None)
    assert next(r for r in sm.view("m")["modes"] if r["id"] == "no_thinking")["source"] == "model card"


def test_a_thinking_call_may_use_only_a_thinking_mode(store):
    with pytest.raises(ValueError):
        sm.set_choices("m", thinking_calls="no_thinking")
    with pytest.raises(KeyError):
        sm.set_owner("m", "no_such_mode", {})
    with pytest.raises(KeyError):
        sm.set_owner("m", "no_thinking", {"seed": 1})


def test_every_mode_says_what_it_is_for_and_what_it_does():
    for mode in sm.MODES:
        assert len(mode.used_for) > 40 and len(mode.what_it_does) > 40


def test_the_call_path_adds_the_mode_s_sampling():
    import inspect

    from app import models

    assert "with_the_mode_s_sampling(payload, self._served_by()[1])" in inspect.getsource(models)


def test_the_settings_page_can_read_determine_and_set_it():
    from app.server.settings import settings_router

    routes = {(sorted(r.methods)[0], r.path) for r in settings_router.routes if hasattr(r, "methods")}
    prefix = settings_router.prefix
    assert ("GET", f"{prefix}/model/sampling") in routes
    assert ("POST", f"{prefix}/model/sampling/determine") in routes
    assert ("PUT", f"{prefix}/model/sampling") in routes


# Measured on two more cards: settings written one a line were skipped, and a benchmark's settings taken instead.
LFM_CARD = """- **Generation parameters**:
  - `temperature: 0.1`
  - `top_k: 50`
  - `repetition_penalty: 1.05`

## Evaluation
- **AutomationBench**: temperature = 0.6, top_p = 0.95, max_turns = 50.
"""
GLM_CARD = """### Evaluation Parameters

**Default Settings (Most Tasks)**

* temperature: `1.0`
* top-p: `0.95`
* max new tokens: `131072`

**Terminal Bench, SWE Bench Verified**

* temperature: `0.7`
* top-p: `1.0`
"""


def test_settings_written_one_a_line_are_read_and_a_benchmark_s_are_not():
    assert sm.from_the_card(LFM_CARD) == {"any": {"temperature": 0.1, "top_k": 50, "repetition_penalty": 1.05}}
    assert sm.from_the_card(GLM_CARD) == {"any": {"temperature": 1.0, "top_p": 0.95}}


def test_a_benchmark_s_settings_are_used_only_when_the_card_has_nothing_else():
    only = "## Results\n- **SWE-bench**: temperature = 0.6, top_p = 0.95\n"
    assert sm.from_the_card(only) == {"any": {"temperature": 0.6, "top_p": 0.95}}
