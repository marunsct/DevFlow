"""A sprint planned again starts from the best product it has had, not the worst.

Measured on a small-model run: a sprint's first attempt ended at 14 of 18 acceptance criteria passing, remediation was
exhausted, the sprint was planned again, and the new drafting rewrote working files; the next rounds measured 0 of 18
with no test reaching the product, and every attempt after it started from that.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.acceptance import suite
from app.graph import best_attempt


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("KEEP_THE_BEST_ATTEMPT", "on")


def _repo(tmp_path: Path) -> Path:
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                       check=True, capture_output=True)

    git("init", "-q")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.ts").write_text("export const app = 'working';\n")
    (tmp_path / "acceptance").mkdir()
    (tmp_path / "acceptance" / "api.spec.ts").write_text("locked suite v1\n")
    git("add", ".")
    git("commit", "-q", "-m", "first")
    return tmp_path


def _measured(monkeypatch, root, passed, ran=True):
    monkeypatch.setattr(suite, "last_result", lambda repo: {"ran": ran, "passed": passed, "failed": 18 - passed})
    monkeypatch.setattr(suite, "suite_files", lambda repo: [root / "acceptance" / "api.spec.ts"])


def test_a_worse_product_is_put_back_to_the_best_one(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    _measured(monkeypatch, root, 14)
    best_attempt.note(root)

    (root / "src" / "app.ts").write_text("export const app = 'rewritten and broken';\n")
    (root / "src" / "extra.ts").write_text("a file the best product did not have\n")
    (root / "acceptance" / "api.spec.ts").write_text("locked suite v2 (repaired since)\n")
    _measured(monkeypatch, root, 0)

    said = best_attempt.restore_if_worse(root)

    assert "passes 0 acceptance tests now and passed 14" in said
    assert (root / "src" / "app.ts").read_text() == "export const app = 'working';\n"
    assert not (root / "src" / "extra.ts").exists()
    assert (root / "acceptance" / "api.spec.ts").read_text() == "locked suite v2 (repaired since)\n"  # the lock stands


def test_a_product_that_is_not_clearly_worse_is_left_as_it_is(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    _measured(monkeypatch, root, 14)
    best_attempt.note(root)
    (root / "src" / "app.ts").write_text("export const app = 'a little different';\n")
    _measured(monkeypatch, root, 13)  # one test fewer is noise

    assert best_attempt.restore_if_worse(root) == ""
    assert "a little different" in (root / "src" / "app.ts").read_text()


def test_the_best_is_only_ever_raised(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    _measured(monkeypatch, root, 10)
    best_attempt.note(root)
    first = best_attempt._read(root)
    (root / "src" / "app.ts").write_text("export const app = 'worse';\n")
    _measured(monkeypatch, root, 4)
    best_attempt.note(root)
    assert best_attempt._read(root) == first

    (root / "src" / "app.ts").write_text("export const app = 'better';\n")
    _measured(monkeypatch, root, 12)
    best_attempt.note(root)
    assert best_attempt._read(root)["passed"] == 12 and best_attempt._read(root)["commit"] != first["commit"]


def test_a_suite_that_did_not_run_puts_nothing_back_and_a_switch_off_does_nothing(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    _measured(monkeypatch, root, 14)
    best_attempt.note(root)
    (root / "src" / "app.ts").write_text("export const app = 'changed';\n")

    _measured(monkeypatch, root, 0, ran=False)
    assert best_attempt.restore_if_worse(root) == ""

    _measured(monkeypatch, root, 0)
    monkeypatch.setenv("KEEP_THE_BEST_ATTEMPT", "off")
    assert best_attempt.restore_if_worse(root) == ""
    assert "changed" in (root / "src" / "app.ts").read_text()


def test_the_planner_puts_the_best_product_back_before_a_sprint_is_planned_again():
    """The re-plan path calls it: the wiring, read from the source, since the graph needs a whole run to build."""
    source = (Path(__file__).resolve().parent.parent / "src" / "app" / "graph" / "workflow.py").read_text()
    assert "best_attempt.restore_if_worse(state[\"repository\"].root_path, margin=1)" in source
    assert "best_attempt.note(state[\"repository\"].root_path)" in source


def test_a_bad_redraft_is_undone_at_its_first_measurement_and_a_good_one_is_left(tmp_path, monkeypatch):
    """A re-plan's redraft took one product from 14 of 18 criteria to 0; undone at once, not after a round of fixers."""
    root = _repo(tmp_path)
    _measured(monkeypatch, root, 14)
    best_attempt.note(root)
    (root / "src" / "app.ts").write_text("export const app = 'redrafted and broken';\n")
    _measured(monkeypatch, root, 0)

    # not a re-plan, or not its first measurement: nothing is done
    assert best_attempt.after_a_redraft(root, test_round=0, replans=0) == ""
    assert best_attempt.after_a_redraft(root, test_round=1, replans=1) == ""
    assert "redrafted" in (root / "src" / "app.ts").read_text()

    said = best_attempt.after_a_redraft(root, test_round=0, replans=1)

    assert "passes 0 acceptance tests now and passed 14" in said
    assert (root / "src" / "app.ts").read_text() == "export const app = 'working';\n"


def test_a_redraft_that_is_as_good_or_better_is_not_undone(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    _measured(monkeypatch, root, 12)
    best_attempt.note(root)
    (root / "src" / "app.ts").write_text("export const app = 'redrafted';\n")
    _measured(monkeypatch, root, 14)

    assert best_attempt.after_a_redraft(root, test_round=0, replans=1) == ""
    assert "redrafted" in (root / "src" / "app.ts").read_text()


def test_the_round_plans_the_sprint_again_at_once_when_the_best_was_put_back():
    source = (Path(__file__).resolve().parent.parent / "src" / "app" / "graph" / "workflow.py").read_text()
    assert "best_attempt.after_a_redraft(" in source
    assert "the redraft left the product worse than its best; the best was put back" in source


def test_when_a_sprint_is_about_to_be_planned_again_one_test_fewer_than_the_best_is_put_back(tmp_path, monkeypatch):
    """A run reached 18 of 18 criteria, was planned again, and released at 17 of 18 with AC-14 deferred."""
    root = _repo(tmp_path)
    _measured(monkeypatch, root, 18)
    best_attempt.note(root)
    (root / "src" / "app.ts").write_text("export const app = 'one test worse';\n")
    _measured(monkeypatch, root, 17)

    assert best_attempt.restore_if_worse(root) == ""  # the default margin treats one test as noise
    assert "one test worse" in (root / "src" / "app.ts").read_text()

    said = best_attempt.restore_if_worse(root, margin=1)

    assert "passes 17 acceptance tests now and passed 18" in said
    assert (root / "src" / "app.ts").read_text() == "export const app = 'working';\n"


def test_the_replan_path_asks_for_a_margin_of_one():
    source = (Path(__file__).resolve().parent.parent / "src" / "app" / "graph" / "workflow.py").read_text()
    assert "best_attempt.restore_if_worse(state[\"repository\"].root_path, margin=1)" in source
