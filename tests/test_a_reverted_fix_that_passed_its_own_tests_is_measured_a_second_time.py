"""A fix reverted for breaking tests, whose own defect's tests passed, is kept and measured again at the defect's next attempt.

Measured per sprint attempt: 4 to 6 fixes were reverted and the defect was dispatched to a fixer again, which wrote its
change from nothing; a revert threw away a fix that did what the defect asked. Behind `KEPT_FIX_CANDIDATES` (off until
measured): the reverted fix is kept as a candidate (files and patches) when its own tests pass, replayed smallest diff
first and composed across attempts where the files are independent, and measured as any fix is.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from app import ci
from app.graph import engineering, kept_fix_candidates, workflow

DEFECT = SimpleNamespace(description="[AC-1] Creating a note fails")


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("KEPT_FIX_CANDIDATES", "on")


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "a.py").write_text("one = 1\ntwo = 2\nthree = 3\n")
    (tmp_path / "b.py").write_text("b = 1\n")
    (tmp_path / "c.py").write_text("c = 1\n")
    return tmp_path


def _fix(root, **files):
    """A fix as a fixer leaves it: edits in the workspace, not committed."""
    for name, text in files.items():
        (root / f"{name}.py").write_text(text)


def _revert_after_keeping(root, base, stage, *, passes=True, broke=("unit: other test",)):
    kept = kept_fix_candidates.keep(root, base, DEFECT, stage, lambda: passes, list(broke))
    assert ci.revert_to(root, base)
    return kept


def test_a_reverted_fix_whose_own_tests_pass_is_kept_and_replayed_at_the_next_attempt(workspace):
    base = ci.commit(workspace, "base")
    _fix(workspace, a="one = 1\ntwo = 22\nthree = 3\n")

    assert _revert_after_keeping(workspace, base, "defect_fix_1_0") is True
    assert (workspace / "a.py").read_text() == "one = 1\ntwo = 2\nthree = 3\n", "the fix is still reverted"

    ci.commit(workspace, "the next attempt starts")
    answer = kept_fix_candidates.replayed(workspace, DEFECT, "defect_fix_2_0")

    assert answer.changed_files == ["a.py"]
    assert (workspace / "a.py").read_text() == "one = 1\ntwo = 22\nthree = 3\n"
    assert "defect_fix_1_0" in answer.decisions[0]


def test_a_fix_whose_own_tests_do_not_pass_or_cannot_be_checked_is_not_kept(workspace):
    base = ci.commit(workspace, "base")
    for outcome in (False, None):
        _fix(workspace, a="one = 11\ntwo = 2\nthree = 3\n")
        assert _revert_after_keeping(workspace, base, "defect_fix_1_0", passes=outcome) is False

    assert kept_fix_candidates.replayed(workspace, DEFECT, "defect_fix_2_0") is None


def test_off_nothing_is_kept_or_replayed(workspace, monkeypatch):
    monkeypatch.setenv("KEPT_FIX_CANDIDATES", "off")
    base = ci.commit(workspace, "base")
    _fix(workspace, a="one = 11\ntwo = 2\nthree = 3\n")

    assert _revert_after_keeping(workspace, base, "defect_fix_1_0") is False
    assert kept_fix_candidates.replayed(workspace, DEFECT, "defect_fix_2_0") is None


def test_the_smallest_diff_is_applied_first_and_a_candidate_on_the_same_file_waits(workspace):
    base = ci.commit(workspace, "base")
    _fix(workspace, a="one = 10\ntwo = 20\nthree = 30\n")
    _revert_after_keeping(workspace, base, "defect_fix_1_0")
    _fix(workspace, a="one = 1\ntwo = 2\nthree = 33\n")
    _revert_after_keeping(workspace, base, "defect_fix_2_0")

    first = kept_fix_candidates.replayed(workspace, DEFECT, "defect_fix_3_0")

    assert (workspace / "a.py").read_text() == "one = 1\ntwo = 2\nthree = 33\n", "one line against three"
    assert first.decisions[0].count("defect_fix_") == 1 and "defect_fix_2_0" in first.decisions[0]
    assert len(kept_fix_candidates._read(workspace)[kept_fix_candidates.defect_key(DEFECT)]["candidates"]) == 1


def test_candidates_on_different_files_from_different_attempts_are_composed(workspace):
    base = ci.commit(workspace, "base")
    _fix(workspace, a="one = 1\ntwo = 22\nthree = 3\n")
    _revert_after_keeping(workspace, base, "defect_fix_1_0")
    _fix(workspace, b="b = 100\nextra = 1\n")
    _revert_after_keeping(workspace, base, "defect_fix_2_0")

    answer = kept_fix_candidates.replayed(workspace, DEFECT, "defect_fix_3_0")

    assert sorted(answer.changed_files) == ["a.py", "b.py"]
    assert "two = 22" in (workspace / "a.py").read_text() and "b = 100" in (workspace / "b.py").read_text()
    assert (workspace / "c.py").read_text() == "c = 1\n"


def test_a_candidate_is_replayed_once_and_a_replay_reverted_again_is_not_kept_again(workspace):
    base = ci.commit(workspace, "base")
    _fix(workspace, a="one = 1\ntwo = 22\nthree = 3\n")
    _revert_after_keeping(workspace, base, "defect_fix_1_0")

    base = ci.commit(workspace, "the next attempt starts")
    assert kept_fix_candidates.replayed(workspace, DEFECT, "defect_fix_2_0") is not None
    # The replay is measured, breaks a test again and is reverted: nothing is kept from it.
    assert _revert_after_keeping(workspace, base, "defect_fix_2_0") is False

    assert kept_fix_candidates.replayed(workspace, DEFECT, "defect_fix_3_0") is None


def test_a_candidate_that_no_longer_applies_is_dropped(workspace):
    base = ci.commit(workspace, "base")
    _fix(workspace, a="one = 1\ntwo = 22\nthree = 3\n")
    _revert_after_keeping(workspace, base, "defect_fix_1_0")
    _fix(workspace, a="something = 'else entirely'\n")
    ci.commit(workspace, "another fix landed")

    assert kept_fix_candidates.replayed(workspace, DEFECT, "defect_fix_2_0") is None
    assert (workspace / "a.py").read_text() == "something = 'else entirely'\n"
    assert kept_fix_candidates._read(workspace)[kept_fix_candidates.defect_key(DEFECT)]["candidates"] == []


def test_a_new_file_is_kept_as_part_of_a_candidate(workspace):
    base = ci.commit(workspace, "base")
    (workspace / "new_module.py").write_text("value = 1\n")
    _fix(workspace, a="one = 1\ntwo = 22\nthree = 3\n")
    _revert_after_keeping(workspace, base, "defect_fix_1_0")
    assert not (workspace / "new_module.py").exists()

    answer = kept_fix_candidates.replayed(workspace, DEFECT, "defect_fix_2_0")

    assert sorted(answer.changed_files) == ["a.py", "new_module.py"]
    assert (workspace / "new_module.py").read_text() == "value = 1\n"


def test_only_a_few_candidates_are_kept_for_a_defect_and_the_largest_go_first(workspace):
    base = ci.commit(workspace, "base")
    for number in range(kept_fix_candidates.MOST_KEPT + 2):
        _fix(workspace, a="".join(f"line{n} = {number}\n" for n in range(number + 1)))
        _revert_after_keeping(workspace, base, f"defect_fix_{number}_0")

    kept = kept_fix_candidates._read(workspace)[kept_fix_candidates.defect_key(DEFECT)]["candidates"]

    assert len(kept) == kept_fix_candidates.MOST_KEPT
    assert [c["size"] for c in kept] == sorted(c["size"] for c in kept)


def test_the_measurement_looks_at_the_fix_before_it_is_reverted(workspace, monkeypatch):
    """`after_a_fix` calls `on_revert` with what the fix broke while the fix is still in the workspace."""
    base = ci.commit(workspace, "base")
    before = ci.Snapshot(label="latest", unit={"t": "passed"}, unit_ran=True)
    after = ci.Snapshot(label="after", unit={"t": "failed"}, unit_ran=True)
    monkeypatch.setattr(engineering, "ci_applies", lambda root: True)
    monkeypatch.setattr(ci, "load", lambda root, which: before)
    monkeypatch.setattr(ci, "take", lambda root, label: after)
    _fix(workspace, a="one = 1\ntwo = 22\nthree = 3\n")
    seen = []

    broke = engineering.after_a_fix(
        str(workspace), base, "defect_fix_1_0", "the defect",
        on_revert=lambda lost: seen.append((lost, (workspace / "a.py").read_text())),
    )

    assert broke == ["unit: t"]
    assert seen == [(["unit: t"], "one = 1\ntwo = 22\nthree = 3\n")]
    assert (workspace / "a.py").read_text() == "one = 1\ntwo = 2\nthree = 3\n"


def test_a_failure_of_the_look_leaves_the_revert_as_it_was(workspace, monkeypatch):
    base = ci.commit(workspace, "base")
    monkeypatch.setattr(engineering, "ci_applies", lambda root: True)
    monkeypatch.setattr(ci, "load", lambda root, which: ci.Snapshot(label="l", unit={"t": "passed"}, unit_ran=True))
    monkeypatch.setattr(ci, "take", lambda root, label: ci.Snapshot(label="a", unit={"t": "failed"}, unit_ran=True))
    _fix(workspace, a="one = 1\ntwo = 22\nthree = 3\n")

    def fails(lost):
        raise RuntimeError("could not look")

    assert engineering.after_a_fix(str(workspace), base, "defect_fix_1_0", "d", on_revert=fails) == ["unit: t"]
    assert (workspace / "a.py").read_text() == "one = 1\ntwo = 2\nthree = 3\n"


def test_the_fix_step_replays_before_a_fixer_and_keeps_what_it_reverts():
    source = inspect.getsource(workflow)
    fix_one = source[source.index("    def _fix_one("):source.index("    def defect_remediation_node(")]

    assert fix_one.index("kept_fix_candidates.replayed(") < fix_one.index("_fixed_by_rewriting(") < fix_one.index("create_specialist_agent(")
    assert "on_revert=lambda lost: kept_fix_candidates.keep(" in fix_one
