"""The workspace tells the truth after the run ends.

A failed run's workspace looked exactly like a released one: the product was
there, the suite was there, and nothing said "this did not ship" - the
database knew and the artifacts did not (monitoring-handover §8.3; Initiative
J.6). Every terminal state but a clean release now writes a machine-readable
marker into the workspace root, a clean release clears it, the run's status
API reports it, and the sweeper learned the two stage-note names that were
measured shipping inside stored products (`blocker.txt`, `verification.log`,
4 files across 199 products).
"""

from __future__ import annotations

import json
from pathlib import Path

from app.graph import terminal_state


def test_a_failed_run_s_workspace_is_marked_non_deliverable(tmp_path: Path) -> None:
    terminal_state.mark(tmp_path, status="failed", reason="the suite never locked", stage="release")

    found = terminal_state.read(tmp_path)

    assert found is not None
    assert found["deliverable"] is False
    assert found["status"] == "failed"
    assert found["reason"] == "the suite never locked"
    assert found["stage"] == "release"
    # The marker is one JSON document in the workspace root: any archive of
    # the workspace carries it.
    assert (tmp_path / terminal_state.MARKER).exists()
    assert json.loads((tmp_path / terminal_state.MARKER).read_text())["deliverable"] is False


def test_a_run_with_gaps_is_marked_with_them(tmp_path: Path) -> None:
    terminal_state.mark(tmp_path, status="completed", gaps=["AC-2 ships deferred"], reason="completed with gaps")

    found = terminal_state.read(tmp_path) or {}

    assert found["completion_gaps"] == ["AC-2 ships deferred"]


def test_a_clean_release_clears_the_marker(tmp_path: Path) -> None:
    terminal_state.mark(tmp_path, status="failed", reason="an earlier attempt")

    terminal_state.clear(tmp_path)

    assert terminal_state.read(tmp_path) is None
    # Clearing where nothing was marked is not an error.
    terminal_state.clear(tmp_path)


def test_a_broken_marker_says_nothing_rather_than_something_wrong(tmp_path: Path) -> None:
    (tmp_path / terminal_state.MARKER).write_text("{not json", encoding="utf-8")

    assert terminal_state.read(tmp_path) is None


def test_the_marker_never_fails_the_terminal_write(tmp_path: Path) -> None:
    """A marker that cannot be written must not lose the run's real error:
    marking, clearing and reading a place that is not a directory all answer
    quietly."""
    a_file = tmp_path / "not-a-directory"
    a_file.write_text("x", encoding="utf-8")

    terminal_state.mark(a_file, status="failed", reason="r")
    terminal_state.clear(a_file)
    assert terminal_state.read(a_file) is None


def test_the_runner_marks_every_terminal_state_but_a_clean_release() -> None:
    import inspect

    from app.server import runner

    source = inspect.getsource(runner)

    assert "from app.graph import terminal_state" in source
    assert "terminal_state.mark(" in source
    assert "terminal_state.clear(" in source
    # The cancellation finisher marks too: a cancelled run is not a delivery.
    cancelled = inspect.getsource(runner.WorkflowRunner._finish_cancelled)
    assert "terminal_state.mark(" in cancelled


def test_the_status_api_reports_what_the_marker_says() -> None:
    from app.server.models import RunStatusResponse

    assert "non_deliverable" in RunStatusResponse.model_fields
    assert RunStatusResponse.model_fields["non_deliverable"].default == ""


def test_the_stage_notes_that_shipped_are_sweepable_now() -> None:
    from app.analysis.file_kinds import is_scratch

    assert is_scratch("blocker.txt")
    assert is_scratch("notes-app/blocker.txt")
    assert is_scratch("verification.log")
    assert is_scratch("src/verification.log")
    # Narrow, because the sweeper deletes: product names stay out.
    assert not is_scratch("blockers.md")
    assert not is_scratch("verification.js")
    assert not is_scratch("app.js")
    assert not is_scratch("docs/release-notes.md")
