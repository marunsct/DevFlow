"""A fix that stops the product is handed back to its own model once before it is reverted (LF.1271, deep review 2.3).

Measured on a medium run: 34 fix stages, 5 reverted, 2 of them correct fixes. One fixed its route and the start then
broke on an import the fix had added; another fixed its route and the tests behind it then reached a list query that
raised ("18 passing to 0"). Each revert threw the correct part away with the fault it had exposed.
"""
from __future__ import annotations

import subprocess
from typing import Any

import pytest

from app import ci
from app.agents.specialists import SpecialistOutput
from app.graph import engineering, judged_fixes

import the_fix_stage
from the_fix_stage import a_defect, a_state

PRODUCT = "app/count.js"
#: What the product starts from, and what a correct fix with a bad import makes of it.
BEFORE = "const count = 1;\n"
FIXED_BUT_STOPPED = "const helper = require('./missing');\nconst count = 2;\n"
REPAIRED = "const count = 2;\n"
NOT_REPAIRED = "const helper = require('./still-missing');\nconst count = 2;\n"
STOPPED = "The product did not start for the acceptance suite: Error: Cannot find module './missing'"


def _git(root, *args):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=root, check=True,
                   capture_output=True)


def _workspace(tmp_path):
    (tmp_path / PRODUCT).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / PRODUCT).write_text(BEFORE)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "before the fix")
    # The fix stage's own base commit, by the name the fix-stage driver gives it.
    _git(tmp_path, "tag", "base")
    return tmp_path


def _measured(root, label):
    """The product measured as its code reads: an import of nothing stops it; `count = 2` makes AC-1 pass."""
    text = (root / PRODUCT).read_text()
    if "missing" in text:
        return ci.Snapshot(label=label, acceptance={}, acceptance_ran=True, problem=STOPPED)
    return ci.Snapshot(label=label, acceptance_ran=True, acceptance={
        "count.spec.js › [AC-1] counts": "passed" if "count = 2" in text else "failed",
        "count.spec.js › [AC-2] lists": "passed",
    })


def _measuring(monkeypatch, root):
    saved: dict[str, Any] = {"latest": _measured(root, "before")}
    monkeypatch.setattr(engineering, "ci_applies", lambda r: True)
    monkeypatch.setattr(ci, "take", lambda r, label, **k: _measured(root, label))
    monkeypatch.setattr(ci, "save", lambda r, snapshot, accepted=False: saved.update(latest=snapshot))
    monkeypatch.setattr(ci, "load", lambda r, which="latest": saved.get("latest"))
    return saved


def _the_fixer_writes(root, text):
    def during(stage):
        (root / PRODUCT).write_text(text)
    return during


def _the_repair_writes(root, text):
    def rewrite(defect, **kwargs):
        (root / PRODUCT).write_text(text)
        return SpecialistOutput(changed_files=[PRODUCT], tests=["the harness's measurement"])
    return rewrite


def _fix(root, monkeypatch, *, repair_writes, **more):
    _measuring(monkeypatch, root)
    real = engineering.after_a_fix
    return the_fix_stage.run(
        root, a_state(root, a_defect("[AC-1] The count is wrong", affected_files=[PRODUCT])),
        during=_the_fixer_writes(root, FIXED_BUT_STOPPED), rewrite=_the_repair_writes(root, repair_writes),
        measure=lambda *a, **k: real(*a, **k), **more)


def _the_attempt(update):
    return update["remediation"].defects[0].attempts[-1]["outcome"]


def test_a_fix_that_stopped_the_start_is_repaired_forward_and_kept(tmp_path, monkeypatch):
    root = _workspace(tmp_path)

    update, seen = _fix(root, monkeypatch, repair_writes=REPAIRED)

    assert (root / PRODUCT).read_text() == REPAIRED, "the fix's correct part stays, its bad import is gone"
    assert update["remediation"].defects[0].status == "fixed"
    assert "repaired forward" in _the_attempt(update)
    asked = seen.rewrites[-1]["defect"]
    assert "Cannot find module './missing'" in asked.actual_behavior, "the repair is handed the start error"
    assert "require('./missing')" in asked.actual_behavior, "and the fix's own diff"
    assert asked.affected_files == [PRODUCT]


