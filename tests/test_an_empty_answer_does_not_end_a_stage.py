"""A live agent's answer with every field empty does not end its stage.

One run's defect-fix stages each reasoned through a reply's whole output
budget, were asked to answer with their tools withheld, wrote useful prose about
what was still wrong - and called `SpecialistOutput` with `{}`. Every field
defaults to empty, so that validated and ended the stage with no fix and no
regression test named. The defect stayed open and the next round did the same:
rounds 3, 4 and 5 on one defect while every test round between them was green.

The base class stays permissive - code and test doubles build empty instances
on purpose - and only the schema a live agent answers with refuses `{}`.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agents import specialists
from app.agents.specialists import AGENT_ANSWER, SpecialistOutput


class TestTheAgentsSchema:
    def test_an_empty_answer_is_refused(self):
        with pytest.raises(ValidationError) as caught:
            AGENT_ANSWER.model_validate({})

        assert "reports nothing" in str(caught.value)
        assert "keep working" in str(caught.value)
        assert "explain why in `decisions` or `verification`" in str(caught.value)

    def test_refusal_message_is_agnostic(self):
        with pytest.raises(ValidationError) as caught:
            AGENT_ANSWER.model_validate({})
        
        message = str(caught.value).lower()
        banned = ["task", "tasks", "to-do", "todo", "button", "click", "checkbox"]
        for word in banned:
            import re
            assert not re.search(rf"\b{re.escape(word)}\b", message), f"Message contains banned word: {word}"

    def test_fields_that_are_all_empty_are_refused(self):
        with pytest.raises(ValidationError):
            AGENT_ANSWER.model_validate({"changed_files": [], "tests": [], "blockers": []})

    @pytest.mark.parametrize(
        "answer",
        [
            {"blockers": ["2 of 3 edit tests still fail after save"]},
            {"changed_files": ["app/app.js"], "tests": ["edit persists after reload"]},
            {"decisions": ["Nothing to change: an earlier stage already did it"]},
            {"verification": [{"command": ["npm", "test"], "exit_code": 0, "summary": "ok"}]},
        ],
    )
    def test_one_field_is_enough(self, answer):
        assert AGENT_ANSWER.model_validate(answer)

    def test_the_tool_the_model_calls_keeps_its_name(self):
        """Prompts, answer recovery and the transcripts all say `SpecialistOutput`."""
        assert AGENT_ANSWER.__name__ == "SpecialistOutput"
        assert AGENT_ANSWER.model_json_schema()["title"] == "SpecialistOutput"

    def test_an_answer_is_still_a_specialist_output(self):
        assert isinstance(AGENT_ANSWER.model_validate({"blockers": ["x"]}), SpecialistOutput)


def test_a_specialist_s_empty_answer_is_sent_back_to_it(tmp_path, monkeypatch):
    """Through a real specialist agent: the `{}` answer comes back to the model as a refusal, not a finished stage."""
    from a_role_agent import Scripted, Stopped
    from langchain_core.messages import AIMessage

    monkeypatch.setattr("app.plugins.middleware.get_plugin_instructions", lambda keys, role: "")
    model = Scripted(replies=[AIMessage(content="", tool_calls=[{"name": "SpecialistOutput", "args": {}, "id": "a1"}])],
                     requests=[])
    agent = specialists.create_specialist_agent("backend", model=model, repo_root=tmp_path)

    with pytest.raises(Stopped):
        agent.invoke({"messages": [{"role": "user", "content": "go"}]}, {"configurable": {"thread_id": "t"}})

    told = [message for message in model.requests[1] if message.type == "tool"]
    assert len(told) == 1 and "reports nothing" in told[0].content
