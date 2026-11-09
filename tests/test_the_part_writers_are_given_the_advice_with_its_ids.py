"""The specification's part writers are given the specialists' advice numbered with its ids (harness review HR2.D.1).

They were given it as raw JSON with no ids while the check that follows demands one decision line per id: 224 rounds
over 120 runs asked again for decisions on ids the writer was never shown.
"""
from __future__ import annotations

import inspect
import re

from app.agents.specialist_advice import advice_block
from app.graph import workflow

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_the_parts_context_carries_the_numbered_advice() -> None:
    source = inspect.getsource(workflow)
    context = source[source.index("def parts_context() -> str:"):source.index("update = None", source.index("def parts_context() -> str:"))]
    assert "advice_block(state.get(\"specialist_advice\"))" in context
    assert '("Specialists\' advice", "specialist_advice")' not in context, "not the raw form any more"


def test_the_numbered_advice_names_every_id_and_the_rule() -> None:
    block = advice_block({"database": ["Index the owner column"], "backend": ["Validate the body", "Return 404 on a miss"]})
    for ident in ("DB-1", "BE-1", "BE-2"):
        assert f"- {ident}:" in block
    assert "specialist_advice_decisions" in block
    assert not BANNED.search(block)
