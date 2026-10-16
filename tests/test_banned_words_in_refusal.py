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

