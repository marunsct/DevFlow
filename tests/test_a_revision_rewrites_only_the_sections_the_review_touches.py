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


def test_a_section_answered_with_an_empty_list_is_left_as_it_stands_and_the_others_are_kept():
    """Measured: the one changed section came back written, a second came back `[]`, and the revision was dropped."""
    model = _Model(["testing", "decisions"], {"testing": ["node:test, 2 tiers"], "decisions": []})

    revised = specification_parts.revised_in_place(PREVIOUS, "- the testing section is thin", model, "")

    assert revised is not None
    assert revised.testing == ["node:test, 2 tiers"]
    assert revised.decisions == PREVIOUS.decisions


def test_a_section_answered_empty_that_already_held_nothing_stays_empty():
    previous = Spec(product_scope="Notes.", file_plan=["a"], testing=["t"], decisions=[])
    model = _Model(["testing", "decisions"], {"testing": ["u"], "decisions": []})

    revised = specification_parts.revised_in_place(previous, "- change", model, "")

    assert revised is not None and revised.testing == ["u"] and revised.decisions == []


def test_the_request_gives_the_form_of_every_section_to_rewrite_even_one_that_holds_nothing():
    """Measured: an empty section had no form to copy, the reply invented record keys, and nine fields failed to validate."""
    previous = Spec(product_scope="Notes.", file_plan=["a"], testing=["t"], decisions=[])
    model = _Model(["decisions"], {"decisions": ["d"]})

    specification_parts.revised_in_place(previous, "- add the missing decision", model, "")

    asked = model.asked[-1]
    form = asked.split("--- The form of each section (JSON schema) ---\n")[1].split("\n\n")[0]
    assert set(json.loads(form)) == {"decisions"}
    assert "Decisions and why." in form
    assert not BANNED.search(asked.split("--- The form of each section")[0].split("--- Required changes")[0])
    assert not BANNED.search("--- The form of each section (JSON schema) ---")


def test_a_model_that_cannot_name_the_sections_and_cannot_revise_leaves_it_to_the_architect():
    assert specification_parts.revised_in_place(PREVIOUS, "- change", _Model([], {}), "") is None


def test_a_model_that_cannot_name_the_sections_revises_every_section_in_parts():
    """Measured live: with no sections named, the architect rewrote the whole
    specification in one reply, cut at the output cap three times running."""
    everything = {"product_scope": "Notes over HTTP, kept in a store.", "file_plan": ["src/app.ts: routes", "src/store.ts: store"],
                  "testing": ["node:test"], "decisions": ["a store module"]}
    model = _Model([], everything)

    revised = specification_parts.revised_in_place(PREVIOUS, "- AC-6: a store module is missing", model, "")

    assert revised is not None and revised.file_plan == everything["file_plan"]
    rewrites = [asked for asked in model.asked if "--- The sections to rewrite" in asked]
    assert len(rewrites) == 2  # four sections, three at a time


def test_the_architect_node_revises_in_place_first_in_fast_delivery():
    source = inspect.getsource(workflow)
    at = source.index("revised = revised_in_place(")
    assert source.index("_fast_delivery() and required_changes and previous_specification is not None") < at
    assert at < source.index('stage_name="principal_architect"')


def test_a_run_with_no_judgement_model_named_revises_in_place_with_the_deployment_s_own(monkeypatch):
    """Measured live: a local-only run names no judgement model, the in-place
    revision required one, and the architect rewrote the whole specification."""
    import app.models

    built = object()
    monkeypatch.setattr(app.models, "build_default_chat_model", lambda: built)

    assert workflow._a_model_to_revise_with(None) is built
    named = object()
    assert workflow._a_model_to_revise_with(named) is named
    assert "_a_model_to_revise_with(judgement_model)" in inspect.getsource(workflow)


class Decision(BaseModel):
    title: str
    decision: str


class SpecWithRecords(BaseModel):
    product_scope: str = Field(description="What the release covers.")
    file_plan: list[str] = Field(description="Every file and what it holds.")
    decisions: list[Decision] = Field(description="Decisions and why.")


class _Echo:
    """Returns the named sections as it was shown them, with one file added - a reviser that keeps what it is not asked to change."""

    def __init__(self):
        self.asked = []

    def invoke(self, messages):
        text = str(messages[-1].content)
        self.asked.append(text)
        if '{"sections"' in text:
            return SimpleNamespace(content=json.dumps({"sections": ["file_plan", "decisions"]}))
        shown = json.loads(text.split("--- The sections to rewrite, as they stand ---\n", 1)[1].split("\n\nReply with", 1)[0])
        shown["file_plan"] = [*shown["file_plan"], "src/health.ts: the health route"]
        return SimpleNamespace(content=json.dumps(shown))


def test_sections_of_records_are_shown_as_json_and_join_again():
    """Measured live: the decision records were shown as `title='...' decision='...'`,
    the reviser handed them back so, and the revision - five minutes of model time -
    could not be joined ("11 validation errors") and was thrown away."""
    previous = SpecWithRecords(product_scope="Notes.", file_plan=["src/app.ts: routes"],
                               decisions=[Decision(title="Store", decision="A JSON file under DATA_DIR")])

    revised = specification_parts.revised_in_place(previous, "- a health route is missing", _Echo(), "")

    assert revised is not None
    assert revised.file_plan[-1] == "src/health.ts: the health route"
    assert revised.decisions == previous.decisions


def test_the_sections_the_review_names_are_rewritten_and_at_most_a_few_more():
    """Asked for every section a change touches or repeats, the model named nearly all of them: ten sections
    rewritten per revision, for three findings."""
    names = ["product_scope", "file_plan", "testing", "decisions", "configuration", "data_flows", "error_catalogue"]
    changes = "[blocking] Configuration section line 266: DATA_DIR default contradicts the File plan."
    chosen = specification_parts._bounded_by_what_the_review_names(
        ["product_scope", "testing", "decisions", "data_flows", "error_catalogue", "configuration"], changes, names)
    assert chosen[:1] == ["configuration"] and "file_plan" in chosen
    assert len(chosen) == 2 + specification_parts.MOST_UNNAMED_SECTIONS
    # A review that names no section keeps what the model chose.
    assert specification_parts._bounded_by_what_the_review_names(["testing"], "make it consistent", names) == ["testing"]
