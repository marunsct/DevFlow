"""Behind `INTERFACE_STATES_AS_CRITERIA` (plan PQ.8): a page's empty, busy and failed states are named in the
specification's interface design, each with a role and the words shown, outside any list.

Read in eight stored products: the best page of the set showed nothing on a failed request and no busy state while one
ran, and put its empty state inside the list; two others had no empty state at all.
"""
from __future__ import annotations

import re

import pytest

from workflow_nodes import a_specification, an_architect, an_architect_state

SWITCH = "INTERFACE_STATES_AS_CRITERIA"
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
ALL_THREE = [
    'Empty: the bookmark view shows an element with role status and the words "No bookmarks yet", above the list.',
    'Busy: while a request is on its way, an element with role status shows "Saving...", outside the list.',
    'Failed: a request that fails shows an element with role alert: "Could not save. Try again.", outside the list.',
]
#: The checks the node runs after a draft that these tests are not about, each finding nothing.
QUIET = {
    "app.graph.workflow._the_served_files_the_plan_leaves_out": lambda spec, state: [],
    "app.graph.workflow._settings_it_cannot_start_without": lambda spec: [],
}


def _a_state(tmp_path, kind: str = "fullstack"):
    from app.agents.stack_selector import StackSelectorOutput, TechnologyStack

    stack = TechnologyStack(language="Python", framework="FastAPI",
                            frontend_framework="React" if kind == "fullstack" else "", database="SQLite",
                            testing_framework="pytest, Playwright", product_kind=kind, additional_tools=[])
    return an_architect_state(tmp_path, stack_selection=StackSelectorOutput(technology_stack=stack, rationale="."))


def _drafted(tmp_path, monkeypatch, *, switch: str = "on", kind: str = "fullstack", design=(), fast: bool = False):
    monkeypatch.setenv(SWITCH, switch)
    return an_architect(_a_state(tmp_path, kind), a_specification(interface_design=list(design)), fast=fast,
                        patches=QUIET)


def test_with_it_on_the_architect_of_a_page_is_told_its_three_states(tmp_path, monkeypatch) -> None:
    _, asked, _ = _drafted(tmp_path, monkeypatch, design=ALL_THREE)

    told = asked[0]
    assert "`Empty: ...`, `Busy: ...` and `Failed: ...`" in told
    assert "outside any list of records" in told and "ARIA role" in told


def test_in_fast_delivery_the_writer_of_the_interface_design_is_told_them_too(tmp_path, monkeypatch) -> None:
    """The architect writes the core; `interface_design`, left empty, is written by a call of its own."""
    _, _, written = _drafted(tmp_path, monkeypatch, fast=True)

    [part] = [text for text in written if "interface_design" in text.split("--- The sections to write ---")[-1]]
    assert "`Empty: ...`, `Busy: ...` and `Failed: ...`" in part


@pytest.mark.parametrize("switch, kind", [("off", "fullstack"), ("on", "http_api")])
def test_with_it_off_or_with_no_page_nothing_is_said(tmp_path, monkeypatch, switch, kind) -> None:
    update, asked, _ = _drafted(tmp_path, monkeypatch, switch=switch, kind=kind)

    assert "`Empty: ...`" not in asked[0]
    assert update["stage"] == "architecture_review"


def test_a_design_without_its_busy_and_failed_states_goes_back_for_them(tmp_path, monkeypatch) -> None:
    update, _, _ = _drafted(tmp_path, monkeypatch, design=ALL_THREE[:1] + ["The list shows newest first."])

    assert update["stage"] == "principal_architect"
    [comment] = update["revision_comments"]
    assert "`Busy:`" in comment and "`Failed:`" in comment and "`Empty:`" not in comment
    assert "Return only `interface_design`" in comment


def test_a_state_named_without_a_role_or_the_words_shown_is_not_named(tmp_path, monkeypatch) -> None:
    update, _, _ = _drafted(tmp_path, monkeypatch, design=[
        *ALL_THREE[:2], "Failed: an error message is shown."])

    assert update["stage"] == "principal_architect"
    assert "`Failed:`" in update["revision_comments"][0]


def test_a_design_naming_all_three_goes_on(tmp_path, monkeypatch) -> None:
    update, _, _ = _drafted(tmp_path, monkeypatch, design=ALL_THREE)

    assert update["stage"] == "architecture_review"


def test_the_words_said_avoid_the_banned_words(tmp_path, monkeypatch) -> None:
    from app.agents.interface_states import RULE, repair

    assert not BANNED.search(RULE)
    assert not BANNED.search(repair(["Empty", "Busy", "Failed"]))


def test_it_is_registered_off_in_code() -> None:
    from app import switches
    from app.observability.provenance import SWITCHES, switch

    assert SWITCH in switches.EXPERIMENTS and SWITCH not in switches.EXPERIMENTS_ON
    assert switch(SWITCHES[SWITCH]).ON_BY_DEFAULT is False
