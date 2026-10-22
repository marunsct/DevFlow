"""A milestone revision assigns what the review asked for, not the whole plan again.

The technical lead revising a milestone plan is given the previous plan and
the review's new comments. One run's second revision kept the previous plan's
tasks - a stray CSS brace and a dead rule, both removed a revision earlier and
not mentioned by the review that sent it back - and added the new ones. The
specialist sent back to them found nothing to fix and spent its turns
re-reading `style.css` to be sure: fifteen refused reads and a 21,000-token reply.
"""

from __future__ import annotations

from app.agents.technical_lead import build_milestone_revision_request


def _prompt() -> str:
    request = build_milestone_revision_request(
        '{"delegated_tasks": [{"task_description": "Remove the stray brace in style.css"}]}',
        ["[major] saveTasks() never checks window.__storageUnavailable."],
    )
    return " ".join(request["messages"][0]["content"].split())


def test_the_previous_tasks_are_said_to_be_done() -> None:
    assert "The tasks in the plan above HAVE ALREADY BEEN CARRIED OUT" in _prompt()
    assert "Do not assign them again" in _prompt()


def test_only_a_requested_change_earns_a_task() -> None:
    prompt = _prompt()

    assert "A task belongs in this revision only if one of the requested changes asks for it" in prompt
    assert "work the review does not mention is done" in prompt


def test_the_requested_change_still_reaches_the_lead() -> None:
    assert "saveTasks() never checks window.__storageUnavailable" in _prompt()
