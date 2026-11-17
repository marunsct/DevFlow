"""A fixer asked for a test that notices a deliberate change is told at each write whether it does (plan item 13b, behind `MUTANT_CHECK_IN_THE_FIX_STAGE`).

Measured: a mutation finding was settled by the harness only after the fix
stage ended, so the fixer wrote its test blind - the checks after a write had
no tests of the defect's own to run for a finding - and a test that noticed
nothing cost a second stage the sprint often had no round for: the finding
became a completion gap (6 of 7 runs left gaps). With the switch on each write
runs that one change against the unit tests as they now are and says so in the
write's reply. Off, a finding's writes are answered with nothing, as before.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.acceptance import mutant_check_in_stage, mutation_guided
from app.graph import verify_after_write

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
SOURCE = "def over(a, b):\n    return a > b\n"
RUN, STAGE = "run-1", "defect_fix_2_0"


@pytest.fixture(autouse=True)
def _the_checks_after_a_write_are_on(monkeypatch):
    monkeypatch.setenv("VERIFY_AFTER_WRITE", "on")


@pytest.fixture
def product(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "calc.py").write_text(SOURCE, encoding="utf-8")
    return tmp_path


def _finding():
    return mutation_guided.defect({"file": "src/calc.py", "line": 2, "column": 13, "original": ">",
                                   "replacement": "<=", "text": "    return a > b"})


def _a_write():
    return SimpleNamespace(status="success", content="Wrote src/test_calc.py")


def _unit_tests(product: Path, written: dict):
    """A unit run: `compares` exists once the fixer has written it, and fails while the comparison is turned round."""
    def run():
        turned = "a <= b" in (product / "src" / "calc.py").read_text(encoding="utf-8")
        return {"kept"} | ({"compares"} if written.get("test") and not turned else set())
    return lambda root: run()


def test_a_write_is_answered_with_whether_the_change_is_now_noticed(product, monkeypatch):
    monkeypatch.setenv("MUTANT_CHECK_IN_THE_FIX_STAGE", "on")
    written: dict = {}
    finding = _finding()
    with patch.object(mutation_guided, "_run_the_unit_tests", _unit_tests(product, written)), \
         verify_after_write.watching(
             RUN, STAGE, mutant_check_in_stage.check_for(product, finding, lambda: None),
             **mutant_check_in_stage.how_for(finding)):
        first = verify_after_write.after_a_write("write_artifact", _a_write(), RUN, STAGE)
        written["test"] = True
        second = verify_after_write.after_a_write("write_artifact", _a_write(), RUN, STAGE)

    assert first.content.endswith(mutant_check_in_stage.SAYS[1]) and "no test notices it yet" in first.content
    assert second.content.endswith(mutant_check_in_stage.SAYS[0]) and "give your answer now" in second.content
    assert (product / "src" / "calc.py").read_text(encoding="utf-8") == SOURCE
    for line in mutant_check_in_stage.SAYS:
        assert not BANNED.search(line), line


def test_a_stage_gets_only_a_few_checks_since_each_is_two_runs_of_the_unit_tests(product, monkeypatch):
    monkeypatch.setenv("MUTANT_CHECK_IN_THE_FIX_STAGE", "on")
    finding = _finding()
    with patch.object(mutation_guided, "_run_the_unit_tests", _unit_tests(product, {})), \
         verify_after_write.watching(
             RUN, STAGE, mutant_check_in_stage.check_for(product, finding, lambda: None),
             **mutant_check_in_stage.how_for(finding)):
        answers = [verify_after_write.after_a_write("write_artifact", _a_write(), RUN, STAGE).content for _ in range(5)]

    assert [a != "Wrote src/test_calc.py" for a in answers] == [True] * mutant_check_in_stage.MOST_CHECKS + [False] * 2


def test_off_or_for_any_other_defect_the_defects_own_tests_answer_as_before(product, monkeypatch):
    other = SimpleNamespace(source="test round")
    default = lambda: True  # noqa: E731
    monkeypatch.setenv("MUTANT_CHECK_IN_THE_FIX_STAGE", "on")
    assert mutant_check_in_stage.check_for(product, other, default) is default
    assert mutant_check_in_stage.how_for(other) == {}
    monkeypatch.setenv("MUTANT_CHECK_IN_THE_FIX_STAGE", "off")
    assert mutant_check_in_stage.check_for(product, _finding(), default) is default
    assert mutant_check_in_stage.how_for(_finding()) == {}

    with verify_after_write.watching(RUN, STAGE, default):
        answered = verify_after_write.after_a_write("write_artifact", _a_write(), RUN, STAGE)
    assert answered.content.endswith(verify_after_write.PASSED)


def test_a_check_with_its_own_words_and_budget_is_what_watching_stores():
    with verify_after_write.watching(RUN, STAGE, lambda: False, says=("yes", "no"), most=1):
        one = verify_after_write.after_a_write("write_artifact", _a_write(), RUN, STAGE)
        two = verify_after_write.after_a_write("write_artifact", _a_write(), RUN, STAGE)
    assert one.content.endswith("\nno") and two.content == "Wrote src/test_calc.py"


def test_the_fix_stage_asks_the_finding_s_own_check(tmp_path, monkeypatch):
    from app.sprint import Defect
    from workflow_node_stubs import one_defect, run_a_fixer

    asked = []

    def finding_s_own(root, defect, default):
        asked.append((Path(root), defect, default))
        return "the finding's own check"

    monkeypatch.setattr(mutant_check_in_stage, "check_for", finding_s_own)
    monkeypatch.setattr(mutant_check_in_stage, "how_for",
                        lambda defect: {"says": ("noticed", "not noticed"), "most": 1} if isinstance(defect, Defect) else {})
    cycle = one_defect()

    seen = run_a_fixer(monkeypatch, tmp_path, cycle=cycle)

    (root, defect, default), = asked
    assert root == tmp_path and defect == cycle.defects[0] and callable(default)
    args, kwargs = seen.watching
    assert args[1] == "defect_fix_1_0" and args[2] == "the finding's own check"
    assert kwargs == {"says": ("noticed", "not noticed"), "most": 1}
