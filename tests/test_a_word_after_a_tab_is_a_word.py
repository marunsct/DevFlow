"""A test of a whitespace criterion that leaves a word after a tab or line break as it was, while words after spaces
change, goes back: it holds the product to breaking words at spaces only.

Measured on one run: `title_case("hello world\\t\\nfoo") == "Hello World\\t\\nFoo"` was locked; a dispute called it wrong,
the rewrite expected `"Hello World\\t\\nfoo"` - what a product splitting on spaces gives - the suite locked 47 of 47
and the hidden test of a word after a tab failed (7/8, a false acceptance).
"""
from __future__ import annotations

import re

from app.acceptance import suite
from app.graph import acceptance_nodes
from tests.test_whitespace_is_tested_with_more_than_a_space import _a_suite

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
BENT = '''
def test_ac9_irregular_whitespace_preserved():
    import textkit
    result = textkit.title_case("hello world\\t\\nfoo")
    assert result == "Hello World\\t\\nfoo"
'''
RIGHT = BENT.replace('nfoo"', 'nFoo"')
JS = '''
test('[AC-9] keeps whitespace', () => {
  expect(titleCase('a b\\tc')).toBe('A B\\tc');
});
'''


def test_a_word_left_small_after_a_tab_is_found(tmp_path):
    _a_suite(tmp_path, BENT)
    found = suite.words_broken_only_at_spaces(tmp_path)
    assert len(found) == 1 and "`test_ac9_irregular_whitespace_preserved` (AC-9)" in found[0]
    assert not BANNED.search(found[0])


def test_the_right_expectation_is_not_found(tmp_path):
    assert "Foo" in RIGHT
    _a_suite(tmp_path, RIGHT)
    assert suite.words_broken_only_at_spaces(tmp_path) == []


def test_a_javascript_expectation_is_read_too(tmp_path):
    root = tmp_path
    _a_suite(root, "")
    (root / "lib" / "acceptance" / "title.spec.js").write_text(JS)
    assert len(suite.words_broken_only_at_spaces(root)) == 1


def test_it_sends_the_suite_back_with_the_other_partial_findings(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from app.acceptance import junit

    _a_suite(tmp_path, BENT)
    monkeypatch.setattr(suite, "run", lambda root: suite.AcceptanceResult(
        ran=True, exit_code=1, command="run", report=junit.Report(found=True, tests=[
            junit.TestResult(name="test_ac9_irregular_whitespace_preserved", outcome="failed", message="no")])))

    update = acceptance_nodes.acceptance_review(
        {"repository": SimpleNamespace(root_path=str(tmp_path)), "acceptance_round": 1,
         "document": SimpleNamespace(text="title_case leaves the whitespace exactly as it was.")},
        {"configurable": {"thread_id": "t"}},
        acceptance_nodes.Context(model=None, judgement_model=None, checkpointer=None, repo_root=None))

    assert update["stage"] == "acceptance_author"
    assert any("`test_ac9_irregular_whitespace_preserved` (AC-9)" in item for item in update["acceptance_feedback"])
