from __future__ import annotations

import inspect
import re

from app.tools import repository


def test_no_banned_words_in_unseen_file_refusal_prompt() -> None:
    source = inspect.getsource(repository._refuse_a_blind_overwrite_of_another_stage_s_file)
    banned = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")
    found_refusal_line = False
    for line in source.splitlines():
        if "Refusing to write" in line or "Read it first" in line:
            found_refusal_line = True
            for word in banned:
                assert not re.search(
                    rf"\b{re.escape(word)}\b", line, re.IGNORECASE
                ), f"Found banned word '{word}' in line: {line}"
    assert found_refusal_line



def test_no_banned_words_in_read_only_rules() -> None:
    from app.agents import role_agent
    banned = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")
    found = False
    for line in role_agent._READ_ONLY_RULES.splitlines():
        if "Do not call tools to edit or write files" in line or "Any code or verification changes" in line:
            found = True
            for word in banned:
                assert not re.search(
                    rf"\b{re.escape(word)}\b", line, re.IGNORECASE
                ), f"Found banned word '{word}' in line: {line}"
    assert found


def test_no_banned_words_in_technical_lead_file_modification_rules() -> None:
    from app.agents import technical_lead
    banned = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")
    found = False
    for line in technical_lead._SYSTEM_PROMPT.splitlines():
        if "Do not modify application source code" in line or "Do not attempt to change repository files directly" in line:
            found = True
            for word in banned:
                assert not re.search(
                    rf"\b{re.escape(word)}\b", line, re.IGNORECASE
                ), f"Found banned word '{word}' in line: {line}"
    assert found


