"""A specification revised in place is kept consistent with the sections left unchanged (LR.42 part 1,
`DESIGN_REVISION_CROSS_CHECKED`).

Measured on 5 of 7 language-sweep runs: the review named a few sections, only those were rewritten, and the second
review found a rewritten section ("Graceful shutdown on SIGTERM") contradicting one left as it was ("No graceful
shutdown"), so the design went to the escalation.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace

from pydantic import BaseModel, Field

from app.graph import design_revision_cross_checked as cross
from app.graph import specification_parts

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


class Spec(BaseModel):
    file_plan: list[str] = Field(description="Every file and what it holds.")
    function_contracts: list[str] = Field(description="Every function and what it does.")
    deployment: list[str] = Field(description="How it runs.")
    testing: list[str] = Field(description="How it is tested.")


PREVIOUS = Spec(
    file_plan=["src/server.py: the HTTP server"],
    function_contracts=["start_server(port): listens on PORT; No graceful shutdown", "list_items(): every item"],
    deployment=["Runs as one process reading PORT"],
    testing=["pytest, one test per route"],
)
CHANGES = "- [blocking] Deployment: say what graceful shutdown does on SIGTERM"
REWRITTEN = ["Runs as one process reading PORT", "Graceful shutdown on SIGTERM: close the server, then exit 0"]
BROUGHT_INTO_LINE = ["start_server(port): listens on PORT; graceful shutdown on SIGTERM", "list_items(): every item"]


class _Model:
    """Names `deployment`, rewrites it as asked, and answers a request to bring sections into line."""

    def __init__(self, deployment=REWRITTEN):
        self.asked, self.deployment = [], deployment

    def invoke(self, messages, **_):
        text = str(messages[-1].content)
        self.asked.append(text)
        if '{"sections"' in text:
            return SimpleNamespace(content=json.dumps({"sections": ["deployment"]}))
        if "statements that now disagree" in text:
            return SimpleNamespace(content=json.dumps({"function_contracts": BROUGHT_INTO_LINE}))
        return SimpleNamespace(content=json.dumps({"deployment": self.deployment}))


def _revisions(model):
    return [asked for asked in model.asked if "--- The sections to rewrite" in asked and "now disagree" not in asked]


# --- the checks themselves --------------------------------------------------------------------------------------

def test_a_statement_that_denies_a_subject_is_told_from_one_that_states_it():
    assert cross.denies("start_server(): No graceful shutdown", "graceful shutdown")
    assert cross.denies("The service does not support graceful shutdown.", "graceful shutdown")
    assert cross.denies("Graceful shutdown is not supported", "graceful shutdown")
    assert cross.denies("LOG_LEVEL is not read", "LOG_LEVEL")
    assert not cross.denies("Graceful shutdown on SIGTERM closes the server", "graceful shutdown")
    # An error case is not a denial of the name it reports on.
    assert not cross.denies("Returns 404 when item_id is not found", "item_id")


def test_opposite_statements_pair_a_rewritten_statement_with_the_unchanged_one_it_contradicts():
    pairs = cross.opposite_statements(
        {"deployment": [REWRITTEN[1]]},
        {"function_contracts": PREVIOUS.function_contracts, "testing": ["Graceful shutdown is tested with SIGTERM"]},
    )
    assert [(p[0], p[1], p[3], p[4]) for p in pairs] == [
        ("graceful shutdown", "deployment", "function_contracts", PREVIOUS.function_contracts[0])]


def test_statements_that_agree_are_not_paired():
    assert cross.opposite_statements({"deployment": ["No graceful shutdown: the process exits"]},
                                     {"function_contracts": PREVIOUS.function_contracts}) == []
    assert cross.opposite_statements({"deployment": ["Reads PORT, default 8000"]},
                                     {"function_contracts": ["start_server(port): listens on PORT"]}) == []


def test_the_related_statements_are_those_of_unchanged_sections_on_the_same_subjects():
    related = cross.related_statements(PREVIOUS, ["deployment"], ["file_plan"], CHANGES)
    assert related == {"function_contracts": [PREVIOUS.function_contracts[0]]}
    # Sections being rewritten, or shown already, are never shown again.
    assert cross.related_statements(PREVIOUS, ["deployment"], ["file_plan", "function_contracts"], CHANGES) == {}


def test_the_related_statements_stay_within_their_budget():
    many = Spec(file_plan=[], deployment=["Reads DATA_DIR"], testing=[],
                function_contracts=[f"load_{n}(): reads DATA_DIR " + "x" * 200 for n in range(60)])
    related = cross.related_statements(many, ["deployment"], [], "- DATA_DIR default", budget=1_000)
    assert 0 < sum(len(s) for s in related["function_contracts"]) <= 1_000


# --- in the revision made in place ------------------------------------------------------------------------------

def test_on_the_revising_request_shows_the_related_unchanged_statements(monkeypatch):
    monkeypatch.setenv("DESIGN_REVISION_CROSS_CHECKED", "on")
    model = _Model(deployment=["Runs as one process reading PORT"])

    specification_parts.revised_in_place(PREVIOUS, CHANGES, model, "")

    [request] = _revisions(model)
    assert cross.SAID in request
    shown = request.split(cross.SAID, 1)[1].split("--- The form of each section")[0]
    assert PREVIOUS.function_contracts[0] in shown and "list_items" not in shown


def test_off_the_revising_request_is_as_before(monkeypatch):
    monkeypatch.setenv("DESIGN_REVISION_CROSS_CHECKED", "off")
    model = _Model()

    revised = specification_parts.revised_in_place(PREVIOUS, CHANGES, model, "")

    assert all(cross.SAID not in asked for asked in model.asked)
    assert all("now disagree" not in asked for asked in model.asked)
    assert revised.function_contracts == PREVIOUS.function_contracts


def test_on_an_unchanged_section_the_revision_now_contradicts_is_brought_into_line_by_one_call(monkeypatch):
    monkeypatch.setenv("DESIGN_REVISION_CROSS_CHECKED", "on")
    model = _Model()

    revised = specification_parts.revised_in_place(PREVIOUS, CHANGES, model, "")

    assert revised.deployment == REWRITTEN
    assert revised.function_contracts == BROUGHT_INTO_LINE
    [settling] = [asked for asked in model.asked if "now disagree" in asked]
    assert cross.SAID in settling and PREVIOUS.function_contracts[0] in settling
    assert set(json.loads(settling.split("--- The sections to rewrite, as they stand ---\n")[1]
                          .split("\n\nReply with")[0])) == {"function_contracts"}


def test_on_a_revision_that_contradicts_nothing_makes_no_further_call(monkeypatch):
    monkeypatch.setenv("DESIGN_REVISION_CROSS_CHECKED", "on")
    model = _Model(deployment=["Runs as one process reading PORT; no graceful shutdown"])

    revised = specification_parts.revised_in_place(PREVIOUS, CHANGES, model, "")

    assert revised.function_contracts == PREVIOUS.function_contracts
    assert all("now disagree" not in asked for asked in model.asked)


def test_a_call_that_cannot_bring_them_into_line_leaves_the_revision_as_it_was(monkeypatch):
    monkeypatch.setenv("DESIGN_REVISION_CROSS_CHECKED", "on")

    class _Failing(_Model):
        def invoke(self, messages, **kwargs):
            if "statements that now disagree" in str(messages[-1].content):
                raise RuntimeError("no reply")
            return super().invoke(messages, **kwargs)

    revised = specification_parts.revised_in_place(PREVIOUS, CHANGES, _Failing(), "")

    assert revised.deployment == REWRITTEN and revised.function_contracts == PREVIOUS.function_contracts


def test_its_words_are_plain(monkeypatch):
    monkeypatch.setenv("DESIGN_REVISION_CROSS_CHECKED", "on")
    model = _Model()

    specification_parts.revised_in_place(PREVIOUS, CHANGES, model, "")

    into_line = [asked for asked in model.asked if "statements that now disagree" in asked]
    assert into_line and not [text for text in [cross.SAID, *into_line] if BANNED.search(text)]
