"""A criterion that speaks of whitespace is tested with more than a plain space, or the suite goes back.

Measured on two runs of one brief: `title_case` leaves "the whitespace exactly as it was"; every locked test used
spaces alone, a product splitting words on spaces only passed, and a hidden test with a tab failed. The prompt rule
(LF.842) did not reach the second suite.
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

from app.acceptance import suite
from app.acceptance.criteria import Criterion
from app.graph import acceptance_nodes

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
SPACES = '''
def test_ac4_ac9_title_case_whitespace_preservation(textkit):
    assert textkit.title_case("  hello  world  ") == "  Hello  World  "


class TestOther:
    def test_ac2_slugify(self, textkit):
        assert textkit.slugify("A b") == "a-b"
'''


def _a_suite(root: Path, text: str) -> None:
    suite_dir = root / "lib" / "acceptance"
    suite_dir.mkdir(parents=True)
    (suite_dir / "run.json").write_text(json.dumps({"command": ["run"], "report": "r.xml"}))
    (suite_dir / "test_title_case.py").write_text(text)
    (root / ".project-directory").write_text("lib\n")
    suite.save_criteria(root, [
        Criterion("AC-9", "title_case upper-cases the first letter of every word, leaving the whitespace exactly as it was", "brief"),
        Criterion("AC-2", "slugify lower-cases and joins words with hyphens", "brief"),
    ])


def test_spaces_alone_are_found(tmp_path):
    _a_suite(tmp_path, SPACES)
    found = suite.whitespace_tested_with_spaces_only(tmp_path)
    assert len(found) == 1 and found[0].startswith("AC-9 speaks of whitespace")
    assert "`test_ac4_ac9_title_case_whitespace_preservation`" in found[0]
    assert not BANNED.search(found[0])


def test_a_tab_or_a_line_break_in_a_test_of_it_holds(tmp_path):
    for i, extra in enumerate(['    assert textkit.title_case("a\\tb") == "A\\tB"\n',
                               '    assert textkit.title_case("a\\nb") == "A\\nB"\n']):
        root = tmp_path / str(i)
        _a_suite(root, SPACES.replace('== "  Hello  World  "\n', '== "  Hello  World  "\n' + extra))
        assert suite.whitespace_tested_with_spaces_only(root) == [], extra


def test_the_lock_sends_it_back_and_once_more_at_the_limit():
    source = inspect.getsource(acceptance_nodes.acceptance_review)
    assert 'check_findings.noted(root, rounds, "whitespace_tested_with_spaces_only"' in source
    assert "if partial and rounds == MAX_ACCEPTANCE_ROUNDS:" in source
