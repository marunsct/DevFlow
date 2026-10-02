"""A file named to be thrown away is not another stage's suite.

A test one stage wrote is kept from the next stage's cleanup, with no way out
offered, because a real suite was once renamed out of the runner's sight. That
rule went by who wrote the file and not by what the file was: one fix stage
left a `tmp_test.js`, the next stage asked to delete it four times, was told
each time that it was a test another stage wrote, and had the tool withheld.
The sweep between stages would have removed the same file without asking.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

import pytest

from app.tools.repository import (
    RepositoryToolError,
    delete_approved_artifact,
    move_approved_artifact,
    write_approved_artifact,
)

A_TEST = "import { test } from 'x';\ntest('adds', () => { expect(1).toBe(1); });\n"


@contextmanager
def _as(stage: str) -> Iterator[None]:
    with patch("app.observability.transcript._stage_from_config", lambda fallback: stage or fallback):
        yield


@pytest.mark.parametrize("left_behind", ["app/tmp_test.js", "app/debug.test.mjs", "app/tests/temp_check.spec.js"])
def test_the_next_stage_is_shown_the_way_to_clear_it(tmp_path: Path, left_behind: str) -> None:
    with _as("defect_fix_2_1"):
        write_approved_artifact(tmp_path, left_behind, A_TEST)

    with _as("specialist_backend_0"):
        with pytest.raises(RepositoryToolError) as refused:
            delete_approved_artifact(tmp_path, left_behind)
        message = str(refused.value)
        assert "defect_fix_2_1 wrote" not in message
        assert "move_artifact" in message

        destination = left_behind + ".probe" if left_behind.endswith("tmp_test.js") else None
        if destination:
            assert destination in message
            move_approved_artifact(tmp_path, left_behind, destination)
            delete_approved_artifact(tmp_path, destination)
            assert not (tmp_path / left_behind).exists()
            assert not (tmp_path / destination).exists()


def test_one_that_holds_no_test_goes_at_once(tmp_path: Path) -> None:
    with _as("defect_fix_2_1"):
        write_approved_artifact(tmp_path, "app/tmp_test.js", "console.log(require('./app'));\n")

    with _as("specialist_backend_0"):
        delete_approved_artifact(tmp_path, "app/tmp_test.js")

    assert not (tmp_path / "app" / "tmp_test.js").exists()


def test_a_suite_with_an_ordinary_name_is_still_kept(tmp_path: Path) -> None:
    with _as("specialist_backend_1"):
        write_approved_artifact(tmp_path, "app/test/cart.spec.js", A_TEST)

    with _as("specialist_testing_2"), pytest.raises(RepositoryToolError) as refused:
        delete_approved_artifact(tmp_path, "app/test/cart.spec.js")

    assert "is a test that specialist_backend_1 wrote" in str(refused.value)
    assert (tmp_path / "app" / "test" / "cart.spec.js").is_file()
