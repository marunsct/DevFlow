"""Behind `FIXERS_HOLD_WHAT_THEY_READ` (LF.1406): after a summary, a fixer's memory holds the files it was reading.

Measured on one medium run: two fixers of one batch, summarised two and three times in 17 and 19 calls, read the same
route, service and entry files again after each summary (31 and 27 reads of 10 files) - the reviews, the lead, the
test rounds and the builders have their memory chosen again at a summary (LF.1288); a fix stage did not.
"""
from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage
from test_a_summary_holds_what_the_stage_was_reading import (
    _a_project_folder_past_its_room,
    _first_message,
    _later,
    _read,
    _Visit,
)

from app.agents import stage_memory

FIXER = "defect_fix_2_2"
AUTH, SCHEMAS, TESTS = "proj/pkg/routes/auth.py", "proj/pkg/schemas.py", "proj/tests/test_auth.py"


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "65536")
    monkeypatch.setenv("PROJECT_MEMORY", "on")
    monkeypatch.setenv("CANONICAL_MEMORY", "on")
    stage_memory.forget_everything()
    yield
    stage_memory.forget_everything()


def _a_fixer_summarised_after_reading(root, tmp_path) -> tuple[str, str]:
    _a_project_folder_past_its_room(root)
    opening = HumanMessage(content="Fix this defect: signing up answers 500.", id="opening")
    with _Visit(root, FIXER, tmp_path) as visit:
        first = _first_message(visit.call([opening]))
        conversation = [opening]
        for n, path in enumerate([AUTH, TESTS, AUTH, SCHEMAS, AUTH]):
            conversation += _read(n, path, root)
        after = _first_message(visit.call(visit.summarised(conversation + _later())))
    return first, after


def test_with_the_switch_on_a_fixer_holds_the_files_it_read_most_after_a_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("FIXERS_HOLD_WHAT_THEY_READ", "on")

    first, after = _a_fixer_summarised_after_reading(tmp_path, tmp_path)

    assert f"=== {AUTH} (numbered lines" not in first, "the arrangement: its opening memory does not hold it"
    assert f"=== {AUTH} (numbered lines) ===" in after


def test_with_the_switch_off_a_fixer_s_memory_stays_as_its_visit_opened(tmp_path, monkeypatch):
    monkeypatch.setenv("FIXERS_HOLD_WHAT_THEY_READ", "off")

    first, after = _a_fixer_summarised_after_reading(tmp_path, tmp_path)

    assert f"=== {AUTH} (numbered lines" not in after
    assert after.startswith(first[:first.index("Fix this defect")])


def test_it_is_a_switch_the_admin_page_lists_off_in_code():
    from app import switches
    from app.agents import fixers_hold_what_they_read
    from app.observability.provenance import SWITCHES

    assert SWITCHES["FIXERS_HOLD_WHAT_THEY_READ"] == "app.agents.fixers_hold_what_they_read"
    assert "FIXERS_HOLD_WHAT_THEY_READ" in switches.GROUPS["Efficiency"]
    assert fixers_hold_what_they_read.ON_BY_DEFAULT is False


@pytest.mark.parametrize("word", ["task", "tasks", "to-do", "todo", "button", "click", "checkbox"])
def test_what_the_admin_page_and_the_record_say_carries_no_product_word(word):
    import re

    from app.agents import fixers_hold_what_they_read

    said = fixers_hold_what_they_read.explanation + " " + fixers_hold_what_they_read.SAID
    assert not re.search(rf"\b{re.escape(word)}\b", said, re.I)
