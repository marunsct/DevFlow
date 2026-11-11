"""An output the brief gives in place of another is held by some test to its whole form, or the suite goes back.

Measured on three runs of one brief: `--json` prints the counts, "or with `--top N` prints `{"top": [...]}`". The
locked test checked only that `top` was in the output, and a product printing the counts and the top words together
passed it (two false acceptances, a third on its way). A prompt rule to the writer and its reviewer did not reach the
test, so the harness reads it.
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

from app.acceptance import suite
from app.graph import acceptance_nodes

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
BRIEF = ('- `--json` prints `{"words": n, "lines": n, "characters": n}`, or with `--top N` prints '
         '`{"top": [{"word": w, "count": c}, ...]}`.\n')
SIGN_IN = ('- `POST /signin` with `{"username": ..., "password": ...}` answers 200 with `{"token": <string>}`, '
           'or 401.\n- A note is `{"id": <integer>, "title": <string>, "body": <string>}`.\n')

WEAK = '''
def test_ac3_json(run_cli):
    data = json.loads(run_cli("--json", "f").stdout)
    assert data["words"] == 5
    assert "top" not in data

def test_ac9_json_with_top(run_cli):
    data = json.loads(run_cli("--json", "--top", "3", "f").stdout)
    assert "top" in data
    assert data["top"][0] == {"word": "dog", "count": 3}
'''


def _a_suite(root: Path, text: str, name: str = "test_cli.py") -> None:
    suite_dir = root / "app" / "acceptance"
    suite_dir.mkdir(parents=True)
    (suite_dir / "run.json").write_text(json.dumps({"command": ["run"], "report": "r.xml"}))
    (suite_dir / name).write_text(text)
    (root / ".project-directory").write_text("app\n")


def test_a_test_that_looks_only_for_its_own_part_is_found(tmp_path):
    _a_suite(tmp_path, WEAK)
    found = suite.outputs_held_only_in_part(tmp_path, BRIEF)
    assert len(found) == 1
    assert '{"top": [{"word": w, "count": c}, ...]}' in found[0]
    assert "`characters`, `lines`, `words`" in found[0] and "would pass even if" in found[0]
    assert not BANNED.search(found[0])


def test_a_whole_comparison_or_an_absence_check_holds_it(tmp_path):
    for i, held in enumerate([
        'assert data == {"top": [{"word": "dog", "count": 3}]}',
        'assert "words" not in data',
        'assert set(data) == {"top"}',
        'assert sorted(data.keys()) == ["top"]',
    ]):
        root = tmp_path / str(i)
        _a_suite(root, WEAK + "    " + held + "\n")
        assert suite.outputs_held_only_in_part(root, BRIEF) == [], held


def test_a_script_suite_s_whole_comparison_holds_it(tmp_path):
    _a_suite(tmp_path, "expect(JSON.parse(out)).toEqual({ top: [{ word: 'dog', count: 3 }] });\n"
                       "expect(counts).not.toHaveProperty('top');\n", name="cli.test.js")
    assert suite.outputs_held_only_in_part(tmp_path, BRIEF) == []


def test_a_request_and_its_answer_are_not_two_forms_of_one_output(tmp_path):
    _a_suite(tmp_path, 'assert "token" in r.json()\nassert r.json()["title"] == "x"\n')
    assert suite.outputs_held_only_in_part(tmp_path, SIGN_IN) == []


def test_an_untested_form_is_left_to_the_coverage_checks(tmp_path):
    _a_suite(tmp_path, 'def test_ac1(run_cli):\n    assert run_cli("f").returncode == 0\n')
    assert suite.outputs_held_only_in_part(tmp_path, BRIEF) == []


def test_the_review_sends_it_back_and_once_more_at_the_limit():
    source = inspect.getsource(acceptance_nodes.acceptance_review)
    assert 'check_findings.noted(root, rounds, "outputs_held_only_in_part"' in source
    assert "if partial and rounds == MAX_ACCEPTANCE_ROUNDS:" in source
    assert "acceptance_feedback=[STRENGTHEN_ONLY, *partial]" in source
