"""A requested change repeated word for word must be flagged as a repeat.

`revision_comments` accumulates, so a lead on its second revision is handed the
same words twice and nothing tells it the measurement did not move. Round two
then reads exactly like round one and gets answered the same way.

Measured on run-ad4815da, which died on `MAX_MILESTONE_REVISIONS`. Its first two
milestone reviews were byte-identical, both blocking on:

    The product exceeds the stated 500-line code limit. The cross-file check
    confirms 506 lines of code (neither blank nor comment) across 3 application
    files.

Six lines over, asked for twice in the same words. The third round did get under
the limit - by deleting `updateTask`, which `app.test.mjs` still called at lines
300-304, so `npm test` exited 1 and that became the new blocking finding. The run
stopped there, having spent four sprints.

So the note says both things that run demonstrated: the change is a repeat, and
meeting a size limit by removing delivered behaviour is not meeting it.
"""

from __future__ import annotations

import pytest

from app.agents.technical_lead import (
    _a_change_asked_for_twice,
    build_milestone_revision_request,
)

#: The finding that was given twice, as the review wrote it.
THE_LINE_LIMIT = (
    "The product exceeds the stated 500-line code limit. The cross-file check "
    "confirms 506 lines of code (neither blank nor comment) across 3 application "
    "files."
)


class TestWhenItFires:
    def test_the_same_change_twice_is_called_a_repeat(self) -> None:
        note = _a_change_asked_for_twice([THE_LINE_LIMIT, THE_LINE_LIMIT])

        assert "SAME CHANGE YOU WERE GIVEN LAST ROUND" in note

    def test_only_whitespace_differs_and_it_still_fires(self) -> None:
        """A re-render can change spacing without changing the finding."""
        spaced = THE_LINE_LIMIT.replace(" ", "  ")

        assert _a_change_asked_for_twice([THE_LINE_LIMIT, spaced]) != ""

    def test_a_first_round_says_nothing(self) -> None:
        assert _a_change_asked_for_twice([THE_LINE_LIMIT]) == ""

    def test_a_different_finding_says_nothing(self) -> None:
        """Round three raised the test failure; that is progress, not a repeat."""
        moved_on = "Test suites reference removed Sprint 2 functionality."

        assert _a_change_asked_for_twice([THE_LINE_LIMIT, moved_on]) == ""

    def test_a_reworded_finding_says_nothing(self) -> None:
        """Deliberately strict. A review that adds detail has done something."""
        fuller = f"{THE_LINE_LIMIT} Largest: task-manager/app.js (198)."

        assert _a_change_asked_for_twice([THE_LINE_LIMIT, fuller]) == ""

    @pytest.mark.parametrize("comments", ([], [""], ["   "], [THE_LINE_LIMIT, ""]))
    def test_nothing_to_compare_says_nothing(self, comments: list[str]) -> None:
        assert _a_change_asked_for_twice(comments) == ""

    def test_an_older_repeat_is_not_dredged_up(self) -> None:
        """Only the round just given matters; an older one was moved past."""
        assert _a_change_asked_for_twice([THE_LINE_LIMIT, THE_LINE_LIMIT, "something else"]) == ""


class TestWhatItSays:
    def test_it_asks_for_the_file_and_the_edit(self) -> None:
        note = _a_change_asked_for_twice([THE_LINE_LIMIT, THE_LINE_LIMIT])

        assert "Name the file and the specific edit" in note

    def test_it_forbids_meeting_a_limit_by_deleting_behaviour(self) -> None:
        """The remedy that ended run-ad4815da."""
        note = _a_change_asked_for_twice([THE_LINE_LIMIT, THE_LINE_LIMIT])

        assert "Do NOT meet it by deleting" in note
        assert "tests that cover it" in note

    def test_it_offers_what_to_remove_instead(self) -> None:
        note = _a_change_asked_for_twice([THE_LINE_LIMIT, THE_LINE_LIMIT])

        for allowed in ("duplication", "dead code", "comments"):
            assert allowed in note


class TestItReachesTheLead:
    def test_the_request_carries_the_note_on_a_repeat(self) -> None:
        request = build_milestone_revision_request(
            '{"selected_sprint_goal": "x"}', [THE_LINE_LIMIT, THE_LINE_LIMIT]
        )
        content = request["messages"][0]["content"]

        assert "SAME CHANGE YOU WERE GIVEN LAST ROUND" in content

    def test_the_request_is_unchanged_on_a_first_revision(self) -> None:
        request = build_milestone_revision_request(
            '{"selected_sprint_goal": "x"}', [THE_LINE_LIMIT]
        )
        content = request["messages"][0]["content"]

        assert "SAME CHANGE" not in content
        # The instruction that was always there must survive.
        assert "DELEGATED TASK" in content
