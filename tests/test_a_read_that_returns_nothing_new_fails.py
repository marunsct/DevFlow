"""The last rung of the read ladder is a refusal, because notices stop working.

Measured across the stored transcripts, by what the stage did on the very next
tool call:

    after a note          27.3% read the same file again,   31% did any work
    after a withholding   30.0% read the same file again,
                          61.5% read a *different* file,     8% did any work
    after the stage-wide  93.0% read again
    exit notice

The exit notice fired 515 times across 29 stages, and run-b0db10b1's
`specialist_ui_ux_0` received it 115 times. Withholding the bytes reduces what
a redundant read costs and moves the stage to another file rather than to
work; naming the exit is ignored outright.

What moves this model is an error. The `node -e` refusal was answered by
writing the code to a file 49% of the time and retried in the same shape 9% of
the time - the opposite profile - because a refusal arrives in the channel the
model reads as "that did not work".
"""

from __future__ import annotations

from app.agents.workspace_backend import (
    REPEATED_READS_BEFORE_NAMING_THE_EXIT,
    REPEATED_READS_BEFORE_REFUSING,
    WorkspaceBackend,
)


def _lines(count: int) -> str:
    return "\n".join(f"line {i}" for i in range(1, count + 1))


def _backend(tmp_path):
    (tmp_path / "app.js").write_text(_lines(400), encoding="utf-8")
    (tmp_path / "page.html").write_text(_lines(400), encoding="utf-8")
    return WorkspaceBackend(str(tmp_path), virtual_mode=True)


def _read(backend, path="/app.js", **kwargs):
    return backend.read(path, **kwargs)


def test_it_is_derived_so_the_two_cannot_drift() -> None:
    assert REPEATED_READS_BEFORE_REFUSING == REPEATED_READS_BEFORE_NAMING_THE_EXIT * 2


def test_a_redundant_read_eventually_fails(tmp_path) -> None:
    backend = _backend(tmp_path)

    errors = []
    for _ in range(REPEATED_READS_BEFORE_REFUSING + 4):
        result = _read(backend)
        errors.append(getattr(result, "error", None))

    assert any(errors), "a stage reading one unchanged file forever never failed"
    assert "Refusing to read" in [e for e in errors if e][0]


def test_the_early_reads_still_succeed(tmp_path) -> None:
    """The ladder is not abolished: the first read returns the file, and the
    rungs below this one still return a result."""
    backend = _backend(tmp_path)

    first = _read(backend)

    assert not getattr(first, "error", None)
    assert "line 400" in first.file_data["content"]


def test_a_range_never_served_still_works_afterwards(tmp_path) -> None:
    """What makes the refusal safe: a stage that has genuinely lost its
    context has a way back that a loop does not take."""
    backend = _backend(tmp_path)
    for _ in range(REPEATED_READS_BEFORE_REFUSING + 4):
        _read(backend)

    onward = _read(backend, offset=200, limit=100)

    assert not getattr(onward, "error", None)
    assert "line 250" in onward.file_data["content"]


def test_a_write_clears_it(tmp_path) -> None:
    """The count is keyed on the file's identity, so a specialist that edits
    and reads back is never refused."""
    import time

    backend = _backend(tmp_path)
    for _ in range(REPEATED_READS_BEFORE_REFUSING + 4):
        _read(backend)

    time.sleep(0.01)
    (tmp_path / "app.js").write_text(_lines(450), encoding="utf-8")

    after = _read(backend)

    assert not getattr(after, "error", None)
    assert "line 450" in after.file_data["content"]


def test_the_refusal_names_both_ways_out(tmp_path) -> None:
    """A refusal with nothing to do next is a stage with nothing to do."""
    backend = _backend(tmp_path)
    message = ""
    for _ in range(REPEATED_READS_BEFORE_REFUSING + 4):
        message = getattr(_read(backend), "error", None) or message

    assert "A range you have NOT read still works" in message
    assert "grep" in message
    assert "return your structured response now" in message
    assert "`blockers`" in message


def test_a_stage_reading_different_files_is_not_refused(tmp_path) -> None:
    """The count is of *repeated* reads, not of reads. Paging through a
    project is what a stage is for."""
    (tmp_path / "a.js").write_text(_lines(100), encoding="utf-8")
    (tmp_path / "b.js").write_text(_lines(100), encoding="utf-8")
    (tmp_path / "c.js").write_text(_lines(100), encoding="utf-8")
    backend = WorkspaceBackend(str(tmp_path), virtual_mode=True)

    for name in ("/a.js", "/b.js", "/c.js"):
        result = backend.read(name)
        assert not getattr(result, "error", None)
