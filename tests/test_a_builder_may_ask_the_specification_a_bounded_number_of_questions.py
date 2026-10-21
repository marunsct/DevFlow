"""A builder or fixer may ask the specification, answered by retrieval first and the architect on a miss, a bounded number of times (plan CM.4).

Behind `ASK_SPECIFICATION`, off until measured on the owner's model (a small
model over-asks).
"""
from __future__ import annotations

import inspect
import json
import os
import re
from types import SimpleNamespace
from unittest import mock

from app.agents import ask_specification as ask
from app.agents import specialists

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


class _Architect:
    def __init__(self):
        self.asked = 0

    def invoke(self, messages, **_):
        self.asked += 1
        return SimpleNamespace(content="Pages hold 20 items; this is a decision, consistent with the listing route.")


def _workspace(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technical_specification.md").write_text(
        "# Spec\n\nTokens are signed with HS256 and expire after one hour.\n\nItems are stored per owner.\n")
    return tmp_path


def _asking(tool, stage, question, run="run-x"):
    with mock.patch("app.observability.transcript._stage_from_config", lambda fallback: stage), \
         mock.patch("app.observability.transcript._run_id_from_config", lambda: run):
        return tool.invoke({"question": question})


def test_a_question_the_specification_answers_is_retrieved_and_a_miss_goes_to_the_architect_once(tmp_path):
    root, architect = _workspace(tmp_path), _Architect()
    tool = ask.build_tool(root, architect)

    found = _asking(tool, "specialist_backend_0", "How long do signed tokens last before they expire?")
    assert found["answer_from"] == "what is written already" and "expire after one hour" in found["passages"][0]
    missed = _asking(tool, "specialist_backend_0", "How many items does each listing page hold?")
    assert missed["answer_from"] == "the architect" and architect.asked == 1
    kept = json.loads((root / ask.ANSWERS_FILE).read_text())
    assert kept[0]["question"].startswith("How many items")
    again = _asking(tool, "specialist_backend_1", "How many items does each listing page hold?")
    assert again["answer_from"] == "what is written already" and architect.asked == 1
    assert not BANNED.search(tool.description)


def test_the_asks_are_bounded_per_stage_and_per_run(tmp_path):
    root = _workspace(tmp_path)
    tool = ask.build_tool(root, None)
    assert "error" not in _asking(tool, "defect_fix_1_0", "tokens expire", run="run-y")
    assert "error" in _asking(tool, "defect_fix_1_0", "tokens expire", run="run-y")
    for n in range(ask.MOST_PER_RUN):
        _asking(tool, f"specialist_backend_{n}", "tokens expire", run="run-z")
    assert "asked 12 questions" in _asking(tool, "specialist_backend_99", "tokens expire", run="run-z")["error"]


def test_it_is_offered_only_when_on():
    assert "ask_specification.enabled()" in inspect.getsource(specialists.create_specialist_agent)
    with mock.patch.dict(os.environ, {"ASK_SPECIFICATION": ""}):
        assert not ask.enabled()
