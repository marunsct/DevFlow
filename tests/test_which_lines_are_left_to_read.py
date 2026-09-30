""""A range you have NOT read still works" named no range.

The refusal at the top of the read ladder told a stage to ask for a range it had
not read, and named neither the ranges already served nor the length of the file.
There was no way to choose one except by guessing, and a stage that guesses asks
for the same range again.

Measured on one run, whose `specialist_documentation_5` sent

    read_file  task-manager/app.js  offset=50  limit=50

28 times, refused on every one after the twelfth. It was the largest single waste
in that run.

The harness knew both halves. The served line numbers are in `read_spans` in
stage memory - the same record the withholding rung reads - and the length is the
file in front of it.

Same shape as `_where_the_files_it_named_actually_are` and
`_the_tasks_this_project_defines`: name what is there instead of only what is
refused.
"""

from __future__ import annotations

import tempfile

import pytest

from app.agents import stage_memory
from app.agents.workspace_backend import (
    REPEATED_READS_BEFORE_REFUSING,
    WorkspaceBackend,
)


@pytest.fixture
def a_refusing_stage(monkeypatch):
    """A backend whose read ladder has reached its refusing rung."""
    stage_memory.forget_everything()
    monkeypatch.setattr(
        stage_memory, "current_stage_key", lambda: ("t-1", "specialist_documentation_5")
    )
    backend = WorkspaceBackend(root_dir=tempfile.mkdtemp(), virtual_mode=True)
    for _ in range(REPEATED_READS_BEFORE_REFUSING):
        backend._count_a_repeated_read()
    yield backend
    stage_memory.forget_everything()


def _served(lines: set[int]) -> None:
    stage_memory.store("read_spans", {})["app.js"] = ("digest", lines, 5)


class TestNamingWhatIsLeft:
    def test_the_lines_already_given_are_named(self, a_refusing_stage):
        _served(set(range(1, 101)))

        message = a_refusing_stage._refuse_a_read_that_returns_nothing_new("app.js", 214)

        assert "You have been given lines 1-100 of 214" in message

    def test_the_lines_not_given_are_named(self, a_refusing_stage):
        """The whole point: "a range you have NOT read" made choosable."""
        _served(set(range(1, 101)))

        message = a_refusing_stage._refuse_a_read_that_returns_nothing_new("app.js", 214)

        assert "have NOT been given are 101-214" in message

    def test_scattered_reads_are_described_as_ranges(self, a_refusing_stage):
        """A stage reads in slices, so the answer has to collapse them."""
        _served(set(range(1, 21)) | set(range(51, 71)) | set(range(101, 111)))

        message = a_refusing_stage._refuse_a_read_that_returns_nothing_new("app.js", 214)

        assert "lines 1-20, 51-70, 101-110 of 214" in message
        assert "21-50, 71-100, 111-214" in message

    def test_a_fully_read_file_says_there_is_nothing_left(self, a_refusing_stage):
        """Which is a different instruction: stop reading, not read elsewhere."""
        _served(set(range(1, 215)))

        message = a_refusing_stage._refuse_a_read_that_returns_nothing_new("app.js", 214)

        assert "which is the whole file (214 lines)" in message
        assert "no range of it left to read" in message

    def test_a_long_list_of_ranges_is_capped(self, a_refusing_stage):
        every_other = {n for n in range(1, 60) if n % 2}
        _served(every_other)

        message = a_refusing_stage._refuse_a_read_that_returns_nothing_new("app.js", 214)

        assert "more" in message

    def test_a_single_line_reads_as_one_number(self, a_refusing_stage):
        _served({7})

        message = a_refusing_stage._refuse_a_read_that_returns_nothing_new("app.js", 214)

        assert "given lines 7 of 214" in message


