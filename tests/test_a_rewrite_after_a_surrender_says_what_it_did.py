"""A surrendered fix stage's rewrite records what it did - wrote, or declined and why (harness review F2).

Measured on 2026-11-07: `SURRENDER_TO_REWRITE` was on in the worker, yet all eight budget-scale fix stages that
wrote nothing since it was built were left open, and nothing said whether the rewrite ran, declined, or wrote nothing.
A mechanism that cannot be seen firing cannot be fixed.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.graph import surrender_to_rewrite as s


def _run(output, rewritten):
    said = []
    s.after_a_surrender(output, lambda: rewritten, note=said.append)
    return said


def test_a_rewrite_that_writes_is_recorded(monkeypatch):
    monkeypatch.setattr(s, "enabled", lambda: True)
    said = _run(SimpleNamespace(changed_files=[]), SimpleNamespace(changed_files=["notes/app.py"]))
    assert said == ["wrote notes/app.py"]


def test_a_rewrite_that_declines_is_recorded(monkeypatch):
    monkeypatch.setattr(s, "enabled", lambda: True)
    assert _run(SimpleNamespace(changed_files=[]), None) == ["declined"]
    assert _run(SimpleNamespace(changed_files=[]), SimpleNamespace(changed_files=[])) == ["declined"]


def test_nothing_is_recorded_when_the_stage_changed_files(monkeypatch):
    monkeypatch.setattr(s, "enabled", lambda: True)
    assert _run(SimpleNamespace(changed_files=["a.py"]), None) == []


def test_the_fix_stage_records_it_with_the_reason(tmp_path, monkeypatch):
    """In the run's own ledger, where the audit reads it: a rewrite the run may not make says why."""
    import the_fix_stage

    from app.agents.specialists import SpecialistOutput
    from app.observability.transcript import read_transcript

    monkeypatch.setenv("SURRENDER_TO_REWRITE", "on")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    # A node run on its own has no graph config to name its run by.
    monkeypatch.setattr("app.observability.transcript._run_id_from_config", lambda: "r")

    the_fix_stage.run(tmp_path, the_fix_stage.a_state(tmp_path), answer=SpecialistOutput(changed_files=[]), approves=False)

    [entry] = [r for r in read_transcript("r", {"defect"}) if r.get("event") == "rewrite after surrender"]
    assert entry["stage"] == "defect_fix_2_0"
    assert entry["detail"] == "declined: the run does not approve its own writes"
