"""A stage circling over its whole file set is told what to do, not told off.

Both read notices are about one file and both say what not to do. A stage
that cycles three files reaches neither quickly, and neither ever says what
it should do instead.

Measured live on run-cac07d52: `specialist_ui_ux_0`, restarted on a fresh
conversation, made 55 reads of which 50 were files the previous attempt had
already read, cycling `index.html`, `app.js` and `styles.css` about a dozen
times. Both per-file rungs fired - 24 notes and 19 withholdings across the
run - and it kept going until the model-call budget stopped it.

This rung is deliberately not harsher. Measured across all 50 transcripts,
every notice that takes something away does worse than the note above it:

    note, read repeat      91%      withhold the content   58%
    note, write unchanged  64%      refuse the call        38%

The order is inverse to harshness, so the rung that was missing adds
information rather than removing more. It names the exit, which is the one
thing none of the others say.
"""

from __future__ import annotations

import pathlib

import pytest

from app.agents.workspace_backend import (
    READS_BEFORE_WITHHOLDING,
    REPEATED_READS_BEFORE_NAMING_THE_EXIT,
    REPEATS_BEFORE_SAYING_SO,
    WorkspaceBackend,
)

EXIT = "There are two ways out"


@pytest.fixture()
def backend(tmp_path: pathlib.Path):
    for name in ("index.html", "app.js", "styles.css"):
        (tmp_path / name).write_text(f"// {name}\n", encoding="utf-8")
    return WorkspaceBackend(root_dir=str(tmp_path), virtual_mode=True)


def _read(backend, name):
    result = backend.read(f"/{name}")
    data = getattr(result, "file_data", None) or {}
    return str(data.get("content") or "")


def test_reading_one_file_a_few_times_does_not_name_the_exit(backend):
    """Re-reading is ordinary; a model checks its work."""
    for _ in range(REPEATS_BEFORE_SAYING_SO + 1):
        out = _read(backend, "app.js")

    assert EXIT not in out


def test_cycling_the_whole_file_set_does_name_the_exit(backend):
    """The case the per-file rungs are slow to reach."""
    out = ""
    for _ in range(REPEATED_READS_BEFORE_NAMING_THE_EXIT + 3):
        for name in ("index.html", "app.js", "styles.css"):
            out = _read(backend, name)

    assert EXIT in out


def test_it_names_both_exits_and_neither_is_read_again(backend):
    out = ""
    for _ in range(REPEATED_READS_BEFORE_NAMING_THE_EXIT + 3):
        for name in ("index.html", "app.js", "styles.css"):
            out = _read(backend, name)

    assert "structured response" in out
    assert "blockers" in out


def test_the_rung_adds_information_rather_than_removing_it(backend):
    """The measured principle: every rung that takes something away does worse."""
    out = ""
    for _ in range(REPEATED_READS_BEFORE_NAMING_THE_EXIT + 3):
        for name in ("index.html", "app.js", "styles.css"):
            out = _read(backend, name)

    # It still says what the file is, or where the content already is.
    assert "same bytes" in out or "already have it" in out


def test_a_first_read_is_untouched(backend):
    out = _read(backend, "app.js")

    assert "// app.js" in out
    assert EXIT not in out


def test_the_thresholds_stay_in_a_sane_order():
    """Hint, note, withhold - and every rung has to be reachable.

    Lowering `READS_BEFORE_WITHHOLDING` to `REPEATS_BEFORE_SAYING_SO` was
    tried and caught here: the withholding is tested first, so the note rung
    would never have fired once. The note is the most-obeyed rung measured
    across the transcripts (91%, against 58% for withholding), so skipping it
    trades the effective rung for the weaker one.
    """
    assert REPEATS_BEFORE_SAYING_SO < READS_BEFORE_WITHHOLDING, (
        "the note must fire at least once before the content is taken away"
    )
    assert REPEATED_READS_BEFORE_NAMING_THE_EXIT >= REPEATS_BEFORE_SAYING_SO
