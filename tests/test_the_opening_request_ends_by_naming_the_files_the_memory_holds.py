"""The opening request ends by naming the files the project memory holds, so a stage does not read them again.

The memory opens the request and the request can run to 70,000 tokens after
it. Measured on one gate run: 24 of 142 tool-calling replies did nothing but
read files the memory held - every review's and the lead's first move.
"""
from __future__ import annotations

import re

from langchain_core.messages import HumanMessage

from app.agents import project_memory

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_the_held_files_close_the_opening_request():
    held = ["docs/product_intake.md", "app/main.py", ".harness/suite.json"]
    opening = project_memory._with_memory([HumanMessage(content="Review the sprint.")], "[memory]", held)[0]

    assert opening.content.startswith("[memory]\n\nReview the sprint.")
    closing = opening.content.split("Review the sprint.", 1)[1]
    assert "`docs/product_intake.md`" in closing and "`app/main.py`" in closing and ".harness" not in closing
    assert not BANNED.search(closing)


def test_nothing_held_adds_nothing_and_a_long_list_is_cut():
    opening = project_memory._with_memory([{"role": "user", "content": "Go."}], "[memory]", [])[0]
    assert opening["content"] == "[memory]\n\nGo."
    many = [f"src/m{n}.py" for n in range(project_memory.MOST_HELD_NAMED + 5)]
    assert "and 5 more" in project_memory.files_held_line(many)


def test_the_middleware_passes_what_the_memory_holds():
    import inspect

    assert "_with_memory(messages, memory, list(held))" in inspect.getsource(project_memory)
