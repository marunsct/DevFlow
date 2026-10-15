"""In fast delivery a revision rewrites only the sections the review's changes touch, at once.

Sent back once, one run's architect wrote its whole specification again: one
reply of 47,669 tokens over 10 minutes, and the next one cut off after 103,080
characters.
"""

from __future__ import annotations

import inspect
import json
import re
from types import SimpleNamespace

from pydantic import BaseModel, Field

from app.graph import specification_parts, workflow

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


class Spec(BaseModel):
    product_scope: str = Field(description="What the release covers.")
    file_plan: list[str] = Field(description="Every file and what it holds.")
    testing: list[str] = Field(description="How it is tested.")
    decisions: list[str] = Field(description="Decisions and why.")


PREVIOUS = Spec(product_scope="Notes over HTTP.", file_plan=["src/app.ts: routes"], testing=["node:test"], decisions=["JSON file"])


class _Model:
    def __init__(self, sections, revised):
        self.sections, self.revised, self.asked = sections, revised, []

    def invoke(self, messages):
        text = str(messages[-1].content)
        self.asked.append(text)
        if '{"sections"' in text:
            return SimpleNamespace(content=json.dumps({"sections": self.sections}))
        return SimpleNamespace(content=json.dumps({k: v for k, v in self.revised.items() if f'"{k}"' in text.split("--- The sections to rewrite")[1]}))


def test_only_the_sections_named_are_rewritten_and_the_rest_kept():
    model = _Model(["file_plan", "testing", "not_a_section"], {"file_plan": ["src/app.ts: routes", "src/store.ts: store"], "testing": ["node:test, 2 tiers"]})

    revised = specification_parts.revised_in_place(PREVIOUS, "- AC-6: a store module is missing", model, "context")

    assert revised.file_plan == ["src/app.ts: routes", "src/store.ts: store"]
    assert revised.testing == ["node:test, 2 tiers"]
    assert revised.product_scope == PREVIOUS.product_scope and revised.decisions == PREVIOUS.decisions
    assert all("AC-6: a store module is missing" in asked for asked in model.asked)
    assert not any(BANNED.search(asked.split("--- Required changes")[0]) for asked in model.asked)


def test_a_section_that_comes_back_empty_leaves_the_revision_to_the_architect():
    model = _Model(["file_plan", "testing"], {"file_plan": ["x"]})

    assert specification_parts.revised_in_place(PREVIOUS, "- change", model, "") is None


def test_a_model_that_cannot_name_the_sections_leaves_it_to_the_architect():
    assert specification_parts.revised_in_place(PREVIOUS, "- change", _Model([], {}), "") is None


def test_the_architect_node_revises_in_place_first_in_fast_delivery():
    source = inspect.getsource(workflow)
    at = source.index("revised = revised_in_place(")
    assert source.index("_fast_delivery() and required_changes and previous_specification is not None") < at
    assert at < source.index('stage_name="principal_architect"')
