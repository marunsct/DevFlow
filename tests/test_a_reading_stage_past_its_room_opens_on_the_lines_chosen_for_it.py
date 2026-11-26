"""A reading stage that opens on a project past its memory's room is given the lines one short call chose for it (plan
PF.4, LF.1558, `RANGES_CHOSEN_BEFORE_A_READING_STAGE`).

Measured before it: the suite's author, the test round and the technical lead wasted 48%, 35% and 52% of their input
on the medium runs - their memory held whole files in rank order until the room ran out, the stage read the rest,
a summary dropped it, and it read it again.

The project is a captured page product (`tests/captured/projects/react-to-do-list-app`), larger than the room a
32,000-token window gives the memory. The model is stood in for; its answer is written in the form the call asks for
(no run has made this call yet, so there is no captured answer to copy).
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from app.agents import project_memory, ranges_chosen_first

PROJECTS = Path(__file__).parent / "captured" / "projects"
PROJECT = "react-to-do-list-app"
ITEM = f"{PROJECT}/src/components/TaskItem.tsx"
APP = f"{PROJECT}/src/App.tsx"
STORAGE = f"{PROJECT}/src/storage.ts"
OPENING = ("Run the product against the acceptance criteria of this sprint: AC-4 (an item is edited in place and "
           "saved) and AC-5 (an item is marked done). Report each failure as a defect with the file it is in.")
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


class TheModel:
    """The model server: answers the ranges it was asked for, and keeps what it was asked."""

    def __init__(self, ranges: list[str]) -> None:
        self.ranges, self.asked = ranges, []

    def invoke(self, messages, **kwargs):
        self.asked.append(messages[-1].content)
        return AIMessage(content=json.dumps({"ranges": self.ranges}))


def _a_workspace(tmp_path: Path, name: str = PROJECT) -> Path:
    shutil.copytree(PROJECTS / name, tmp_path / name)
    (tmp_path / ".project-directory").write_text(name)
    return tmp_path


@pytest.fixture(autouse=True)
def _arranged(monkeypatch):
    monkeypatch.setenv("RANGES_CHOSEN_BEFORE_A_READING_STAGE", "on")
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "32000")
    ranges_chosen_first.forget()


def test_a_test_round_past_its_room_holds_the_chosen_lines_and_outlines_the_rest(tmp_path):
    root = _a_workspace(tmp_path)
    model = TheModel([f"{ITEM}: lines 1-30", f"{APP}: lines 5-25"])

    memory, held = project_memory.render_for_a_stage(root, model, OPENING, "test_round_1")

    item = (root / ITEM).read_text().splitlines()
    assert f"=== {ITEM} ({len(item)} lines; the {ranges_chosen_first.SAID}" in memory
    assert f"\n1: {item[0]}\n" in memory and f"\n30: {item[29]}\n" in memory and f"\n31: {item[30]}\n" not in memory
    assert f"=== {STORAGE} ===" not in memory, "a code file no range named was held whole"
    assert f"{STORAGE} (" in memory, "a code file no range named is outlined, to be read by range"
    assert not any(path.endswith((".ts", ".tsx", ".js")) for path in held)


def test_the_call_is_given_the_stage_s_request_and_the_outline_and_asked_once(tmp_path):
    root = _a_workspace(tmp_path)
    model = TheModel([f"{ITEM}: lines 1-30"])

    project_memory.render_for_a_stage(root, model, OPENING, "acceptance_author")
    project_memory.render_for_a_stage(root, model, OPENING, "acceptance_author")

    assert len(model.asked) == 1
    assert OPENING in model.asked[0]
    assert re.search(rf"{re.escape(ITEM)} \(\d+ lines\)\n  \d+-\d+  ", model.asked[0])


def test_a_project_within_its_room_is_held_as_before_and_nothing_is_asked(tmp_path, monkeypatch):
    root = _a_workspace(tmp_path, "python-wordstats")
    model = TheModel([])

    on = project_memory.render_for_a_stage(root, model, OPENING, "technical_lead")
    monkeypatch.setenv("RANGES_CHOSEN_BEFORE_A_READING_STAGE", "off")
    off = project_memory.render_for_a_stage(root, model, OPENING, "technical_lead")

    assert on == off and model.asked == []


def test_another_stage_and_the_size_gate_ask_nothing(tmp_path):
    root = _a_workspace(tmp_path)
    model = TheModel([f"{ITEM}: lines 1-30"])

    project_memory.render_for_a_stage(root, model, OPENING, "specialist_backend_0")
    project_memory.render_for_a_stage(root, model, OPENING, "test_round_1", noted=False)

    assert model.asked == []


def test_only_ranges_of_files_the_project_holds_are_kept_each_within_its_file():
    files = {ITEM: "line\n" * 50, APP: "line\n" * 10}

    found = ranges_chosen_first.ranges_in(
        f"`{ITEM}: lines 40-400`, `{APP}:3-6`, `src/missing.ts: lines 1-9`, `{APP}: lines 5-8`", files)

    assert found == {ITEM: [(40, 50)], APP: [(3, 8)]}


def test_the_call_s_words_avoid_the_product_words():
    assert not BANNED.search(ranges_chosen_first._SYSTEM + ranges_chosen_first._prompt("", ""))
    assert not BANNED.search(ranges_chosen_first.SAID)
