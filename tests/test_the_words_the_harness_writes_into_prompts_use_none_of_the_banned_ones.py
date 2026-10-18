"""The fixed words the day's changes put in front of the model use none of the banned ones (plan item AO.10).

Every new prompt rule gets a test banning the whole words task, tasks, to-do,
todo, button, click and checkbox. Three of the day's additions had none: the
command tool's network sentence, the project-memory change note, and the
completion-gap strings.
"""
from __future__ import annotations

import re
from unittest import mock

from app.agents import project_memory, settled_answer
from app.graph import delivery
from app.tools import agent_toolkit, sandbox

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_the_command_tool_s_text_in_both_modes():
    for mode in (sandbox.IN_CONTAINER_MODE, "docker"):
        with mock.patch.object(sandbox, "execution_mode", lambda mode=mode: mode):
            assert not BANNED.search(agent_toolkit.build_terminal_command_tool("/tmp").description), mode


def test_the_project_memory_change_note_in_both_forms(monkeypatch):
    before, after = {"app/a.js": "one\n"}, {"app/a.js": "two\n"}
    for withheld in (True, False):
        monkeypatch.setattr(settled_answer, "the_read_tool_is_withheld", lambda withheld=withheld: withheld)
        assert not BANNED.search(project_memory.changes_since(before, after))


def test_the_completion_gap_strings():
    state = {"decisions": [{"decision": delivery.RECORDED_AS_RISKS, "id": "D-1", "rationale": "x\nfinding one"}]}
    gaps = delivery._findings_recorded_as_risks(state)
    assert gaps
    # The fixed sentences the release writes, read out of its source.
    source = open(delivery.__file__, encoding="utf-8").read()
    sentences = re.findall(r'gaps\.append\(\s*"([^"]+)"', source) + re.findall(r'return "(The product ships[^"]+)"', source)
    assert len(sentences) >= 2
    assert not any(BANNED.search(text) for text in [*gaps, *sentences])


def test_the_steering_and_lesson_headers():
    from app.plugins import lessons
    from app.server import steering

    assert not BANNED.search(steering.as_instructions.__doc__ or "")
    assert not BANNED.search("=== THE OWNER'S DIRECTION FOR THIS RUN ===\nThe owner sent these while the run was going; they come before any other preference:")
    assert not BANNED.search("=== LESSONS FROM EARLIER RUNS ===")
    assert lessons.MOST_RULE_LINES == 2
