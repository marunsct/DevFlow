"""A fix split into "its tests only" keeps the dependency declarations those tests need.

Measured on one run: a fix wrote a guard in the product, a unit test for it and a test-only package in the manifest. The
guard broke an acceptance test, so the harness kept the tests and put the rest back - the manifest and its lock file
with it - and the next round raised "cannot find package" for a package the fix had declared, costing a sprint attempt.
"""
from __future__ import annotations

from app import ci
from app.graph import engineering

BEFORE = ci.Snapshot(label="b", unit_ran=True, acceptance_ran=True,
                     unit={"old": "passed"}, acceptance={"[AC-1] lists": "passed"})
CHANGED = ["app/src/routes.js", "app/package.json", "app/package-lock.json", "app/tests/api.test.js"]


def _split(monkeypatch, measure):
    put_back: list[list[str]] = []
    monkeypatch.setattr(ci, "commit", lambda root, message: "c0ffee")
    monkeypatch.setattr(ci, "changed_since", lambda root, base: list(CHANGED))
    monkeypatch.setattr(ci, "restore_paths", lambda root, base, paths: put_back.append(list(paths)) or True)
    monkeypatch.setattr(ci, "take", lambda root, label: measure(put_back))
    kept = engineering._its_tests_without_its_product_change(
        "/w", "base", BEFORE, ["acceptance: [AC-1] lists"], "defect_fix_2_0")
    return kept, put_back


def test_the_manifest_and_lock_stay_with_the_tests(monkeypatch):
    kept, put_back = _split(monkeypatch, lambda put_back: ci.Snapshot(
        label="a", unit_ran=True, acceptance_ran=True, unit={"old": "passed"}, acceptance={"[AC-1] lists": "passed"}))
    assert kept is not None
    assert put_back == [["app/src/routes.js"]]


def test_when_the_kept_declarations_break_something_the_tests_stay_alone(monkeypatch):
    def measure(put_back):
        whole = len(put_back) > 1
        return ci.Snapshot(label="a", unit_ran=True, acceptance_ran=True, unit={"old": "passed"},
                           acceptance={"[AC-1] lists": "passed" if whole else "failed"})

    kept, put_back = _split(monkeypatch, measure)
    assert kept is not None
    assert put_back[0] == ["app/src/routes.js"]
    assert set(put_back[1]) == {"app/src/routes.js", "app/package.json", "app/package-lock.json"}


def test_only_dependency_files_count_as_declarations():
    for path in ("a/package.json", "pyproject.toml", "x/go.sum", "Cargo.lock", "b/poetry.lock", "uv.lock"):
        assert engineering._declares_dependencies(path), path
    for path in ("a/src/app.js", "a/public/main.js", "a/config.json", "a/tsconfig.json"):
        assert not engineering._declares_dependencies(path), path
