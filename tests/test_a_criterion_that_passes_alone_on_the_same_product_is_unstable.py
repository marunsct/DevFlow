"""A criterion that fails in the whole suite and passes alone on the same product is held as unstable, not closed as fixed.

Measured on a gate run: across three attempts at one sprint, criteria the round
raised were closed at dispatch by a passing re-measure of their own tests and
raised again by the next round on the same product; fixers were sent at them
and the sprint failed twice.
"""
from __future__ import annotations

import inspect
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


def test_a_suite_measurement_records_its_fingerprint_and_no_record_is_never_unchanged(tmp_path):
    assert not unstable.unchanged_since_the_suite_measured(tmp_path)
    assert "saved[\"fingerprint\"] = fingerprint(repo_root)" in inspect.getsource(suite._judged)


def test_the_dispatch_holds_a_dispute_for_an_unstable_criterion_and_says_why():
    source = inspect.getsource(workflow._closed_if_an_earlier_fix_resolved_it)
    assert "unstable.unchanged_since_the_suite_measured(root)" in source
    assert 'stage="acceptance_dispute"' in source
    text = unstable.reason(["AC-4"])
    assert "AC-4" in text and "pass when they run alone" in text


def test_the_product_s_state_is_taken_before_the_probe_runs():
    """The probe itself rewrote a committed store file, so the product had always 'changed'."""
    source = inspect.getsource(workflow._closed_if_an_earlier_fix_resolved_it)
    assert source.index("unchanged = unstable.unchanged_since_the_suite_measured(root)") < source.index(
        "if _the_defect_s_tests_pass(Path(root), defect):")
