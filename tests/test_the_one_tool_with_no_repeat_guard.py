"""`read_command_output` was the only tool that let a failure repeat in silence.

Every other tool that can fail the same way twice says so. Counted across the 24
current-generation runs, failed results that mention a repeat:

    132  read_file
     93  edit_artifact
     90  run_terminal_command
     36  write_artifact
      0  read_command_output

And it was the second-biggest waster of identical failing calls - 19 of them,
with single stages sending one reference 8, 6 and 5 times:

    fd891220  specialist_ui_ux_1  x8  '1717171717-backend-specialist-pytest-stdout-a1b2c3d4.log'
    a000000b  test_round_0        x6  'task-manager/app.js'
    2ac28a2f  specialist_ui_ux_1  x5  'simple-to-do-list-jest-config-cjs-edit-artifact-stdout'

One run is the one that shows the message was not the problem. Its
`specialist_testing_2` was answered, correctly and in full,

    'task-manager/app.test.mjs' looks like a path rather than a journal
    reference: a reference ends in eight random characters. To read a file in
    the workspace, use `read_file`.

and asked for the same reference ten more times.

Refusing is safe here in a way it is not for a command: entries are created under
fresh random names, so a reference that did not resolve cannot start resolving.
No later command can produce the name that was guessed.
"""

from __future__ import annotations

import pytest

from app.agents import stage_memory
from app.tools import agent_toolkit, journal
from app.tools.agent_toolkit import (
    _MISSES_BEFORE_REFUSING,
    _MISSES_BEFORE_SAYING_SO,
)


@pytest.fixture(autouse=True)
def a_clean_tally(monkeypatch):
    stage_memory.forget_everything()
    agent_toolkit._MISSES_OUTSIDE_A_RUN.clear()
    monkeypatch.setattr(stage_memory, "current_stage_key", lambda: ("t-1", "test_round_0"))
    yield
    stage_memory.forget_everything()
    agent_toolkit._MISSES_OUTSIDE_A_RUN.clear()


@pytest.fixture
def a_journal_with_nothing_in_it(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "read_entry", lambda name: None)
    monkeypatch.setattr(journal, "list_entries", lambda scope="", limit=10: [])
    return agent_toolkit.build_journal_read_tool(str(tmp_path))


#: What one run's `specialist_testing_2` sent eleven times.
THE_REFERENCE_IT_KEPT_SENDING = "task-manager/app.test.mjs"


class TestTheRungsItNeverHad:
    def test_the_first_miss_reads_as_it_always_did(self, a_journal_with_nothing_in_it):
        """One miss is ordinary and must not be scolded."""
        result = a_journal_with_nothing_in_it.invoke(
            {"reference": THE_REFERENCE_IT_KEPT_SENDING}
        )

        assert "times now" not in result["error"]
        assert "No journalled output named" in result["error"]

    def test_the_second_miss_says_so(self, a_journal_with_nothing_in_it):
        for _ in range(_MISSES_BEFORE_SAYING_SO):
            result = a_journal_with_nothing_in_it.invoke(
                {"reference": THE_REFERENCE_IT_KEPT_SENDING}
            )

        assert "2 times now" in result["error"]

    def test_the_note_says_it_can_never_resolve(self, a_journal_with_nothing_in_it):
        """Which is what makes asking again pointless rather than merely unlucky."""
        for _ in range(_MISSES_BEFORE_SAYING_SO):
            result = a_journal_with_nothing_in_it.invoke(
                {"reference": THE_REFERENCE_IT_KEPT_SENDING}
            )

        assert "never will" in result["error"]
        assert "fresh random names" in result["error"]

    def test_the_third_miss_is_refused(self, a_journal_with_nothing_in_it):
        for _ in range(_MISSES_BEFORE_REFUSING):
            result = a_journal_with_nothing_in_it.invoke(
                {"reference": THE_REFERENCE_IT_KEPT_SENDING}
            )

        assert result["error"].startswith("Not looking for")

    def test_the_refusal_says_what_to_do_instead(self, a_journal_with_nothing_in_it):
        """Every other refusal in this harness does, and a dead end is worse."""
        for _ in range(_MISSES_BEFORE_REFUSING):
            result = a_journal_with_nothing_in_it.invoke(
                {"reference": THE_REFERENCE_IT_KEPT_SENDING}
            )

        assert "`read_file`" in result["error"]
        assert "truncation pointer" in result["error"]
        assert "structured response" in result["error"]

    def test_a_refused_reference_stops_building_the_long_answer(
        self, tmp_path, monkeypatch
    ):
        """One run sent eleven of these.

        The lookup itself stays: it is a local read, and a reference that somehow
        did resolve should still be served. What stops is the listing and the
        explanation built around it, and - the point - the stage gets a refusal
        rather than one more paragraph to ignore.
        """
        listed: list[str] = []
        monkeypatch.setattr(journal, "read_entry", lambda name: None)
        monkeypatch.setattr(
            journal, "list_entries",
            lambda scope="", limit=10: listed.append(scope) or [],
        )
        tool = agent_toolkit.build_journal_read_tool(str(tmp_path))

        results = [
            tool.invoke({"reference": THE_REFERENCE_IT_KEPT_SENDING})
            for _ in range(11)
        ]

        assert len(listed) == _MISSES_BEFORE_REFUSING - 1, listed
        assert all(
            r["error"].startswith("Not looking for")
            for r in results[_MISSES_BEFORE_REFUSING - 1:]
        )


