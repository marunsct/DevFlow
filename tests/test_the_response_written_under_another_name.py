"""The structured response written as a file, recognised by its content.

`_the_response_it_should_be_returning` refuses it by name, and the name is
whatever the agent invents. Five runs died on this loop and the name check
caught three:

    one run  docs/structured_response.md         32 writes
    one run  todo-list/structured_response.json   8
    one run  docs/structured_response.json        4
    one run  final_response.json                  6   - fell through
    one run  docs/summary.json                    5   - fell through

Fifty-five writes across the five, every one carrying the same thing:
`{"changed_files": [...], "decisions": [...], "tests": [...]}`. Only the
filename varies, so the content is what this reads.

Eighteen of the fifty-five recorded run failures are a stage repeating one
write until the loop guard stops it, and this is the largest single cause
among them.
"""

from __future__ import annotations

import json

import pytest

from app.tools.repository import (
    RepositoryToolError,
    _the_response_written_under_another_name,
    write_approved_artifact,
)

A_RESPONSE = {
    "changed_files": ["app.js"],
    "decisions": ["Used node:test"],
    "tests": ["app.test.mjs"],
    "verification": [],
    "risks": [],
    "blockers": [],
}


@pytest.mark.parametrize(
    "path",
    [
        "final_response.json",
        "final_output.json",
        "docs/summary.json",
        "docs/structured_response.json",
        "some_name_nobody_has_used_yet.json",
    ],
)
def test_the_response_is_refused_under_any_name(tmp_path, path):
    (tmp_path / "docs").mkdir()
    with pytest.raises(RepositoryToolError) as refusal:
        write_approved_artifact(tmp_path, path, json.dumps(A_RESPONSE))
    assert "returned, not written" in str(refusal.value)


def test_it_names_the_fields_that_gave_it_away(tmp_path):
    with pytest.raises(RepositoryToolError) as refusal:
        write_approved_artifact(tmp_path, "final_response.json", json.dumps(A_RESPONSE))
    assert "changed_files" in str(refusal.value)


def test_it_says_to_stop_calling_tools(tmp_path):
    """A refusal that does not say what to do instead is how the loop starts."""
    with pytest.raises(RepositoryToolError) as refusal:
        write_approved_artifact(tmp_path, "final_response.json", json.dumps(A_RESPONSE))
    assert "Stop calling tools and return the structured response" in str(refusal.value)


@pytest.mark.parametrize(
    "content",
    [
        json.dumps({"name": "p", "version": "1.0.0", "scripts": {"test": "node --test"}}),
        json.dumps([{"id": 1, "title": "Buy milk", "completed": False}]),
        json.dumps({"tests": "on"}),
        json.dumps({"tests": "on", "documentation": "yes"}),
        "export function addTask() {}\n",
        "# A heading\n\nSome prose.\n",
        "not json at all",
        "null",
    ],
)
def test_ordinary_content_is_left_alone(tmp_path, content):
    assert _the_response_written_under_another_name(("p", "thing.json"), content) is None


def test_two_matching_fields_are_a_coincidence_and_three_are_not(tmp_path):
    """`summary` and `tests` alone could be some other document's keys; every
    real instance in the corpus carries five or more."""
    assert (
        _the_response_written_under_another_name(
            ("x.json",), json.dumps({"tests": [], "summary": ""})
        )
        is None
    )
    assert _the_response_written_under_another_name(
        ("x.json",), json.dumps({"tests": [], "summary": "", "risks": []})
    )


def test_the_one_instance_in_the_corpus_is_recognised():
    """One run's `final_output.json`, the only file of 660 that trips it."""
    assert _the_response_written_under_another_name(
        ("final_output.json",),
        json.dumps(
            {
                "changed_files": [],
                "decisions": ["Unable to execute tests"],
                "tests": ["app.test.mjs"],
                "verification": [],
            }
        ),
    )


def test_every_form_of_this_refusal_shares_one_repeat_key():
    """The loop guard must count these as one event, not as many.

    `_the_same_refusal` keys on the first 60 characters after the colon. The
    field list varies with whatever the agent included, so it comes after the
    invariant sentence - a varying opening would reset the repeat count on
    every attempt, which is the exact weakness that helper exists to close.
    Leading with the shared sentence also makes this share a key with the
    by-name refusal, so a stage alternating between the two still counts up.
    """
    from app.agents.repeated_queries import _the_same_refusal
    from app.tools.repository import _the_response_it_should_be_returning

    forms = [
        _the_response_written_under_another_name(
            ("final_response.json",),
            json.dumps({"changed_files": [], "decisions": [], "tests": []}),
        ),
        _the_response_written_under_another_name(
            ("docs", "summary.json"),
            json.dumps({"risks": [], "blockers": [], "documentation": [], "role": "x"}),
        ),
        _the_response_it_should_be_returning(("docs", "structured_response.md")),
    ]
    keys = {_the_same_refusal(json.dumps({"error": form})) for form in forms}
    assert len(keys) == 1, keys
    assert keys.pop() == "your structured response is returned, not written"
