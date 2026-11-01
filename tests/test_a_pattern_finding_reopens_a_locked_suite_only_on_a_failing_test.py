"""A text pattern's finding sends a locked suite back to QA only if the test it names fails in the last measurement.

Measured over two days: five false findings, each reopening a right suite for 10 to 60 minutes. No model-written spec is
run here: only text is read, and the reports are made up.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from app.acceptance import junit, suite
from app.graph import acceptance_nodes

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
SPEC = """import { test, expect } from '@playwright/test';

test('[AC-1] lists the items', async ({ page }) => {
  await page.getByRole('list').click();
});

test('[AC-2] signs in', async ({ request }) => {
  const r = await request.post('/login', { data: { user: 'nobody' } });
  expect(r.status).toBe(200);
});
"""


def _report(failed: tuple[str, ...] = (), passed: tuple[str, ...] = ("x",)):
    tests = [junit.TestResult(name=name, outcome="failed", message="m") for name in failed]
    tests += [junit.TestResult(name=name, outcome="passed") for name in passed]
    return SimpleNamespace(report=SimpleNamespace(tests=tests), problem="", ran=True)


@pytest.fixture
def locked(tmp_path):
    """A locked suite on a project with no pack, whose real pattern check finds the `r.status` read in AC-2."""
    (tmp_path / ".project-directory").write_text("notes\n")
    (tmp_path / "notes" / "acceptance").mkdir(parents=True)
    (tmp_path / "notes" / "acceptance" / "items.spec.js").write_text(SPEC)
    suite.lock(tmp_path)
    return tmp_path


def _both(root, result):
    found = suite.tests_that_cannot_pass(root, result)
    return found, suite.findings_that_reopen(root, result, found)


def test_a_finding_on_a_test_that_passes_does_not_reopen_and_is_kept_as_a_note(locked):
    found, kept = _both(locked, _report(passed=("items.spec.js › [AC-1] lists the items", "items.spec.js › [AC-2] signs in")))
    assert any("line(s) 9" in f for f in found), found
    assert kept == []
    notes = suite.notes_kept(locked)
    assert notes and "line(s) 9" in notes[0]
    assert not BANNED.search(suite.NOT_ACTED_ON)


def test_a_finding_on_a_test_that_fails_reopens(locked):
    found, kept = _both(locked, _report(failed=("items.spec.js › [AC-2] signs in",), passed=("items.spec.js › [AC-1] lists the items",)))
    assert kept == list(found) and kept
    assert suite.notes_kept(locked) == []


def test_another_test_failing_does_not_make_it_reopen(locked):
    _, kept = _both(locked, _report(failed=("items.spec.js › [AC-1] lists the items",), passed=("items.spec.js › [AC-2] signs in",)))
    assert kept == []


def test_before_a_first_lock_it_goes_to_qa_as_now(tmp_path):
    (tmp_path / ".project-directory").write_text("notes\n")
    (tmp_path / "notes" / "acceptance").mkdir(parents=True)
    (tmp_path / "notes" / "acceptance" / "items.spec.js").write_text(SPEC)
    found, kept = _both(tmp_path, _report(passed=("[AC-2] signs in",)))
    assert kept == list(found) and kept


def test_the_round_uses_the_rule(locked, monkeypatch):
    result = _report(passed=("items.spec.js › [AC-1] lists the items", "items.spec.js › [AC-2] signs in"))
    monkeypatch.setattr(acceptance_nodes, "run_for_sprint", lambda _s: (result, []))
    monkeypatch.setattr(acceptance_nodes.acceptance_requests, "acceptance_block", lambda _r, _d: "suite")
    monkeypatch.setattr(suite, "tests_left_behind_by_their_own_change", lambda *_: [])
    monkeypatch.setattr(suite, "vacuous_green", lambda *_: [])
    state = {"repository": SimpleNamespace(root_path=str(locked))}
    _, broken = acceptance_nodes.acceptance_for_round(state)
    assert not [item for item in broken if "items.spec.js" in item], broken
    assert acceptance_nodes.reopen_the_suite_for(state, broken) is None


def test_a_note_is_not_a_release_gap(locked, monkeypatch):
    from app.graph import delivery

    result = _report(passed=("items.spec.js › [AC-1] lists the items", "items.spec.js › [AC-2] signs in"))
    suite.findings_that_reopen(locked, result, suite.tests_that_cannot_pass(locked, result))
    monkeypatch.setattr(suite, "is_locked", lambda _r: False)
    monkeypatch.setattr(delivery, "_unit_tests_failing", lambda _r: [])
    update = delivery.release(
        {"repository": SimpleNamespace(root_path=str(locked)), "release_attempts": 0, "decisions": []},
        {"configurable": {}},
        SimpleNamespace(judgement_model=None, checkpointer=None, repo_root=str(locked), allow_subdirectories=True),
    )
    assert not [gap for gap in update.get("completion_gaps", []) if "items.spec.js" in gap]
    assert "Noted, not a gap" in str(update) and "items.spec.js" in str(update)


def test_a_product_that_did_not_start_has_measured_nothing_about_any_test(locked):
    result = _report(failed=("items.spec.js › [AC-2] signs in",), passed=())
    result.problem = suite.PRODUCT_DID_NOT_START + ": x"
    _, kept = _both(locked, result)
    assert kept == []


def test_a_suite_with_no_results_at_all_acts_as_before(locked):
    result = SimpleNamespace(report=SimpleNamespace(tests=[]), problem="the runner wrote no report", ran=False)
    found, kept = _both(locked, result)
    assert kept == list(found) and kept


def test_a_measured_finding_is_not_judged(locked, monkeypatch):
    measured = "`[AC-1] lists the items` fails because of an error in the test's own code, not because the product is unbuilt: x"
    monkeypatch.setattr(suite, "tests_that_broke_themselves", lambda *_: [measured])
    result = _report(passed=("items.spec.js › [AC-2] signs in",))
    _, kept = _both(locked, result)
    assert kept == [measured]


def test_a_finding_that_names_no_test_acts_as_before(locked, monkeypatch):
    """A file's top, before any test: the whole file cannot load, and no test is its to answer for."""
    finding = "`notes/acceptance/items.spec.js` line 1 uses `require` in an ES module"
    monkeypatch.setattr(suite, "tests_with_module_system_mismatch", lambda _r: [finding])
    result = _report(passed=("items.spec.js › [AC-1] lists the items", "items.spec.js › [AC-2] signs in"))
    _, kept = _both(locked, result)
    assert kept == [finding]


