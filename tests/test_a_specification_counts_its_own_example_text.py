"""A specification counts the length of its own example text from that text, never by guess.

Per-role audit over 30 runs: hand-typed counts of example text began in the specification and the suite copied them -
`'abc def \\n'` given as 8 characters (9), `"Hello world foo bar baz \\n"` as 24 (25) and 2 lines (1), 12 bytes (14) - in
three runs; one cost 283 model calls on a right product.
"""
from __future__ import annotations

import re

from app.agents import principal_architect

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _the_rule() -> str:
    prompt = principal_architect._SYSTEM_PROMPT if hasattr(principal_architect, "_SYSTEM_PROMPT") else ""
    start = prompt.find("- Where an example gives a count or a length of its own text")
    assert start >= 0, "the architect is told"
    return prompt[start:prompt.find("\n- ", start + 3)]


def test_the_architect_counts_example_text_from_the_text():
    rule = _the_rule()
    for word in ("characters", "lines", "bytes", "one unit at a time", "the length of the text above"):
        assert word in rule
    assert not BANNED.search(rule)
