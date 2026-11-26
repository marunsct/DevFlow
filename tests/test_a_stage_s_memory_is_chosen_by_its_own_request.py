"""A stage's memory is chosen and sized by its own request, not by the note the harness puts before it (LF.1565).

Measured on the latest medium run: a code review restarted on a fresh conversation opened on its carry-over note,
then its request. The memory was chosen by the first message - the note - so the review was given the memory of an
ordinary stage ranked by the note's words: none of the three files its request said were "held whole in the project
memory for this review, with their line numbers" was there numbered, one not at all. And every stage that opens on
the empty-project notice (the advisers, the architect, the architecture review) had its opening sized as if its
request were the notice's few hundred characters.

The request and the workspace are a code review's and an architecture review's, rebuilt from their transcripts; the
carry-over note is the restarted review's, word for word.
"""
from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import HumanMessage
from langchain_core.runnables.config import var_child_runnable_config

from app.agents import project_memory, review_files

CAPTURED = Path(__file__).parent / "captured"
REVIEW = json.loads((CAPTURED / "code_review_opening.json").read_text("utf-8"))
ARCHITECTURE = json.loads((CAPTURED / "architecture_review_opening.json").read_text("utf-8"))
CARRY_OVER = (CAPTURED / "code-review-carry-over-note.txt").read_text("utf-8")


class _Request:
    def __init__(self, messages):
        self.messages, self.model = messages, None

    def override(self, messages):
        return _Request(messages)


def _opened(tmp_path, monkeypatch, files: dict[str, str], messages: list[str], stage: str):
    """What the stage's first call was sent, and the `request_budget` records its opening left."""
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "91776")
    monkeypatch.setenv("MODEL_MAX_OUTPUT_TOKENS", "32000")
    monkeypatch.setenv("PROJECT_MEMORY", "on")
    monkeypatch.setenv("OPENING_ROOM_FOR_REVIEWS", "off")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    root = tmp_path / "workspace"
    for path, text in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text, encoding="utf-8")
    sent: list = []
    token = var_child_runnable_config.set({"configurable": {"app_stage": stage, "app_run_id": "run-opening"}})
    try:
        project_memory.build_project_memory_middleware(str(root)).wrap_model_call(
            _Request([HumanMessage(content=text) for text in messages]), sent.append)
    finally:
        var_child_runnable_config.reset(token)
    path = tmp_path / "data" / "transcripts" / "run-opening.jsonl"
    records = [r for r in map(json.loads, path.read_text().splitlines()) if r.get("kind") == "request_budget"] \
        if path.exists() else []
    return "\n".join(str(m.content) for m in sent[0].messages), records


def test_a_restarted_review_holds_numbered_the_files_its_request_names(tmp_path, monkeypatch):
    request = REVIEW["opening_messages"][0]
    sent, _ = _opened(tmp_path, monkeypatch, REVIEW["files"], [CARRY_OVER, request], REVIEW["stage"])
    named = review_files.held_named_in(request)

    assert named
    assert [path for path in named if f"=== {path} (numbered lines, under review)" not in sent] == []


def test_a_stage_after_the_empty_project_notice_is_sized_with_its_request(tmp_path, monkeypatch):
    notice, request = ARCHITECTURE["opening_messages"]
    (tmp_path / "workspace" / "task-management-dashboard").mkdir(parents=True)
    _, records = _opened(tmp_path, monkeypatch, ARCHITECTURE["files"], [notice, request], "architecture_review")

    assert records
    assert records[-1]["built"] > len(request)


#: The listing each call is given after the request, as the restarted review's first call carried it.
LISTING = ("The workspace as it stands. This is what is there - you do not need to list the directories to find out:\n"
           "  task-management-dashboard/.gitignore (10 lines)\n")


def test_the_ask_is_the_request_between_the_harness_s_notes():
    notice = ARCHITECTURE["opening_messages"][0]
    messages = [HumanMessage(content=CARRY_OVER), HumanMessage(content=notice), HumanMessage(content="the request"),
                {"role": "user", "content": LISTING}, {"role": "assistant", "content": "a reply"},
                HumanMessage(content="a later message")]

    assert project_memory.the_stage_s_ask(messages) == "the request"
