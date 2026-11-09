"""Each drafted file's passes and outcome are recorded (harness review HR2.P.5).

Whether a draft's repair held, and why a file went to the agent loop, were log lines only: 111 of 827 drafting calls
were repair passes and none of them could be judged.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from app.graph import drafting
from app.agents.technical_lead import SpecialistTask


def _order(*files: str) -> SpecialistTask:
    return SpecialistTask(specialist_role="backend", task_description="build the store",
                          acceptance_criteria=["works"], files=list(files))


def test_a_draft_refused_for_a_parse_error_records_two_drafts(tmp_path, monkeypatch) -> None:
    notes = []
    monkeypatch.setattr(drafting, "_noted", lambda path, attempt, outcome: notes.append((path, attempt, outcome)))
    monkeypatch.setattr(drafting, "_draft_one", lambda *a, **k: "export const a = 1\n")
    tries = []

    def write(root, path, content):
        tries.append(path)
        if len(tries) == 1:
            raise ValueError("TypeScript cannot parse this file on line 3")

    drafted = drafting.draft_work_orders([_order("app/src/store.ts")], object(), None, str(tmp_path), object(), write=write)

    assert list(drafted) == [0]
    assert [(attempt, outcome.split(":")[0]) for _, attempt, outcome in notes] == [
        ("first", "refused for its content"), ("content-refusal", "accepted"),
    ]


def test_a_draft_left_to_the_loop_says_why(tmp_path, monkeypatch) -> None:
    notes = []
    monkeypatch.setattr(drafting, "_noted", lambda path, attempt, outcome: notes.append((path, attempt, outcome)))
    monkeypatch.setattr(drafting, "_draft_one", lambda *a, **k: "")
    drafting.draft_work_orders([_order("app/src/store.ts")], object(), None, str(tmp_path), object(),
                               write=lambda *a: None)
    assert notes == [("app/src/store.ts", "first", "left to the loop: the draft was empty")]


def test_the_effects_report_counts_the_drafts() -> None:
    path = Path(__file__).resolve().parents[1] / "scripts" / "loop" / "effects.py"
    spec = importlib.util.spec_from_file_location("loop_effects_drafts", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    records = [
        {"kind": "draft", "path": "a", "attempt": "first", "outcome": "accepted"},
        {"kind": "draft", "path": "b", "attempt": "first", "outcome": "accepted"},
        {"kind": "draft", "path": "b", "attempt": "repair-1", "outcome": "accepted"},
        {"kind": "draft", "path": "c", "attempt": "first", "outcome": "left to the loop: the draft was empty"},
    ]
    assert module.draft_lines(records) == [
        "drafts: 3 file(s), 2 accepted at the first pass, 0 after a content refusal; "
        "1 repair pass(es), 1 kept; 1 left to the loop (1 the draft was empty)"
    ]
