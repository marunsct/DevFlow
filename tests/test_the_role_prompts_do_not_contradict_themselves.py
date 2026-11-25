"""The role prompts do not contradict each other or the tools the roles have (LR.54, launch review).

Found: read-only roles were told to delegate changes with no tool to delegate with, and that reading widely was "the
whole of" their job beside a memory that says not to read again what it holds; builders were told not to "separate"
core logic beside the testability rule's "keep the pure logic apart from I/O"; and "read the entire file in one call"
beside a read tool that returns 100 lines unless asked for more.
"""
from __future__ import annotations

import inspect
import re

from app.agents import role_agent, specialists

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_the_contradictions_are_gone():
    role = inspect.getsource(role_agent)
    assert "must be delegated" not in role and "is the whole of your job" not in role
    assert "`read_file` call with no `limit`: it returns the whole" in role
    builders = inspect.getsource(specialists)
    assert "'separate' core application logic" not in builders
    assert "is not removing it: the product still runs it" in builders


def test_the_new_words_ban_the_product_s_nouns():
    role = inspect.getsource(role_agent)
    for phrase in ("for the stage that writes it", "Read what your answer rests on", "call with no `limit`: it returns"):
        at = role.index(phrase)
        assert not BANNED.search(role[at - 200:at + 300])
    builders = inspect.getsource(specialists)
    at = builders.index("is not removing it")
    assert not BANNED.search(builders[at - 300:at + 100])