class TestCountingTheRightThing:
    def test_a_different_reference_starts_from_one(self, a_journal_with_nothing_in_it):
        """A stage that asks about two things has not repeated itself."""
        for _ in range(_MISSES_BEFORE_REFUSING):
            a_journal_with_nothing_in_it.invoke({"reference": "one.log"})

        result = a_journal_with_nothing_in_it.invoke({"reference": "another.log"})

        assert not result["error"].startswith("Not looking for")

    def test_the_tally_survives_a_rebuilt_toolkit(self, tmp_path, monkeypatch):
        """The toolkit is rebuilt with the agent on every approval resume."""
        monkeypatch.setattr(journal, "read_entry", lambda name: None)
        monkeypatch.setattr(journal, "list_entries", lambda scope="", limit=10: [])

        for _ in range(_MISSES_BEFORE_REFUSING):
            tool = agent_toolkit.build_journal_read_tool(str(tmp_path))
            result = tool.invoke({"reference": THE_REFERENCE_IT_KEPT_SENDING})

        assert result["error"].startswith("Not looking for")

    def test_another_stage_is_not_charged_for_it(self, tmp_path, monkeypatch):
        """The tally is per stage, like the repeated-read one."""
        monkeypatch.setattr(journal, "read_entry", lambda name: None)
        monkeypatch.setattr(journal, "list_entries", lambda scope="", limit=10: [])
        tool = agent_toolkit.build_journal_read_tool(str(tmp_path))

        for _ in range(_MISSES_BEFORE_REFUSING):
            tool.invoke({"reference": THE_REFERENCE_IT_KEPT_SENDING})

        monkeypatch.setattr(
            stage_memory, "current_stage_key", lambda: ("t-1", "specialist_backend_0")
        )
        result = tool.invoke({"reference": THE_REFERENCE_IT_KEPT_SENDING})

        assert not result["error"].startswith("Not looking for")


class TestTheToolStillWorks:
    def test_a_real_reference_reads(self, tmp_path, monkeypatch):
        monkeypatch.setattr(journal, "read_entry", lambda name: "the full output\n")
        tool = agent_toolkit.build_journal_read_tool(str(tmp_path))

        assert "the full output" in tool.invoke(
            {"reference": "1790474922-run-x-npm-stdout-42c95e2d.log"}
        )

    def test_a_success_after_a_miss_is_not_blocked(self, tmp_path, monkeypatch):
        """Only the reference that missed is counted, never the tool."""
        monkeypatch.setattr(journal, "read_entry",
                            lambda name: None if name == "bad.log" else "output\n")
        monkeypatch.setattr(journal, "list_entries", lambda scope="", limit=10: [])
        tool = agent_toolkit.build_journal_read_tool(str(tmp_path))

        for _ in range(_MISSES_BEFORE_REFUSING + 2):
            tool.invoke({"reference": "bad.log"})

        assert "output" in tool.invoke({"reference": "1790474922-run-x-npm-stdout-42c95e2d.log"})

    def test_the_listing_still_names_what_exists(self, tmp_path, monkeypatch):
        monkeypatch.setattr(journal, "read_entry", lambda name: None)
        monkeypatch.setattr(
            journal, "list_entries",
            lambda scope="", limit=10: ["1790474922-run-x-npm-stdout-42c95e2d.log"],
        )
        tool = agent_toolkit.build_journal_read_tool(str(tmp_path))

        result = tool.invoke({"reference": "guessed.log"})

        assert "1790474922-run-x-npm-stdout-42c95e2d.log" in result["error"]

    def test_the_path_redirect_survives(self, a_journal_with_nothing_in_it):
        """Added earlier this session, and it must still reach the second miss.

        The workspace here is empty, so the redirect takes its "and there is no
        file of that name either" form - which is the form one run needed.
        """
        for _ in range(_MISSES_BEFORE_SAYING_SO):
            result = a_journal_with_nothing_in_it.invoke(
                {"reference": THE_REFERENCE_IT_KEPT_SENDING}
            )

        assert "looks like a path rather than a journal reference" in result["error"]
        assert "no file of that name anywhere in the workspace" in result["error"]
