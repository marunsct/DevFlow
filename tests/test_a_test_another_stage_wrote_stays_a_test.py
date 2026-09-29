"""A test one stage wrote cannot be renamed out of the suite by another.

The delete refusal offers a way out for a probe a stage wrote for itself:
rename it to a name the runner does not collect, then delete that. One run's
`specialist_testing_2` took it for a 100-line suite `specialist_backend_1` had
written. One assertion failed, so it wrote a replacement and moved the original
to `test/app.e2e.spec.js.bak` - out of the suite, and left in the product.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

import pytest

from app.analysis import project_memory
from app.tools.repository import (
    RepositoryToolError,
    delete_approved_artifact,
    move_approved_artifact,
    write_approved_artifact,
)

SUITE = "app/test/app.e2e.spec.js"


@contextmanager
def _as(stage: str) -> Iterator[None]:
    with patch("app.observability.transcript._stage_from_config", lambda fallback: stage or fallback):
        yield


def _written_by(root: Path, stage: str, path: str = SUITE) -> None:
    with _as(stage):
        write_approved_artifact(root, path, "import { test } from 'x';\ntest('adds', () => {});\n")


def test_the_creator_is_kept_when_another_stage_edits_it(tmp_path: Path) -> None:
    _written_by(tmp_path, "specialist_backend_1")
    project_memory.record(tmp_path, SUITE, "specialist_testing_2")

    assert project_memory.who_created(tmp_path, SUITE) == "specialist_backend_1"
    assert project_memory.who_changed(tmp_path, SUITE) == "specialist_testing_2"


def test_moving_another_stage_s_test_out_of_the_suite_is_refused(tmp_path: Path) -> None:
    _written_by(tmp_path, "specialist_backend_1")

    with _as("specialist_testing_2"), pytest.raises(RepositoryToolError) as refused:
        move_approved_artifact(tmp_path, SUITE, SUITE + ".bak")

    assert "is a test that specialist_backend_1 wrote" in str(refused.value)
    assert "correct that assertion in place" in str(refused.value)
    assert (tmp_path / SUITE).is_file()


def test_its_delete_refusal_does_not_offer_the_rename(tmp_path: Path) -> None:
    _written_by(tmp_path, "specialist_backend_1")

    with _as("specialist_testing_2"), pytest.raises(RepositoryToolError) as refused:
        delete_approved_artifact(tmp_path, SUITE)

    assert "move_artifact" not in str(refused.value)
    assert "is a test that specialist_backend_1 wrote" in str(refused.value)


def test_moving_it_to_another_test_name_is_allowed(tmp_path: Path) -> None:
    """Reorganising a suite is not removing it."""
    _written_by(tmp_path, "specialist_backend_1")

    with _as("specialist_testing_2"):
        move_approved_artifact(tmp_path, SUITE, "app/tests/app.e2e.spec.js")

    assert (tmp_path / "app/tests/app.e2e.spec.js").is_file()


def test_a_probe_the_stage_wrote_itself_keeps_its_way_out(tmp_path: Path) -> None:
    probe = "app/debug.test.mjs"
    _written_by(tmp_path, "specialist_testing_2", probe)

    with _as("specialist_testing_2"):
        with pytest.raises(RepositoryToolError) as refused:
            delete_approved_artifact(tmp_path, probe)
        assert "move_artifact" in str(refused.value)
        move_approved_artifact(tmp_path, probe, "app/debug.mjs")
        delete_approved_artifact(tmp_path, "app/debug.mjs")

    assert not (tmp_path / "app/debug.mjs").exists()


def test_outside_a_run_nothing_changes(tmp_path: Path) -> None:
    _written_by(tmp_path, "specialist_backend_1")

    with _as(""):
        move_approved_artifact(tmp_path, SUITE, "app/test/app.e2e.js.probe")
