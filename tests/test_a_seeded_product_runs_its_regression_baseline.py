"""Every seeded run holds its product's own green tests as the contract, whatever a bundle says (plan WS.7).

The regression contract sat behind a premium bundle, off in the code: a deployment without the bundle changed an
existing product with nothing holding what it already did. It is part of the base product now, and each baseline taken
is a `baseline` record in the run's transcript.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import ci
from app.acceptance import regression_contract
from app.graph import engineering
from app.models.model_pin import as_the_run


def _locked(tmp_path: Path, monkeypatch, *, seeded: bool) -> ci.Snapshot | None:
    """Lock the suite in a workspace whose own tests the sandbox reports (the sandbox is cut off)."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    if seeded:
        regression_contract.mark_seeded(workspace, {"type": "git"})
    monkeypatch.setattr(engineering, "ci_applies", lambda root: True)
    monkeypatch.setattr(ci, "commit", lambda root, message: "c0ffee")
    monkeypatch.setattr(ci, "take", lambda root, label, **_: ci.Snapshot(
        label=label, commit="c0ffee", unit={"test_existing_checkout": "passed", "test_not_yet_built": "failed"},
        acceptance={}, unit_ran=True, acceptance_ran=True))
    with as_the_run("run-seeded"):
        engineering.suite_locked(str(workspace))
    return ci.load(str(workspace), "accepted")


def _transcript(tmp_path: Path) -> list[dict]:
    path = tmp_path / "data" / "transcripts" / "run-seeded.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.is_file() else []


@pytest.fixture(autouse=True)
def _nothing_set(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("RUN_TRANSCRIPT", "true")
    for name in ("REGRESSION_CONTRACT", "SWITCH_OVERRIDES_FROM_SETTINGS"):
        monkeypatch.delenv(name, raising=False)
    # The bundle the contract used to follow, off as a deployment without it has it.
    monkeypatch.setenv("PREMIUM_DEEP_VERIFICATION", "off")


def test_a_seeded_product_s_green_tests_are_the_baseline_with_nothing_switched_on(tmp_path, monkeypatch):
    baseline = _locked(tmp_path, monkeypatch, seeded=True)

    assert baseline.passing() == {"unit: test_existing_checkout"}


def test_the_baseline_is_a_record_in_the_run_s_transcript(tmp_path, monkeypatch):
    _locked(tmp_path, monkeypatch, seeded=True)

    baselines = [entry for entry in _transcript(tmp_path) if entry["kind"] == "baseline"]
    assert [(entry["held"], entry["tests"]) for entry in baselines] == [(1, ["unit: test_existing_checkout"])]


def test_a_greenfield_run_s_baseline_stays_empty_and_unrecorded(tmp_path, monkeypatch):
    baseline = _locked(tmp_path, monkeypatch, seeded=False)

    assert baseline.passing() == set()
    assert not [entry for entry in _transcript(tmp_path) if entry["kind"] == "baseline"]


def test_only_the_variable_set_off_on_the_host_turns_it_off(tmp_path, monkeypatch):
    monkeypatch.setenv("REGRESSION_CONTRACT", "off")

    baseline = _locked(tmp_path, monkeypatch, seeded=True)

    assert baseline.passing() == set()
