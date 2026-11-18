"""A stage whose reading was done before it began is not offered the lookup tools, even with the tool list held stable.

Measured on one hosted run: the architect was offered `read_docs` with its reading already done, called it five times,
and was refused five times - each a paid hosted turn. The list is held stable so a tool withheld part way through a
visit does not change the prompt prefix; a stage researched before it began has the lookups withheld from its first
call, so leaving them out keeps the list the same on every call of the visit.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

import pytest

from app.tools import research

TOOLS = ["read_file", "read_docs", "look_up_package", "search_the_web", "read_web_page", "write_answer"]


@dataclass
class _Request:
    tools: list[Any] = field(default_factory=list)

    def override(self, **changes: Any) -> "_Request":
        return replace(self, **changes)


def _offered(**context: Any) -> list[str]:
    seen: list[str] = []
    middleware = research.build_research_share_middleware()
    middleware.wrap_model_call(_Request(tools=[{"name": t} for t in TOOLS]), lambda r: seen.extend(t["name"] for t in r.tools))
    return seen


@pytest.mark.parametrize("stable", ["on", "off"])
def test_a_researched_stage_is_offered_no_lookup(monkeypatch, stable):
    monkeypatch.setenv("STABLE_TOOLS", stable)
    with research.researched():
        offered = _offered()

    assert offered == ["read_file", "write_answer"]


def test_a_stage_not_researched_keeps_its_lookups_while_the_list_is_held_stable(monkeypatch):
    monkeypatch.setenv("STABLE_TOOLS", "on")

    assert _offered() == TOOLS
