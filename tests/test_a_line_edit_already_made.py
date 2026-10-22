"""A `replace_lines` whose change is already in the file succeeds, as `edit_artifact` does.

One run's `specialist_backend_0` changed a test file's import line with
`edit_artifact`, then sent `replace_lines` for the same change - its
`expect_start` still the old line - four times. Each was refused with "That
line is not in the file at all now ... Read the file again", although the line
it asked for was already line 12.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.repository import RepositoryToolError, edit_approved_artifact, replace_approved_lines

OLD = "import { createTask, toggleTask, renameTask, deleteTask } from '../app.js';"
NEW = "import { createTask, toggleTask, editTask, filterTasks, deleteTask } from '../app.js';"
SUITE = "import assert from 'node:assert';\nimport { describe, it } from 'node:test';\n" + OLD + "\n\ndescribe('x', () => {});\n"


def test_the_same_change_sent_again_by_line_is_already_applied(tmp_path: Path) -> None:
    (tmp_path / "app.test.mjs").write_text(SUITE, encoding="utf-8")
    edit_approved_artifact(tmp_path, "app.test.mjs", OLD, NEW)

    result = replace_approved_lines(tmp_path, "app.test.mjs", 3, 3, NEW, expect_start=OLD)

    assert result["status"] == "already_applied"
    assert "already in 'app.test.mjs', at line 3" in result["detail"]
    assert (tmp_path / "app.test.mjs").read_text(encoding="utf-8").count(NEW) == 1


def test_a_line_that_is_gone_and_not_replaced_is_still_refused(tmp_path: Path) -> None:
    (tmp_path / "app.test.mjs").write_text(SUITE.replace(OLD, "// removed"), encoding="utf-8")

    with pytest.raises(RepositoryToolError) as refused:
        replace_approved_lines(tmp_path, "app.test.mjs", 3, 3, NEW, expect_start=OLD)

    assert "not what you expected" in str(refused.value)
