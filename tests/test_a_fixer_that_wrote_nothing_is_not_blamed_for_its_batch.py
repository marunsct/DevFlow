"""A broken batch of fixes puts back only a fixer that changed something (LF.1543).

Measured on a web front-end run in parallel mode: of a batch of two fixers, one (the suite's shared step) wrote
nothing - its one edit failed because the other fixer had changed the stylesheet since it read it, and its rewrite
found no file it might write - while the other (the unstyled page) rewrote the page component and the stylesheet. The
batch broke one unit test. Because one fixer had no recorded writes, the measurement gave up telling the fixers apart:
both were recorded "its batch broke 1 test(s)", both were sent to be fixed alone, and the fixer that changed nothing
was told its change broke a test. The paths, the stage names and the broken test below are the ones in that run.
"""
from __future__ import annotations

import subprocess
from types import SimpleNamespace

from app import ci
from app.graph import batch_attribution, batch_file_claims, engineering

APP = "simple-to-do-list-app/src/App.tsx"
STYLES = "simple-to-do-list-app/src/styles.css"
SPEC = "simple-to-do-list-app/acceptance/todo.spec.js"
TOGGLE = "tests/App.test.tsx › tests/App.test.tsx › App Component > AC-2 & AC-9: Toggle Completion"
STYLED = "tests/App.test.tsx › tests/App.test.tsx › App Component > AC-1: Add"
PASSED_BEFORE = {TOGGLE: "passed", STYLED: "passed"}


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), "-c", "user.email=h@example.com", "-c", "user.name=h", *args],
                          check=True, capture_output=True, text=True).stdout.strip()


def _a_workspace(root):
    for path, text in ((APP, "export function App() { return <input onChange={toggle} /> }\n"),
                       (STYLES, "body { margin: 0; }\n"), (SPEC, "test('adds', () => {})\n")):
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text)
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    return _git(root, "rev-parse", "HEAD")


def _the_product_s_tests(monkeypatch, root):
    """The unit run as the edge: the toggle test fails once the component no longer wires its change handler."""
    def take(root_, label, **kwargs):
        toggles = "onChange={toggle}" in (root / APP).read_text()
        return ci.Snapshot(label=label, unit={TOGGLE: "passed" if toggles else "failed", STYLED: "passed"},
                           unit_ran=True)

    monkeypatch.setattr(engineering, "ci_applies", lambda root_: True)
    monkeypatch.setattr(ci, "load", lambda root_, which="latest": ci.Snapshot(label="latest", unit=dict(PASSED_BEFORE),
                                                                                unit_ran=True))
    monkeypatch.setattr(ci, "take", take)
    monkeypatch.setattr(ci, "save", lambda *a, **k: None)
    monkeypatch.setattr("app.analysis.language_service.underlined_in", lambda *a, **k: {})


def _the_page_rewritten(root):
    (root / APP).write_text("export function App() { return <input className='done' /> }\n")
    (root / STYLES).write_text("body { margin: 0; color: #222; }\n")


def test_a_fixer_that_wrote_nothing_is_not_put_back_with_the_one_that_broke_the_batch(tmp_path, monkeypatch):
    base = _a_workspace(tmp_path)
    _the_product_s_tests(monkeypatch, tmp_path)
    _the_page_rewritten(tmp_path)

    broke, put_back = engineering.after_a_batch(
        str(tmp_path), base, "defect_fix_2_batch", "suite's shared step; the page is not styled",
        [("defect_fix_2_5", [APP, STYLES]), ("defect_fix_2_3", [])],
    )

    assert broke == [f"unit: {TOGGLE}"]
    assert put_back == ["defect_fix_2_5"]
    assert "onChange={toggle}" in (tmp_path / APP).read_text(), "the change that broke the test is put back"