class TestWhenItCannotSay:
    def test_no_record_of_what_was_read(self, a_refusing_stage):
        message = a_refusing_stage._refuse_a_read_that_returns_nothing_new("app.js", 214)

        assert "You have been given" not in message
        assert "A range you have NOT read still works" in message

    def test_no_line_count(self, a_refusing_stage):
        """Without a length there are no unread lines to name."""
        _served(set(range(1, 101)))

        message = a_refusing_stage._refuse_a_read_that_returns_nothing_new("app.js", 0)

        assert "whole file" in message or "You have been given lines 1-100" in message

    def test_an_empty_span_record(self, a_refusing_stage):
        _served(set())

        assert "You have been given" not in (
            a_refusing_stage._refuse_a_read_that_returns_nothing_new("app.js", 214)
        )

    def test_a_malformed_record_does_not_raise(self, a_refusing_stage):
        stage_memory.store("read_spans", {})["app.js"] = ("digest", "not a set", 5)

        assert a_refusing_stage._refuse_a_read_that_returns_nothing_new("app.js", 214)

    def test_a_different_file_is_not_described(self, a_refusing_stage):
        _served(set(range(1, 101)))

        assert "You have been given" not in (
            a_refusing_stage._refuse_a_read_that_returns_nothing_new("other.js", 214)
        )


class TestTheLadderIsUnchanged:
    def test_a_stage_below_the_threshold_is_not_refused(self, monkeypatch):
        stage_memory.forget_everything()
        monkeypatch.setattr(stage_memory, "current_stage_key", lambda: ("t-2", "s"))
        backend = WorkspaceBackend(root_dir=tempfile.mkdtemp(), virtual_mode=True)
        backend._count_a_repeated_read()

        assert backend._refuse_a_read_that_returns_nothing_new("app.js", 214) == ""

    def test_the_rest_of_the_refusal_survives(self, a_refusing_stage):
        _served(set(range(1, 101)))

        message = a_refusing_stage._refuse_a_read_that_returns_nothing_new("app.js", 214)

        assert "12th time this stage has asked" in message
        assert "`blockers`" in message
        assert "`grep`" in message

    def test_both_call_sites_pass_the_line_count(self):
        """A site that forgot it would silently lose the whole answer."""
        import inspect

        from app.agents import workspace_backend

        source = inspect.getsource(workspace_backend)

        assert source.count("_refuse_a_read_that_returns_nothing_new(") == 3
        # Three: the two refusal sites, and `_the_part_it_covered`, which says
        # whether a repeated read was the whole file or a window of it.
        assert source.count("self._lines_in_the_file(result, content)") == 3


class TestTheLengthIsTheFileNotTheWindow:
    """A ranged read passed the length of its window as the file's length.

    Measured on one run's `test_round_0`, refused `offset=241 limit=35` on a
    271-line `index.html`:

        You have been given lines 1-271, which is the whole file (31 lines).
    """

    @pytest.fixture
    def a_read_file(self, a_refusing_stage):
        root = a_refusing_stage.cwd
        (root / "index.html").write_text(
            "".join(f"<p>{n}</p>\n" for n in range(1, 272)), encoding="utf-8"
        )
        return a_refusing_stage

    def _refused_tail_read(self, backend):
        backend.read("/index.html", offset=0, limit=400)
        for _ in range(20):
            result = backend.read("/index.html", offset=240, limit=35)
            if result.error:
                return result.error
        raise AssertionError("the repeated tail read was never refused")

    def test_the_refusal_names_the_file_s_length(self, a_read_file):
        message = self._refused_tail_read(a_read_file)

        assert "which is the whole file (271 lines)" in message

    def test_the_window_s_length_is_not_called_the_file_s(self, a_read_file):
        message = self._refused_tail_read(a_read_file)

        assert "(31 lines)" not in message

    def test_a_result_without_a_total_falls_back_to_the_window(self):
        class NoTotal:
            total_lines = None

        assert WorkspaceBackend._lines_in_the_file(NoTotal(), "a\nb\nc") == 3
