"""The project memory and its line of held files go on the stage's request, not on a note the harness put before it
(LF.1574).

Measured on a restarted code review: the memory and its closing "[Already in front of you ...]" line were put on the
carry-over note, so the line meant to sit where the model is about to act came between the note and the request.
The note is that review's, word for word; the notice and request an architecture review's.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import HumanMessage

from app.agents import project_memory, stage_memory

CAPTURED = Path(__file__).parent / "captured"
ARCHITECTURE = json.loads((CAPTURED / "architecture_review_opening.json").read_text("utf-8"))
CARRY_OVER = (CAPTURED / "code-review-carry-over-note.txt").read_text("utf-8")


class _Request(SimpleNamespace):
    def override(self, **changes):
        return _Request(**{**self.__dict__, **changes})


def _sent(tmp_path, monkeypatch, opening: list[str]) -> list:
    monkeypatch.setenv("PROJECT_MEMORY", "on")
    for path, text in ARCHITECTURE["files"].items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text, encoding="utf-8")
    (tmp_path / "task-management-dashboard").mkdir()
    sent: list = []
    with stage_memory.remembering("a-note-first"):
        project_memory.build_project_memory_middleware(str(tmp_path)).wrap_model_call(
            _Request(messages=[HumanMessage(content=text) for text in opening], model=None),
            lambda request: sent.append(request.messages))
    stage_memory.forget_everything()
    return sent[-1]


def test_after_the_notes_the_request_carries_the_memory_and_its_closing_line(tmp_path, monkeypatch):
    notice, request = ARCHITECTURE["opening_messages"]
    sent = _sent(tmp_path, monkeypatch, [CARRY_OVER, notice, request])

    assert [str(m.content) for m in sent[:2]] == [CARRY_OVER, notice]
    assert str(sent[2].content).startswith("[Project memory:")
    assert str(sent[2].content).rstrip().endswith("so work from the memory.]")
    assert str(sent[2].content).count(request) == 1
