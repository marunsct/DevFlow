"""A criterion that fails in the whole suite and passes alone on the same product is held as unstable, not closed as fixed.

Measured on a gate run: across three attempts at one sprint, criteria the round
raised were closed at dispatch by a passing re-measure of their own tests and
raised again by the next round on the same product; fixers were sent at them
and the sprint failed twice.
"""
from __future__ import annotations

import json
import subprocess

from app.acceptance import suite, unstable
from app.graph import workflow


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), "-c", "user.email=h@example.com", "-c", "user.name=h", *args],
                   check=True, capture_output=True)


def _measured(tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "measured")
    (tmp_path / suite.RESULT_FILE).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / suite.RESULT_FILE).write_text(json.dumps({"fingerprint": unstable.fingerprint(tmp_path)}))
    return tmp_path


def test_the_same_product_is_unchanged_and_any_product_change_is_not(tmp_path):
    root = _measured(tmp_path)
    assert unstable.unchanged_since_the_suite_measured(root)
    (root / "test-results").mkdir()
    (root / "test-results" / "acceptance.xml").write_text("<x/>")
    assert unstable.unchanged_since_the_suite_measured(root), "a runner's output is not the product"
    (root / "app.py").write_text("x = 2\n")
    assert not unstable.unchanged_since_the_suite_measured(root)
    (root / "app.py").write_text("x = 1\n")
    _git(root, "commit", "-qm", "noop", "--allow-empty")
    # A commit that changes no product file leaves the product as it was: the harness commits its own records between
    # measurements, and counting each commit made an unchanged product's unit tests run again (LF.350).
    assert unstable.unchanged_since_the_suite_measured(root), "a commit of nothing is the same product"


def test_a_suite_measurement_records_the_product_it_measured(tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "built")
    assert not unstable.unchanged_since_the_suite_measured(tmp_path), "no measurement yet"

    suite.run(tmp_path)

    assert unstable.unchanged_since_the_suite_measured(tmp_path)


def _dispatched(root, monkeypatch, probe):
    from types import SimpleNamespace

    from app.graph import acceptance_nodes, engineering
    from app.sprint import Defect, RemediationCycle

    monkeypatch.setattr(suite, "is_locked", lambda root: True)
    monkeypatch.setattr(acceptance_nodes, "passing_since_reported", lambda state, criteria: [])
    monkeypatch.setattr(workflow, "_resolved_by_a_measurement", lambda state, defect, **k: ("", ""))
    monkeypatch.setattr(engineering, "no_longer_underlined", lambda root, description: "")
    monkeypatch.setattr(workflow, "_a_dispute_may_be_held_now", lambda state, also=None: True)
    monkeypatch.setattr(workflow, "_the_defect_s_tests_pass", probe)
    defect = Defect(description="[AC-4] Delete removes the note", severity="major", reproduction_steps="r",
                    expected_behavior="e", actual_behavior="a", owner="backend", failing_criteria=["AC-4"])
    cycle = RemediationCycle(sprint_goal="g", defects=[defect])
    return workflow._closed_if_an_earlier_fix_resolved_it(
        {"repository": SimpleNamespace(root_path=str(root)), "test_round": 1}, cycle, 0)


def test_the_product_s_state_is_taken_before_the_probe_runs(tmp_path, monkeypatch):
    """The probe itself rewrote a committed store file, so the product had always 'changed'."""
    root = _measured(tmp_path)

    def the_probe_rewrites_its_store(path, defect):
        (root / "app.py").write_text("x = 2\n")
        return True

    held = _dispatched(root, monkeypatch, the_probe_rewrites_its_store)

    assert held is not None and held["stage"] == "acceptance_dispute", "unstable, not closed as fixed"
    assert "AC-4" in held["dispute_reason"] and "pass when they run alone" in held["dispute_reason"]


def test_a_criterion_passing_alone_on_a_product_changed_since_is_closed_as_fixed(tmp_path, monkeypatch):
    root = _measured(tmp_path)
    (root / "app.py").write_text("x = 2\n")

    closed = _dispatched(root, monkeypatch, lambda path, defect: True)

    assert closed is not None and closed["stage"] == "defect_remediation"
