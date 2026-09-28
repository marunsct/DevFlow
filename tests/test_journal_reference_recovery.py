"""A lost truncation pointer must be recoverable, and only from your own run.

When a command's output does not fit the conversation it is cut to head and tail
and the whole of it is journalled, with a pointer in the gap. An agent that reads
that pointer can read the rest back. An agent that no longer has it could not:
the reference ends in eight random hex characters, so it cannot be reconstructed
from the command, however exactly the agent remembers running it.

The refusal said "use the exact reference from the truncation pointer", which is
advice only to an agent that already has it. Measured on one run, from the
offline audit of its 723 tool calls: eight failed `read_command_output` calls on
invented names of the right shape -
`5-backend-specialist-pytest-stdout-a1b2c3d4.log` - and seven of those eight were
identical repeats. It was the single largest group of costly failures in the run.

The refusal now names what exists, scoped to the run asking. The journal is one
directory under `DATA_DIR`, shared and kept for three days, and the worker runs
two runs at a time, so an unscoped list would offer another run's build log as
readily as this run's - and an agent reading another run's passing tests as its
own is a worse outcome than the error this replaces.
"""

from __future__ import annotations

import pytest

from app.tools import journal


@pytest.fixture
def a_journal(tmp_path, monkeypatch):
    monkeypatch.setenv("CTX_JOURNAL_ROOT", str(tmp_path / "journal"))
    return tmp_path


class TestScopingAnEntryToItsRun:
    @pytest.mark.parametrize("root, expected", [
        ("/app/data/workspaces/default/workspace-run-a0000005-a778-4faa", "run-a0000005"),
        ("/data/workspace-run-a0000008-0d1b-46f0-9456-802c8921d4b1", "run-a0000008"),
        ("", ""),
        (None, ""),
    ])
    def test_the_run_is_read_off_the_workspace_path(self, root, expected):
        assert journal.scope_of(root) == expected

    def test_a_workspace_that_names_no_run_still_gives_a_usable_tag(self):
        """Tests and one-off roots are not named after a run, and must still work."""
        tag = journal.scope_of("/tmp/pytest-of-arun/some-workspace")

        assert tag and "/" not in tag

    def test_an_entry_carries_its_run_in_its_name(self, a_journal):
        reference = journal.write_entry("testing-npm-stdout", "x" * 100, scope="run-abc12345")

        assert reference is not None
        assert "run-abc12345" in reference
        assert journal.read_entry(reference) == "x" * 100

    def test_an_entry_without_a_scope_is_still_written(self, a_journal):
        """`_truncate` is called from paths that have no workspace to name."""
        reference = journal.write_entry("output", "y" * 10)

        assert reference is not None
        assert journal.read_entry(reference) == "y" * 10


class TestListingWhatExists:
    def test_only_this_run_s_entries_are_listed(self, a_journal):
        mine = journal.write_entry("testing-pytest-stdout", "mine", scope="run-aaaaaaa1")
        theirs = journal.write_entry("testing-pytest-stdout", "theirs", scope="run-bbbbbbb2")

        listed = journal.list_entries(scope="run-aaaaaaa1")

        assert mine in listed
        assert theirs not in listed, "another run's build log must not be offered"

    def test_newest_first(self, a_journal):
        import os
        import time

        first = journal.write_entry("one", "1" * 10, scope="run-aaaaaaa1")
        second = journal.write_entry("two", "2" * 10, scope="run-aaaaaaa1")
        root = journal.journal_root()
        now = time.time()
        os.utime(root / first, (now - 60, now - 60))
        os.utime(root / second, (now, now))

        assert journal.list_entries(scope="run-aaaaaaa1")[0] == second

    def test_an_unreadable_journal_suggests_nothing_rather_than_raising(self, monkeypatch):
        """This runs inside an error path; a second failure there is worse."""
        monkeypatch.setenv("CTX_JOURNAL_ROOT", "/definitely/not/a/directory")

        assert journal.list_entries(scope="run-aaaaaaa1") == []

    def test_the_limit_is_respected(self, a_journal):
        for index in range(15):
            journal.write_entry(f"entry{index}", "z" * 10, scope="run-aaaaaaa1")

        assert len(journal.list_entries(scope="run-aaaaaaa1", limit=4)) == 4


class TestWhatTheToolSaysBack:
    def _tool(self, repo_root):
        from app.tools.agent_toolkit import build_journal_read_tool

        return build_journal_read_tool(repo_root)

    def test_a_wrong_reference_is_answered_with_the_real_ones(self, a_journal):
        """The fix: eight guesses become one list."""
        root = a_journal / "workspace-run-aaaaaaa1-1111-2222"
        root.mkdir()
        real = journal.write_entry("testing-pytest-stdout", "the real log", scope="run-aaaaaaa1")

        result = self._tool(str(root)).invoke(
            {"reference": "5-backend-specialist-pytest-stdout-a1b2c3d4.log"}
        )

        assert isinstance(result, dict)
        assert real in result["error"]
        assert "cannot be guessed" in result["error"]

    def test_another_run_s_entries_are_not_offered(self, a_journal):
        root = a_journal / "workspace-run-aaaaaaa1-1111-2222"
        root.mkdir()
        theirs = journal.write_entry("testing-pytest-stdout", "not yours", scope="run-bbbbbbb2")

        result = self._tool(str(root)).invoke({"reference": "invented.log"})

        assert theirs not in result["error"]
        assert "nothing journalled" in result["error"]

    def test_a_correct_reference_still_reads_back(self, a_journal):
        root = a_journal / "workspace-run-aaaaaaa1-1111-2222"
        root.mkdir()
        reference = journal.write_entry("testing-pytest-stdout", "line one\nline two", scope="run-aaaaaaa1")

        result = self._tool(str(root)).invoke({"reference": reference})

        assert "line two" in result

    def test_the_tool_still_works_with_no_root_at_all(self, a_journal):
        """`repo_root` is optional, and its absence must not break the read."""
        reference = journal.write_entry("output", "readable", scope="")

        assert "readable" in self._tool(None).invoke({"reference": reference})