def test_a_fix_still_stopped_after_its_one_repair_is_reverted(tmp_path, monkeypatch):
    root = _workspace(tmp_path)

    update, seen = _fix(root, monkeypatch, repair_writes=NOT_REPAIRED)

    assert (root / PRODUCT).read_text() == BEFORE, "reverted to where the fix started"
    assert _the_attempt(update).startswith("reverted after a forward repair failed")
    assert len(seen.rewrites) == 1, "one repair a fix stage"
    assert update["remediation"].defects[0].fix_attempts == 1


def test_a_run_that_does_not_approve_its_own_writes_reverts_as_before(tmp_path, monkeypatch):
    root = _workspace(tmp_path)

    update, seen = _fix(root, monkeypatch, repair_writes=REPAIRED, approves=False)

    assert (root / PRODUCT).read_text() == BEFORE
    assert seen.rewrites == []
    assert _the_attempt(update).startswith("reverted")


# --- what a repair is handed, read from the measurements -----------------------------------------------------------


def _snap(acceptance=None, problem="", unit=None):
    return ci.Snapshot(label="m", acceptance=acceptance or {}, acceptance_ran=True, unit=unit or {}, unit_ran=True,
                       problem=problem)


def test_a_product_that_did_not_start_before_the_fix_is_not_the_fix_s_to_repair(tmp_path):
    before = _snap(problem=STOPPED)
    after = _snap(problem=STOPPED)

    assert judged_fixes.what_a_repair_is_given(tmp_path, before, after, ["the product did not start before"]) == ""


def test_unit_tests_that_no_longer_build_are_handed_to_a_repair(tmp_path):
    before = _snap(unit={"t › adds": "passed"})
    after = _snap(unit={ci.UNIT_TESTS_DID_NOT_RUN: "failed"})

    handed = judged_fixes.what_a_repair_is_given(tmp_path, before, after, ["unit: t › adds"])

    assert "unit tests no longer build" in handed


def _saved_result(root, tests):
    """The suite's saved result of the product as it is on disk now."""
    import json

    from app.acceptance.unstable import fingerprint

    path = root / ".harness" / "acceptance-result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"criteria": {"AC-1": {"tests": tests}}, "fingerprint": fingerprint(root)}))


def _failed(name, message):
    return {"name": name, "outcome": "failed", "message": message}


LIST_RAISED = "Error: expect(received).toBe(expected)\nExpected: 200\nReceived: 500\n  -> GET http://localhost:3000/api/items"


def test_broken_tests_that_all_stop_at_one_new_step_name_it_for_the_repair():
    tests = [_failed("[AC-1] lists items", LIST_RAISED), _failed("[AC-1] lists two", LIST_RAISED)]

    step = judged_fixes.the_new_step(tests, ["acceptance: items.spec.js › [AC-1] lists items",
                                            "acceptance: items.spec.js › [AC-1] lists two"])

    assert "GET /api/items" in step and "answered 500" in step


def test_broken_tests_that_stop_at_different_steps_name_none():
    tests = [_failed("[AC-1] lists items", LIST_RAISED),
             _failed("[AC-1] signs in", "Error: Expected: 201\nReceived: 404\n  -> POST http://localhost:3000/api/login")]

    assert judged_fixes.the_new_step(tests, ["acceptance: a › [AC-1] lists items", "acceptance: a › [AC-1] signs in"]) == ""


