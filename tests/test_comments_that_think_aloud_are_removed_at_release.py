"""A run of comments in which the model reasoned to itself is removed at release, whole and only as comments.

Two of eight scored products lost a handoff point to such a block in their unit tests; the release can remove it
without a round of the sprint, since a comment changes nothing the program does.
"""
from __future__ import annotations

import ast
import re
from unittest import mock

import pytest

from app.stacks import contract, release_docs

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

PYTHON = '''def test_words():
    text = "abc123 test_456"
    # underscore is not in pattern, so "test_456" splits?
    # Wait, pattern is [a-zA-Z0-9']+. Underscore is NOT included.
    # So it returns ['test', '456'].
    assert count(text) == 3


def test_store():
    # A NOT NULL column keeps its default.
    try:
        insert(None)
        # Actually, in SQLite a NULL into a NOT NULL column uses the default.
        # But let's stick to the constraint test.
    except Error:
        pass  # expected
    note = """
    # Wait, this line is data in a string.
    """
'''

JAVASCRIPT = """export function total(items) {
  // eslint-disable-next-line no-unused-vars
  // Hmm, should an empty list be zero? Let me check the spec.
  // It should.
  return items.reduce((a, b) => a + b, 0);
}
// The sum of every item.
"""


@pytest.fixture
def product(tmp_path):
    (tmp_path / "app" / "tests").mkdir(parents=True)
    (tmp_path / "app" / "tests" / "test_core.py").write_text(PYTHON)
    (tmp_path / "app" / "sum.js").write_text(JAVASCRIPT)
    return tmp_path


def test_the_reasoning_block_goes_whole_and_the_code_still_parses(product):
    changed = release_docs.remove_thinking_aloud(product)
    assert sorted(changed) == ["app/sum.js", "app/tests/test_core.py"]
    python = (product / "app" / "tests" / "test_core.py").read_text()
    ast.parse(python)
    assert "Wait, pattern" not in python and "So it returns" not in python and "underscore" not in python
    assert "Actually" not in python and "let's stick" not in python
    assert "# A NOT NULL column keeps its default." in python, "a note for the reader stays"
    assert "# Wait, this line is data in a string." in python, "a line inside a string is never a comment"
    assert "pass  # expected" in python
    javascript = (product / "app" / "sum.js").read_text()
    assert "Hmm" not in javascript and "It should." not in javascript
    assert "eslint-disable-next-line" in javascript, "a comment a tool reads stays"
    assert "// The sum of every item." in javascript


def test_a_file_the_harness_owns_is_never_touched(product):
    before = (product / "app" / "tests" / "test_core.py").read_text()
    owns = lambda root, rel: contract.LOCKED_SUITE if rel.endswith("test_core.py") else ""  # noqa: E731
    with mock.patch.object(contract, "owned_by_the_harness", owns):
        changed = release_docs.remove_thinking_aloud(product)
    assert changed == ["app/sum.js"]
    assert (product / "app" / "tests" / "test_core.py").read_text() == before


def test_a_product_with_no_such_comment_is_left_as_it_is(tmp_path):
    (tmp_path / "main.py").write_text("# Reads the settings.\nx = 1\n")
    assert release_docs.remove_thinking_aloud(tmp_path) == []
    assert (tmp_path / "main.py").read_text() == "# Reads the settings.\nx = 1\n"


def test_the_release_s_handoff_removes_them_even_with_the_docs_switch_off(product):
    with mock.patch.object(release_docs, "enabled", return_value=False):
        release_docs.complete_the_handoff(product)
    assert "Wait, pattern" not in (product / "app" / "tests" / "test_core.py").read_text()


def test_the_handoff_score_finds_none_after_it(product):
    # The score reads lines, not tokens: a line in a string that reads like one would still count there.
    path = product / "app" / "tests" / "test_core.py"
    path.write_text(path.read_text().replace("    # Wait, this line is data in a string.\n", ""))
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("score", Path(__file__).resolve().parents[1] / "scripts" / "bench" / "score.py")
    score = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(score)
    assert score.handoff(product / "app")["handoff"]["no_thinking_aloud_in_comments"] is False
    release_docs.remove_thinking_aloud(product)
    assert score.handoff(product / "app")["handoff"]["no_thinking_aloud_in_comments"] is True


def test_its_explanation_bans_the_product_words():
    assert not BANNED.search(release_docs.remove_thinking_aloud.__doc__ or "")
