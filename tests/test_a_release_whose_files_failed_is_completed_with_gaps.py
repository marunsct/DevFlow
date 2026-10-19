"""A release whose packaged CI or container files failed is completed with gaps (Initiative BK).

`stacks/release.py` catches a failed write and says so in `missing`, which went
only into the release decision's rationale: `completion_gaps` was assembled
before the files were written, so the run, the run list, the evidence page and
the bench export all read plain "completed".
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.graph import delivery
from app.stacks import contract, release


@pytest.fixture
def run_release(tmp_path, monkeypatch):
    from app.analysis import integration_checks

    monkeypatch.setattr(integration_checks, "problems_that_break_the_product", lambda root, stack=None, brief="": [])

    def run():
        update = delivery.release(
            {"repository": SimpleNamespace(root_path=str(tmp_path))},
            {"configurable": {}},
            SimpleNamespace(judgement_model=None, checkpointer=None, repo_root=str(tmp_path), allow_subdirectories=True),
        )
        return [str(gap) for gap in update.get("completion_gaps") or []]

    return run


def _a_pack(monkeypatch, files):
    pack = SimpleNamespace(title="Some pack")
    monkeypatch.setattr(contract, "the_pack", lambda root: (pack, {"project": "app", "title": "App"}))
    monkeypatch.setattr(release, "files_for", lambda pack, project, title, package=None: files)


def test_a_failed_release_file_is_a_completion_gap(run_release, monkeypatch):
    _a_pack(monkeypatch, {".github/workflows/ci.yml": "on: push\n"})

    def refuse(self, *args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", refuse)

    gaps = run_release()

    assert any("Adding the release files failed" in gap and "disk full" in gap for gap in gaps)


def test_a_product_no_pack_covers_is_not_given_the_gap(run_release, monkeypatch):
    monkeypatch.setattr(contract, "the_pack", lambda root: None)

    assert not any("release" in gap.lower() and "pipeline" in gap.lower() for gap in run_release())


def test_a_clean_release_adds_no_gap(tmp_path, monkeypatch):
    _a_pack(monkeypatch, {"ci.yml": "on: push\n"})
    monkeypatch.setattr("app.tools.version_control.commit_all", lambda root, message: None)

    outcome = release.write(tmp_path)

    assert outcome.written == ["ci.yml"] and outcome.a_gap == ""
