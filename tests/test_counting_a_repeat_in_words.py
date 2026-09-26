"""A notice that counts repeats must be able to count.

Both notices that tell a stage how many times it has re-read something built
the ordinal by appending "th", so the first three of anything read "1th", "2th",
"3th", and everything past twenty read "21th", "22th", "31th". Seen live through
run-2ac28a2f, whose `specialist_ui_ux_0` was told it was the "22th time this
stage has asked for content it already has".

Cosmetic in isolation and not in aggregate: these strings are emitted dozens of
times per run and are read by a language model being asked to accept that it
has read something enough times. A sentence that cannot count is a poor argument
for that.
"""

from __future__ import annotations

import pytest

from app.agents.workspace_backend import _times


class TestTheOnesThatWereWrong:
    @pytest.mark.parametrize(
        "count,expected",
        [(1, "1st"), (2, "2nd"), (3, "3rd"), (21, "21st"), (22, "22nd"), (23, "23rd"),
         (31, "31st"), (42, "42nd"), (53, "53rd"), (101, "101st"), (122, "122nd")],
    )
    def test_it_now_reads_correctly(self, count, expected):
        assert _times(count) == expected


class TestTheOnesThatWereAlreadyRight:
    @pytest.mark.parametrize(
        "count,expected",
        [(4, "4th"), (5, "5th"), (10, "10th"), (11, "11th"), (12, "12th"), (13, "13th"),
         (14, "14th"), (20, "20th"), (100, "100th"), (111, "111th"), (112, "112th"),
         (113, "113th")],
    )
    def test_the_teens_and_the_rest_are_unchanged(self, count, expected):
        """11, 12 and 13 take "th" however they are reached, including 111-113."""
        assert _times(count) == expected


class TestTheNoticesThatUseIt:
    def test_the_refusal_says_the_ordinal_correctly(self, tmp_path, monkeypatch):
        """The message run-2ac28a2f received, at the count it received it."""
        from app.agents import stage_memory
        from app.agents.workspace_backend import WorkspaceBackend

        monkeypatch.setattr(stage_memory, "current_stage_key", lambda: ("t-x", "s-x"))
        backend = WorkspaceBackend(root_dir=str(tmp_path), virtual_mode=True)
        for _ in range(22):
            backend._count_a_repeated_read()

        message = backend._refuse_a_read_that_returns_nothing_new("app.js")

        assert "22nd time" in message
        assert "22th" not in message

    def test_a_stage_below_the_threshold_is_not_refused(self, tmp_path, monkeypatch):
        """The thresholds are untouched; only how the number is spelled changed."""
        from app.agents import stage_memory
        from app.agents.workspace_backend import WorkspaceBackend

        monkeypatch.setattr(stage_memory, "current_stage_key", lambda: ("t-y", "s-y"))
        backend = WorkspaceBackend(root_dir=str(tmp_path), virtual_mode=True)
        backend._count_a_repeated_read()

        assert backend._refuse_a_read_that_returns_nothing_new("app.js") == ""
