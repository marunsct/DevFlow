"""A model measured strong is not given the prompt blocks written against a small model's failures.

Deep review 2026-11-18, item C7: role system prompts run 15-19k characters, much of it rules measured on a small
local model (return the answer through the schema, reasoning is not work, a result is not a file). With
`LEAN_PROMPTS_FOR_STRONG_MODELS` on, a model whose deep diagnosis recorded the tier "strong" is built without them;
its role, the stack's facts and the stage's rules stay. Any other model, or the switch off, gets the prompt as before.
"""
from __future__ import annotations

from tests.a_role_agent import Scripted, Stopped


def _system_prompt_of(model_name: str, root, monkeypatch) -> str:
    from app.agents.specialists import create_specialist_agent

    monkeypatch.setattr("app.plugins.middleware.get_plugin_instructions", lambda keys, role: "")
    model = Scripted(replies=[], requests=[], offered=[])
    monkeypatch.setattr("app.models.reply_salvage.served_name", lambda _model: model_name)
    agent = create_specialist_agent("backend", model=model, repo_root=str(root))
    try:
        agent.invoke({"messages": [{"role": "user", "content": "go"}]}, {"configurable": {"thread_id": "t"}})
    except Stopped:
        pass
    return next(str(m.content) for m in model.requests[0] if getattr(m, "type", "") == "system")


def _measured(name: str, tier: str, data_dir, monkeypatch) -> None:
    from app.models.guidance import Profile, keep

    monkeypatch.setenv("DATA_DIR", str(data_dir))
    keep(Profile(model=name, tier=tier, score=0.95 if tier == "strong" else 0.5))


def test_a_model_measured_strong_is_built_without_the_weak_model_blocks(tmp_path, monkeypatch):
    monkeypatch.setenv("LEAN_PROMPTS_FOR_STRONG_MODELS", "on")
    _measured("hosted-strong", "strong", tmp_path / "data", monkeypatch)

    prompt = _system_prompt_of("hosted-strong", tmp_path, monkeypatch)

    assert "REASONING IS NOT WORK" not in prompt
    assert "How to finish:" not in prompt
    assert "ARTIFACTS ARE NOT YOUR STRUCTURED RESPONSE" not in prompt
    assert "You are the Backend specialist" in prompt
    assert "CRITICAL DIRECTORY RULES" in prompt


def test_a_model_measured_weak_keeps_every_block(tmp_path, monkeypatch):
    monkeypatch.setenv("LEAN_PROMPTS_FOR_STRONG_MODELS", "on")
    _measured("local-small", "weak", tmp_path / "data", monkeypatch)

    prompt = _system_prompt_of("local-small", tmp_path, monkeypatch)

    assert "REASONING IS NOT WORK" in prompt and "How to finish:" in prompt


def test_with_the_switch_off_a_strong_model_keeps_every_block(tmp_path, monkeypatch):
    monkeypatch.setenv("LEAN_PROMPTS_FOR_STRONG_MODELS", "off")
    _measured("hosted-strong", "strong", tmp_path / "data", monkeypatch)

    prompt = _system_prompt_of("hosted-strong", tmp_path, monkeypatch)

    assert "REASONING IS NOT WORK" in prompt and "How to finish:" in prompt
