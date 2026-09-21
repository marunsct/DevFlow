"""Asking for fewer lines of a file you have read is not a new read.

Measured on run-d483f554's `specialist_ui_ux_0`, reading the 391-line
`task-manager/app.js` it had written itself two minutes earlier:

    reads  2-11  whole file   withheld from the 4th on   1,111 bytes
    read     12  limit=120    3,483 bytes, returned in full
    reads 12-14  limit=120    withheld on the 3rd
    read     15  limit=100    2,897 bytes, returned in full
    reads 15-17  limit=100    withheld on the 3rd
    read     18  limit=100    withheld

Narrowing the window reset the byte-identical counter and the file came back
whole - twice, after it had already been withheld ten times. About 19,000
characters of lines the stage had already been given, and those six calls are
what carried it to the edge of its model-call budget, where the tools were
withheld and the stage ended.

The span check knew. It printed "You have already read lines 1-120 of this
file in this stage" on reads 12 and 13 and returned the bytes anyway.
"""

from __future__ import annotations

from app.agents.workspace_backend import READS_BEFORE_WITHHOLDING, WorkspaceBackend


def _lines(count: int) -> str:
    return "\n".join(f"line {i}" for i in range(1, count + 1))


def _read(backend: WorkspaceBackend, **kwargs) -> str:
    return backend.read("/app.js", **kwargs).file_data["content"]


def test_a_narrowed_window_stops_returning_the_file(tmp_path) -> None:
    (tmp_path / "app.js").write_text(_lines(391), encoding="utf-8")
    backend = WorkspaceBackend(str(tmp_path), virtual_mode=True)

    whole = _read(backend)
    assert "line 391" in whole

    # Every one of these is a subset of what the first read returned.
    sizes = [len(_read(backend, offset=0, limit=limit)) for limit in (120, 110, 100)]

    assert len(sizes) == READS_BEFORE_WITHHOLDING
    assert sizes[-1] < len(whole) / 4, (
        f"the third window of already-seen lines still returned {sizes[-1]} "
        f"characters against a whole file of {len(whole)}"
    )
    assert "line 50" not in _read(backend, offset=0, limit=90)


def test_the_withheld_result_says_a_narrower_window_will_not_help(tmp_path) -> None:
    """The way out is a range outside what has been read - not a smaller one."""
    (tmp_path / "app.js").write_text(_lines(391), encoding="utf-8")
    backend = WorkspaceBackend(str(tmp_path), virtual_mode=True)

    _read(backend)
    for limit in (120, 110, 100):
        content = _read(backend, offset=0, limit=limit)

    assert "same lines" in content
    assert "a range outside what you have read" in content


def test_lines_never_served_still_come_back(tmp_path) -> None:
    """The refusal applies to already-seen lines of an unchanged file, and to
    nothing else. A stage paging forward through a file is doing its job."""
    (tmp_path / "app.js").write_text(_lines(400), encoding="utf-8")
    backend = WorkspaceBackend(str(tmp_path), virtual_mode=True)

    _read(backend, offset=0, limit=100)
    for _ in range(READS_BEFORE_WITHHOLDING + 2):
        _read(backend, offset=0, limit=50)

    onward = _read(backend, offset=100, limit=100)

    assert "line 150" in onward
    assert "already been given" not in onward


def test_a_write_resets_it(tmp_path) -> None:
    """Keyed on size and mtime, so a specialist that edits and reads back is
    never refused - the reason the byte-identical rung could not cover this."""
    import time

    page = tmp_path / "app.js"
    page.write_text(_lines(391), encoding="utf-8")
    backend = WorkspaceBackend(str(tmp_path), virtual_mode=True)

    _read(backend)
    for limit in (120, 110, 100):
        _read(backend, offset=0, limit=limit)

    time.sleep(0.01)
    page.write_text(_lines(420), encoding="utf-8")

    assert "line 90" in _read(backend, offset=0, limit=100)


def test_the_two_rungs_withhold_on_the_same_count(tmp_path) -> None:
    """One constant, so they cannot drift apart: the byte-identical ladder and
    the already-seen-lines ladder are the same waste seen two ways."""
    import inspect

    source = inspect.getsource(WorkspaceBackend._note_if_already_seen)

    assert "READS_BEFORE_WITHHOLDING" in source