def test_a_change_no_fixer_s_writes_name_is_measured_and_kept_when_sound(tmp_path, monkeypatch):
    """The silent fixer may have changed a file through a command: the writer is still found, by measuring the rest."""
    base = _a_workspace(tmp_path)
    _the_product_s_tests(monkeypatch, tmp_path)
    _the_page_rewritten(tmp_path)
    (tmp_path / SPEC).write_text("test('adds', () => {})\ntest('waits for the list', () => {})\n")

    broke, put_back = engineering.after_a_batch(
        str(tmp_path), base, "defect_fix_2_batch", "suite's shared step; the page is not styled",
        [("defect_fix_2_5", [APP, STYLES]), ("defect_fix_2_3", [])],
    )

    assert broke and put_back == ["defect_fix_2_5"]
    assert "waits for the list" in (tmp_path / SPEC).read_text(), "the change no write names is kept"
    assert "onChange={toggle}" in (tmp_path / APP).read_text()


def test_the_gather_leaves_the_fixer_that_wrote_nothing_unblamed(tmp_path, monkeypatch):
    from workflow_nodes import run_node

    from app.agents.specialists import SpecialistOutput
    from app.sprint import Defect, RemediationCycle

    base = _a_workspace(tmp_path)
    _the_product_s_tests(monkeypatch, tmp_path)
    with batch_file_claims.holding("", "defect_fix_2_5"), batch_file_claims.holding("", "defect_fix_2_3"):
        _the_page_rewritten(tmp_path)
        for path in (APP, STYLES):
            batch_file_claims.claim("", "defect_fix_2_5", "edit_artifact", {"relative_path": path})

    def a_defect(description, files):
        return Defect(description=description, severity="major", reproduction_steps="r", expected_behavior="e",
                      actual_behavior="a", owner="ui_ux", affected_files=files)

    state = {
        "repository": SimpleNamespace(root_path=str(tmp_path)), "test_round": 2, "current_sprint_index": 0,
        "remediation": RemediationCycle(sprint_goal="g", defects=[
            *(a_defect(f"earlier {n}", []) for n in range(3)),
            a_defect("19 acceptance tests across 13 criteria stop at the suite's shared step `todo.spec.js:12`", []),
            a_defect("earlier 4", []),
            a_defect("The interface is not styled: the only stylesheet is the one the scaffold wrote", [STYLES]),
        ]),
        "fix_batch": [3, 5], "fix_base_commit": base,
        "specialist_outputs": {"defect_fix_2_3": SpecialistOutput(changed_files=[], tests=[]),
                               "defect_fix_2_5": SpecialistOutput(changed_files=[APP, STYLES], tests=["t"])},
    }

    update = run_node("defect_fix_gather", state, str(tmp_path))

    shared_step, styled = update["remediation"].defects[3], update["remediation"].defects[5]
    assert "reverted" in styled.actual_behavior
    assert "reverted" not in shared_step.actual_behavior
    assert update["fixes_one_at_a_time"] == ["defect_fix_2_5"]


def test_the_effects_report_counts_batch_reverts_by_cause():
    records = [
        {"kind": batch_attribution.RECORD_KIND, "how": batch_attribution.ONLY_WRITER, "batch": 2,
         "put_back": ["defect_fix_2_5"], "cleared": ["defect_fix_2_3"]},
        {"kind": batch_attribution.RECORD_KIND, "how": batch_attribution.NO_ONE_CULPRIT, "batch": 3,
         "put_back": ["defect_fix_1_0", "defect_fix_1_1", "defect_fix_1_2"], "cleared": []},
        {"kind": "defect", "event": "reverted"},
    ]

    (line,) = batch_attribution.effects_lines(records)

    assert line.split()[0] == "2" and "batch reverts by cause" in line
    assert "4 of 5 fixers put back" in line and "1 that wrote nothing kept out of blame" in line


def test_the_effects_report_says_when_no_batch_broke():
    assert batch_attribution.effects_lines([{"kind": "defect", "event": "reverted"}]) == [
        "     -  LF.1543 batch reverts by cause: not reached"]