def test_a_regression_at_one_new_step_is_repaired_forward_and_kept_only_when_it_holds(tmp_path, monkeypatch):
    """The "18 passing to 0" case: the fix's route reached a list query that raised; one repair of that query holds."""
    root = _workspace(tmp_path)
    monkeypatch.setattr(engineering, "ci_applies", lambda r: True)

    def measured(r, label, **k):
        text = (root / PRODUCT).read_text()
        raised = "query()" in text
        return ci.Snapshot(label=label, acceptance_ran=True, acceptance={
            "items.spec.js › [AC-1] lists items": "failed" if raised else "passed",
            "items.spec.js › [AC-1] lists two": "failed" if raised else "passed",
            "items.spec.js › [AC-2] counts": "passed" if "count = 2" in text else "failed",
        })

    saved = {"latest": measured(root, "before")}
    monkeypatch.setattr(ci, "take", measured)
    monkeypatch.setattr(ci, "save", lambda r, snapshot, accepted=False: saved.update(latest=snapshot))
    monkeypatch.setattr(ci, "load", lambda r, which="latest": saved["latest"])
    (root / PRODUCT).write_text("const count = 2;\nquery();\n")
    _saved_result(root, [_failed("[AC-1] lists items", LIST_RAISED), _failed("[AC-1] lists two", LIST_RAISED)])
    handed: list[str] = []

    def repair(what):
        handed.append(what)
        (root / PRODUCT).write_text(REPAIRED)
        return True

    broke = engineering.after_a_fix(str(root), "base", "defect_fix_1_0", "count", repair_forward=repair)

    assert broke == []
    assert (root / PRODUCT).read_text() == REPAIRED
    assert "GET /api/items" in handed[0]


# --- the record `loop.sh effects` reads -----------------------------------------------------------------------------


@pytest.mark.parametrize("broke, label", [
    ([], "LF.1271 a fix that broke what worked was repaired forward and kept"),
    (["acceptance: a › b"], "LF.1271 a fix reverted after its forward repair failed"),
])
def test_the_effects_report_counts_a_forward_repair(broke, label):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "effects", Path(__file__).resolve().parents[1] / "scripts" / "loop" / "effects.py")
    effects = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(effects)
    repair = judged_fixes.ForwardRepair("r", "base", a_defect(), lambda asked, files: None)
    repair.what, repair.changed = "the start failed", ["app/count.js"]

    lines = effects.effects([{"kind": "defect", "event": judged_fixes.REPAIRED_FORWARD, "detail": repair.said(broke)}])

    assert any(line.strip().startswith("1") and label in line for line in lines)


def test_the_repair_s_words_avoid_the_words_the_prompts_never_use(tmp_path):
    import re

    text = " ".join([judged_fixes.REPAIR_HEADING, judged_fixes.REPAIR_EXPECTED, judged_fixes.REPAIR_STEPS,
                     judged_fixes.MOVED_EVIDENCE,
                     judged_fixes.what_a_repair_is_given(tmp_path, _snap(), _snap(problem=STOPPED), ["x"]),
                     judged_fixes.the_new_step([_failed("[AC-1] a", LIST_RAISED)], ["acceptance: s › [AC-1] a"])])

    assert not re.search(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", text, re.I)


def test_a_repair_may_rewrite_the_caller_the_start_s_error_names_not_only_what_the_fix_changed(tmp_path):
    """Measured on a Rust run: a fix changed `src/lib.rs`, its caller in `src/main.rs` stopped compiling, and the repair,
    let rewrite only `src/lib.rs`, sent it back unchanged twice; a fix with 18 tests passing was reverted."""
    project = tmp_path / "notes-api" / "src"
    project.mkdir(parents=True)
    (project / "lib.rs").write_text("pub fn app() {}\n")
    (project / "main.rs").write_text("fn main() { notes_api::app(); }\n")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "before the fix")
    (project / "lib.rs").write_text("pub fn app(state: u8) {}\n")
    said = ("The product did not start: error[E0061]: this function takes 1 argument but 0 arguments were supplied\n"
            "  --> src/main.rs:1:13\n  --> /home/u/.cargo/registry/src/index/axum-0.8.9/src/routing/mod.rs:408:12")

    _, files = judged_fixes.the_repair_asked(tmp_path, "HEAD", a_defect("The product does not start"), said)

    assert files == ["notes-api/src/main.rs", "notes-api/src/lib.rs"]
