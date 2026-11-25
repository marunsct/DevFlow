"""A broken batch reverts only the fixer whose change broke it, and a fix keeps the best version it reached.

Deep review 2026-11-18, item A3: the batch gather reverted every parallel fixer of a batch for one culprit (8 of 37
recent reverts); and a fixer that fixed its error, then broke the build with its last edit, either had the broken build
kept or the whole stage reverted to its start, losing the version where its own tests passed.
"""
from __future__ import annotations

import subprocess
from types import SimpleNamespace

from app import ci
from app.graph import batch_file_claims, best_checkpoint, engineering

PASSED_BEFORE = {"t_notes": "passed", "t_tags": "passed"}


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), "-c", "user.email=h@example.com", "-c", "user.name=h", *args],
                          check=True, capture_output=True, text=True).stdout.strip()


def _a_workspace(root):
    (root / "app").mkdir()
    (root / "app" / "notes.py").write_text("NOTES = 1\n")
    (root / "app" / "tags.py").write_text("TAGS = 1\n")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    return _git(root, "rev-parse", "HEAD")


def _the_product_s_tests(monkeypatch, root):
    """The project's own tests as the edge: a file holding `broken` fails its test, everything else passes."""
    def take(root_, label, **kwargs):
        unit = {f"t_{name}": "failed" if "broken" in (root / "app" / f"{name}.py").read_text() else "passed"
                for name in ("notes", "tags")}
        return ci.Snapshot(label=label, unit=unit, unit_ran=True)

    monkeypatch.setattr(engineering, "ci_applies", lambda root_: True)
    monkeypatch.setattr(ci, "load", lambda root_, which="latest": ci.Snapshot(label="latest", unit=dict(PASSED_BEFORE),
                                                                                unit_ran=True))
    monkeypatch.setattr(ci, "take", take)
    monkeypatch.setattr(ci, "save", lambda *a, **k: None)
    monkeypatch.setattr("app.analysis.language_service.underlined_in", lambda *a, **k: {})


def test_a_broken_batch_puts_back_only_the_fixer_whose_change_broke_it(tmp_path, monkeypatch):
    base = _a_workspace(tmp_path)
    _the_product_s_tests(monkeypatch, tmp_path)
    (tmp_path / "app" / "notes.py").write_text("NOTES = 2  # broken\n")  # the culprit, written first
    (tmp_path / "app" / "tags.py").write_text("TAGS = 2\n")               # a sound fix, written last

    broke, put_back = engineering.after_a_batch(
        str(tmp_path), base, "defect_fix_2_batch", "two fixes",
        [("defect_fix_2_1", ["app/tags.py"]), ("defect_fix_2_0", ["app/notes.py"])],
    )

    assert broke and put_back == ["defect_fix_2_0"]
    assert (tmp_path / "app" / "tags.py").read_text() == "TAGS = 2\n", "the sound fix is kept"
    assert (tmp_path / "app" / "notes.py").read_text() == "NOTES = 1\n", "the culprit is put back"


def test_the_gather_reverts_only_the_culprit_and_settles_the_rest(tmp_path, monkeypatch):
    from workflow_nodes import run_node

    from app.agents.specialists import SpecialistOutput
    from app.sprint import Defect, RemediationCycle

    base = _a_workspace(tmp_path)
    _the_product_s_tests(monkeypatch, tmp_path)
    # The batch's own measurement is the latest: the kept fix's tests pass in it, which is what closes its defect.
    monkeypatch.setattr(ci, "load", lambda root_, which="latest": ci.Snapshot(
        label="after defect_fix_2_batch", unit=dict(PASSED_BEFORE), unit_ran=True))
    for stage, path, text in (("defect_fix_2_0", "app/notes.py", "NOTES = 2  # broken\n"),
                              ("defect_fix_2_1", "app/tags.py", "TAGS = 2\n")):
        with batch_file_claims.holding("", stage):
            (tmp_path / path).write_text(text)
            batch_file_claims.claim("", stage, "write_artifact", {"relative_path": path})

    def a_defect(description, files, test):
        # Raised from a failing unit test, which is what its unit tests answer for (LF.1443).
        return Defect(description=description, severity="major", reproduction_steps="r", expected_behavior="e",
                      actual_behavior="a", owner="backend", affected_files=files, kind="failing_test",
                      evidence=[{"test": test}])

    state = {
        "repository": SimpleNamespace(root_path=str(tmp_path)), "test_round": 2, "current_sprint_index": 0,
        "remediation": RemediationCycle(sprint_goal="g", defects=[a_defect("Notes are lost", ["app/notes.py"], "t_notes"),
                                                                  a_defect("Tags are lost", ["app/tags.py"], "t_tags")]),
        "fix_batch": [0, 1], "fix_base_commit": base,
        "specialist_outputs": {name: SpecialistOutput(changed_files=[path], tests=["t"]) for name, path in
                               (("defect_fix_2_0", "app/notes.py"), ("defect_fix_2_1", "app/tags.py"))},
    }

    update = run_node("defect_fix_gather", state, str(tmp_path))

    notes, tags = update["remediation"].defects
    assert notes.status == "open" and "reverted" in notes.actual_behavior
    assert tags.status == "fixed"
    assert update["fixes_one_at_a_time"] == ["defect_fix_2_0"]


def test_a_fix_that_ended_broken_keeps_the_version_its_own_tests_passed_at(tmp_path, monkeypatch):
    from app.graph import verify_after_write

    monkeypatch.setenv("VERIFY_AFTER_WRITE", "on")
    base = _a_workspace(tmp_path)
    _the_product_s_tests(monkeypatch, tmp_path)

    def its_own_tests_pass():
        return "broken" not in (tmp_path / "app" / "tags.py").read_text()

    with verify_after_write.watching("run", "defect_fix_2_1", its_own_tests_pass, checkpoints_in=tmp_path):
        for text in ("TAGS = 2\n", "TAGS = 3  # broken\n"):  # its fix, then a last write that broke it
            (tmp_path / "app" / "tags.py").write_text(text)
            verify_after_write.after_a_write("write_artifact", SimpleNamespace(content="Wrote it", status="success"),
                                             "run", "defect_fix_2_1")
    broke = engineering.after_a_fix(str(tmp_path), base, "defect_fix_2_1", "tags are lost")

    instead = best_checkpoint.instead_of(
        tmp_path, "run", "defect_fix_2_1", base, broke, lambda: None,
        lambda against: engineering.after_a_fix(str(tmp_path), against, "defect_fix_2_1", "tags are lost"),
    )

    assert broke and instead == []
    assert (tmp_path / "app" / "tags.py").read_text() == "TAGS = 2\n"
