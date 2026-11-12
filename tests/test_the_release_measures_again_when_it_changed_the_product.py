"""The release runs the suite again when its own clean-ups changed the product after the last run (HR2.G.9).

Command lines, throwaways, untouched templates and the run's own data are cleared after the release's suite run, so
what shipped was never measured as it shipped.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

from app import completion_verdict
from app.graph import delivery


def _suite(monkeypatch, *, changed: bool, failed: list[str], ran: bool = True):
    runs = []
    monkeypatch.setattr("app.acceptance.suite.is_locked", lambda root: True)
    monkeypatch.setattr("app.acceptance.suite.last_result", lambda root: {"fingerprint": "abc", "criteria": {
        "AC-2": {"tests": [{"name": n, "outcome": "passed"} for n in failed]},
        "AC-9": {"tests": [{"name": "[AC-9] failing all along", "outcome": "failed"}]}}})
    monkeypatch.setattr("app.acceptance.unstable.unchanged_since_the_suite_measured", lambda root: not changed)
    tests = [SimpleNamespace(name=n, outcome="failed") for n in failed] + [SimpleNamespace(name="ok", outcome="passed")]

    def run(root):
        runs.append(root)
        return SimpleNamespace(ran=ran, report=SimpleNamespace(tests=tests), problem="no report")

    monkeypatch.setattr("app.acceptance.suite.run", run)
    return runs


def test_a_changed_product_is_measured_again_and_a_failure_is_a_gap_that_blocks(monkeypatch, tmp_path) -> None:
    runs = _suite(monkeypatch, changed=True, failed=["[AC-2] lists every note"])
    gaps = delivery._measured_again_if_it_changed(tmp_path)
    assert runs == [tmp_path]
    assert gaps and gaps[0].startswith(delivery.CHANGED_AT_RELEASE) and "[AC-2] lists every note" in gaps[0]
    assert completion_verdict.is_blocking(gaps[0])


def test_an_unchanged_product_is_not_run_again(monkeypatch, tmp_path) -> None:
    runs = _suite(monkeypatch, changed=False, failed=[])
    assert delivery._measured_again_if_it_changed(tmp_path) == [] and runs == []


def test_a_changed_product_that_still_passes_ships_without_a_gap(monkeypatch, tmp_path) -> None:
    _suite(monkeypatch, changed=True, failed=[])
    assert delivery._measured_again_if_it_changed(tmp_path) == []


def test_the_release_measures_again_after_its_clean_ups() -> None:
    source = inspect.getsource(delivery.release)
    assert source.index("_clear_the_throwaways(root)") < source.index("_measured_again_if_it_changed(root, left_out)") \
        < source.index("release_outcome = release_files.write(root)")



def test_a_test_that_was_failing_before_the_clean_ups_is_not_blamed_on_them(monkeypatch, tmp_path) -> None:
    """The first time this fired, the four tests it named were the deferred criteria's, failing all along."""
    monkeypatch.setattr("app.acceptance.suite.is_locked", lambda root: True)
    monkeypatch.setattr("app.acceptance.suite.last_result", lambda root: {"fingerprint": "abc", "criteria": {
        "AC-9": {"tests": [{"name": "[AC-9] failing all along", "outcome": "failed"}]}}})
    monkeypatch.setattr("app.acceptance.unstable.unchanged_since_the_suite_measured", lambda root: False)
    monkeypatch.setattr("app.acceptance.suite.run", lambda root: SimpleNamespace(
        ran=True, report=SimpleNamespace(tests=[SimpleNamespace(name="[AC-9] failing all along", outcome="failed")])))
    assert delivery._measured_again_if_it_changed(tmp_path) == []
