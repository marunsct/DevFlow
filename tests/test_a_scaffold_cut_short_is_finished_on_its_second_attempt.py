"""A scaffold cut short - a failed first attempt, or a worker restarted mid-install - is finished on its next attempt.

The retry of the whole scaffold found the first attempt's own manifest, took
it for a seeded codebase ("already has a project manifest; it is built on as it
is") and refused, so the retry could never succeed. One run failed at its
scaffold because a deploy restarted the worker during it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.stacks import contract, pack_named
from app.stacks.scaffold import scaffold

PASSED = "<testsuites><testcase name='smoke'/></testsuites>"


class WorkerStopped(Exception):
    pass


def _runner(root: Path, pack, stop_at_install: bool):
    def run(argv, category, working_directory):
        if category == "install" and stop_at_install:
            raise WorkerStopped
        if category != "test":
            return {"returncode": "0", "stdout": "", "stderr": ""}
        unit = list(argv) == pack.commands(working_directory)["unit_test"]
        target = root / working_directory / (pack.unit_report if unit else pack.acceptance_report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(PASSED)
        return {"returncode": "0", "stdout": "", "stderr": ""}

    return run


@pytest.mark.parametrize("name", ["python-http-api", "browser-javascript"])
def test_the_attempt_after_one_cut_short_finishes_the_scaffold(tmp_path: Path, name: str) -> None:
    pack = pack_named(name)
    with pytest.raises(WorkerStopped):
        scaffold(tmp_path, pack, "notes-api", "Notes", run=_runner(tmp_path, pack, stop_at_install=True))

    result = scaffold(tmp_path, pack, "notes-api", "Notes", run=_runner(tmp_path, pack, stop_at_install=False))

    assert result.ok, result.problem
    assert contract.scaffolded(contract.read(tmp_path))


def test_a_seeded_codebase_is_still_built_on_as_it_is(tmp_path: Path) -> None:
    pack = pack_named("python-http-api")
    (tmp_path / "notes-api").mkdir()
    (tmp_path / "notes-api" / "requirements.txt").write_text("flask\n")

    result = scaffold(tmp_path, pack, "notes-api", "Notes", run=_runner(tmp_path, pack, stop_at_install=False))

    assert not result.ok and "built on as it is" in result.problem
    assert (tmp_path / "notes-api" / "requirements.txt").read_text() == "flask\n"


def test_another_pack_s_unfinished_scaffold_is_not_taken_as_this_one_s(tmp_path: Path) -> None:
    other, pack = pack_named("browser-javascript"), pack_named("python-http-api")
    with pytest.raises(WorkerStopped):
        scaffold(tmp_path, other, "notes-api", "Notes", run=_runner(tmp_path, other, stop_at_install=True))
    (tmp_path / "notes-api" / "requirements.txt").write_text("flask\n")

    result = scaffold(tmp_path, pack, "notes-api", "Notes", run=_runner(tmp_path, pack, stop_at_install=False))

    assert not result.ok and "built on as it is" in result.problem
