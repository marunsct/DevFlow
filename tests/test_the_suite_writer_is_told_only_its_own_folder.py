"""The acceptance suite's writer is told its own folder once, and nothing that sends it to unit tests or product code.

Per-role audit 2026-11-20: its system prompt still said it defines and runs unit, integration and other tests, that it
may run programs to "build code ... and perform end-to-end development", and that tests live beside the code they test,
while its request says only the acceptance folder is its own. On one run the writer tried unit-test and product files
three times and was refused each time.
"""

from __future__ import annotations

import json

import pytest

FOLDER = "notes/acceptance"


@pytest.fixture
def prompts(tmp_path, monkeypatch):
    """(the suite writer's system prompt, the work-order testing specialist's), built in a scaffolded workspace."""
    from deepagents import create_deep_agent

    import app.agents.role_agent as role_agent
    from app.agents.specialists import create_specialist_agent
    from app.models import CompatibleChatOpenAI

    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "stack-pack.json").write_text(json.dumps({
        "pack": "browser-javascript", "project": "notes", "title": "Notes", "acceptance_dir": "acceptance",
    }))
    model = CompatibleChatOpenAI(model="Qwen3.5-9B-GGUF", api_key="unused", base_url="http://localhost:9/v1")
    captured: list[str] = []

    def spy(**kwargs):
        captured.append(kwargs["system_prompt"])
        return create_deep_agent(**kwargs)

    monkeypatch.setattr(role_agent, "create_deep_agent", spy)
    create_specialist_agent("testing", model=model, repo_root=tmp_path, writing_the_suite=True)
    create_specialist_agent("testing", model=model, repo_root=tmp_path)
    return captured


def test_the_suite_writer_is_not_told_to_write_unit_tests_or_build_the_product(prompts):
    flat = " ".join(prompts[0].split())

    assert "unit, integration" not in flat
    assert "build code" not in flat and "end-to-end development" not in flat
    assert "Tests live beside the code they test" not in flat


def test_the_suite_writer_is_told_its_own_folder_once(prompts):
    flat = " ".join(prompts[0].split())

    assert flat.count(f"`{FOLDER}/`") == 1
    assert "the one folder you write in" in flat


def test_a_work_order_s_test_writer_keeps_the_builder_s_wording(prompts):
    flat = " ".join(prompts[1].split())

    assert "unit, integration" in flat and "end-to-end development" in flat
    assert "Tests live beside the code they test" in flat
    assert f"`{FOLDER}/`" not in flat


def test_with_no_folder_known_yet_the_suite_writer_is_pointed_at_its_request(tmp_path, monkeypatch):
    from deepagents import create_deep_agent

    import app.agents.role_agent as role_agent
    from app.agents.specialists import create_specialist_agent
    from app.models import CompatibleChatOpenAI

    captured: list[str] = []
    monkeypatch.setattr(role_agent, "create_deep_agent",
                        lambda **kwargs: captured.append(kwargs["system_prompt"]) or create_deep_agent(**kwargs))
    model = CompatibleChatOpenAI(model="Qwen3.5-9B-GGUF", api_key="unused", base_url="http://localhost:9/v1")

    create_specialist_agent("testing", model=model, repo_root=tmp_path, writing_the_suite=True)

    flat = " ".join(captured[0].split())
    assert "the acceptance folder your request names" in flat
    assert "Tests live beside the code they test" not in flat


# The banned words are checked over every rendered prompt, this one included, in
# `test_no_rendered_system_prompt_carries_a_product_word`.
