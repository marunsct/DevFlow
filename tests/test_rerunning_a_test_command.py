"""A test runner's own report must not look like a change to the product.

`_written_since` decides whether to tell an agent it has re-run a command
with nothing changed since. It walks the directory the command ran in, and a
test runner writes its report into that directory every single time it runs.
So the command's own output cleared the gate that suppresses the note, and
the note could never fire for any suite that produces a report.

Measured across all 50 stored transcripts: 203 test commands were re-run
inside one stage with no successful write in between, and the ledger note
fired once. Only 2 of the 203 had byte-identical output, because test output
carries timings - so a content digest cannot catch these either, and the
write-gate is the only thing that can.

`test-results/` is present in four of the six most recent workspaces.

These directories are deliberately NOT hidden from listings and reads.
Playwright's `test-results/error-context.md` says why a browser test failed,
and an agent read it to good effect on run-cac07d52.
"""

from __future__ import annotations

import pathlib
import time
from datetime import datetime, timezone

import pytest

from app.tools.repository import IGNORED_DIRECTORIES
from app.tools.sandbox import _RUNNER_OUTPUT_DIRECTORIES, _written_since


@pytest.fixture()
def project(tmp_path: pathlib.Path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.js").write_text("const a = 1;\n", encoding="utf-8")
    moment = datetime.now(timezone.utc).isoformat()
    time.sleep(0.02)
    return tmp_path, moment


@pytest.mark.parametrize("directory", sorted(_RUNNER_OUTPUT_DIRECTORIES))
def test_a_runner_writing_its_report_is_not_a_change(project, directory):
    root, moment = project
    output = root / "app" / directory
    output.mkdir()
    (output / "report.txt").write_text("1 failed", encoding="utf-8")

    assert not _written_since(str(root), moment, "app"), (
        f"{directory}/ is the command's own output; counting it silences the "
        "note that tells an agent it changed nothing"
    )


def test_a_change_to_the_product_still_counts(project):
    root, moment = project
    (root / "app" / "main.js").write_text("const a = 2;\n", encoding="utf-8")

    assert _written_since(str(root), moment, "app")


def test_a_new_source_file_still_counts(project):
    root, moment = project
    (root / "app" / "extra.js").write_text("export const b = 1;\n", encoding="utf-8")

    assert _written_since(str(root), moment, "app")


def test_a_report_beside_a_real_edit_does_not_mask_it(project):
    """The gate must notice the edit even when a report was written too."""
    root, moment = project
    (root / "app" / "test-results").mkdir()
    (root / "app" / "test-results" / "r.txt").write_text("x", encoding="utf-8")
    (root / "app" / "main.js").write_text("const a = 3;\n", encoding="utf-8")

    assert _written_since(str(root), moment, "app")


def test_runner_output_is_still_readable():
    """Hiding these would remove the best diagnostic a browser suite produces."""
    overlap = sorted(_RUNNER_OUTPUT_DIRECTORIES & IGNORED_DIRECTORIES)
    assert not overlap, (
        "these are excluded from the write-gate only; hiding them from listings "
        f"would hide Playwright's error-context.md: {overlap}"
    )