def test_a_finding_by_a_title_and_a_generated_title_are_matched(locked, monkeypatch):
    spec = locked / "notes" / "acceptance" / "made.spec.js"
    spec.write_text("for (const x of xs) {\n  test(`[AC-3] shows ${x}`, async () => {\n    bad();\n  });\n}\n")
    finding = "`notes/acceptance/made.spec.js` line 3: bad"
    monkeypatch.setattr(suite, "tests_with_module_system_mismatch", lambda _r: [finding])
    failing = _report(failed=("made.spec.js › [AC-3] shows one",))
    assert finding in suite.findings_that_reopen(locked, failing, suite.tests_that_cannot_pass(locked, failing))
    passing = _report(passed=("made.spec.js › [AC-3] shows one",))
    assert finding not in suite.findings_that_reopen(locked, passing, suite.tests_that_cannot_pass(locked, passing))


def test_a_python_test_is_found_by_its_name(tmp_path):
    (tmp_path / "t.py").write_text("import x\n\ndef test_one():\n    bad()\n\ndef test_two():\n    ok()\n")
    assert suite._the_tests_at(tmp_path, "`t.py` line 4: bad") == ["test_one"]
    assert suite._the_tests_at(tmp_path, "`t.py` line 1: bad") == []


def test_it_never_raises(locked, monkeypatch):
    monkeypatch.setattr(suite, "_the_tests_at", lambda *_: 1 / 0)
    found = suite.tests_that_cannot_pass(locked, _report())
    assert suite.findings_that_reopen(locked, _report(), found) == list(found)


def test_a_plain_list_acts_as_before(locked):
    assert suite.findings_that_reopen(locked, _report(), ["`x` line 1"]) == ["`x` line 1"]


def test_a_file_named_that_cannot_be_found_names_no_test(locked):
    """Never read as a title nothing fails under: that would silence a real finding."""
    assert suite._the_tests_at(locked, "`gone/away.spec.js` line 3: bad") == []


def test_a_file_named_from_inside_the_project_is_found(locked):
    assert suite._the_tests_at(locked, "`acceptance/items.spec.js` line 9: bad") == ["[AC-2] signs in"]
