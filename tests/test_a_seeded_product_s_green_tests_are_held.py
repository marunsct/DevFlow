"""A seeded product's own green tests are a contract the change must keep (plan BW.1).

The CI baseline at the suite's lock was empty for every run, so a change that
broke what a seeded product already did was caught by no regression check.
Behind `REGRESSION_CONTRACT`, off until measured.
"""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from app import ci
from app.acceptance import regression_contract
from app.graph import engineering
from app.server import seeding


def test_seeding_marks_the_workspace(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(seeding, "seed_from_git", lambda workspace, url, **_: {"type": "git", "url": url})

    seeding.seed_workspace(tmp_path, SimpleNamespace(type="git", url="https://example.com/r.git"), resolve_upload=None)

    assert regression_contract.seeded(tmp_path)
    assert not regression_contract.seeded(tmp_path / "elsewhere")


def _locked(tmp_path: Path, monkeypatch, switch: str) -> ci.Snapshot | None:
    regression_contract.mark_seeded(tmp_path, {"type": "archive"})
    monkeypatch.setattr(engineering, "ci_applies", lambda root: True)
    monkeypatch.setattr(ci, "commit", lambda root, message: "c0ffee")
    monkeypatch.setattr(ci, "take", lambda root, label, **_: ci.Snapshot(
        label=label, commit="c0ffee", unit={"test_old_signin": "passed", "test_new_due": "failed"},
        acceptance={"test_ac9_signup": "passed"}, unit_ran=True, acceptance_ran=True))
    with mock.patch.dict(os.environ, {"REGRESSION_CONTRACT": switch}):
        engineering.suite_locked(str(tmp_path))
    return ci.load(str(tmp_path), "accepted")


def test_on_the_baseline_holds_what_the_seeded_product_passes_and_a_later_failure_regresses(tmp_path, monkeypatch):
    baseline = _locked(tmp_path, monkeypatch, "on")

    assert baseline.passing() == {"unit: test_old_signin", "acceptance: test_ac9_signup"}
    later = ci.Snapshot(label="after", unit={"test_old_signin": "failed", "test_new_due": "passed"},
                        acceptance={"test_ac9_signup": "passed"}, unit_ran=True, acceptance_ran=True)
    assert ci.regressions(baseline, later) == ["unit: test_old_signin"]


def test_off_the_baseline_is_empty_as_before(tmp_path, monkeypatch):
    baseline = _locked(tmp_path, monkeypatch, "")

    assert baseline.passing() == set()
