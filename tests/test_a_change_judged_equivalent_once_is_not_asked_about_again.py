"""A deliberate change judged equivalent once is not raised or asked about again (plan item 13d, behind `EQUIVALENT_MUTANTS_REMEMBERED`).

Measured: the verdict "this change behaves as the original" lived only in the
one finding it closed; the next sprint attempt's probe chose the same change,
raised it again and spent another fix stage on the same reasoning. With the
switch on the verdict is kept in the workspace by file, line text and operator,
the probe leaves such a change out before it counts its few changes, and the
fixer's verdict is read in its usual spellings. Off, nothing is kept or skipped.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.acceptance import mutation_equivalents, mutation_guided
from app.agents.specialists import SpecialistOutput
from app.sprint import RemediationCycle

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
SOURCE = "def over(a, b):\n    return a > b\n\n\ndef under(a, b):\n    return a < b\n"
WHY = "both comparisons agree for every input the function can be given"


@pytest.fixture
def product(tmp_path, monkeypatch):
    monkeypatch.setenv("EQUIVALENT_MUTANTS_REMEMBERED", "on")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "calc.py").write_text(SOURCE, encoding="utf-8")
    monkeypatch.setattr(
        "app.stacks.contract.the_pack",
        lambda root: (SimpleNamespace(kind="python_service", kept_files=[]), {"project": ""}),
    )
    return tmp_path


def _a_site(line=2, column=13, text="    return a > b", original=">", replacement="<="):
    return {"file": "src/calc.py", "line": line, "column": column, "original": original,
            "replacement": replacement, "text": text}


def _settle(product: Path, result: SpecialistOutput):
    from app.graph.workflow import _settle_the_fix

    finding = mutation_guided.defect(_a_site())
    cycle = RemediationCycle(sprint_goal="g", defects=[finding])
    state = {"repository": SimpleNamespace(root_path=str(product)), "specialist_outputs": {}, "test_round": 2}
    update, _ = _settle_the_fix(state, cycle, 0, "defect_fix_2_0", result, measured="after defect_fix_2_0")
    return update["remediation"].defects[0]


def test_a_verdict_of_equivalent_is_kept_and_the_probe_does_not_choose_that_change_again(product):
    with patch.object(mutation_guided, "settled", return_value=False):
        closed = _settle(product, SpecialistOutput(decisions=[f"Equivalent: {WHY}"]))
    assert closed.status == "accepted_risk"
    assert mutation_equivalents.is_known(product, _a_site())

    survivors = mutation_guided.probe(product, ["src/calc.py"], count=12, run_unit=lambda: True)

    assert [(s["line"], s["original"], s["replacement"]) for s in survivors]
    assert (2, ">", "<=") not in [(s["line"], s["original"], s["replacement"]) for s in survivors]


def test_the_known_change_does_not_use_up_one_of_the_few_a_sprint_tries(product):
    with patch.object(mutation_guided, "settled", return_value=False):
        _settle(product, SpecialistOutput(decisions=[f"Equivalent: {WHY}"]))

    survivors = mutation_guided.probe(product, ["src/calc.py"], count=1, run_unit=lambda: True)

    assert len(survivors) == 1 and survivors[0]["line"] == 6


def test_the_same_change_where_the_fix_moved_it_is_still_the_same_change(product):
    mutation_equivalents.record(product, _a_site(), WHY)
    (product / "src" / "calc.py").write_text("import math\n\n" + SOURCE, encoding="utf-8")

    survivors = mutation_guided.probe(product, ["src/calc.py"], count=12, run_unit=lambda: True)

    assert (3, ">", "<=") not in [(s["line"], s["original"], s["replacement"]) for s in survivors]
    assert survivors


def test_another_operator_on_the_same_line_is_another_change(product):
    mutation_equivalents.record(product, _a_site(), WHY)
    assert not mutation_equivalents.is_known(product, _a_site(replacement=">="))
    assert not mutation_equivalents.is_known(product, {**_a_site(), "file": "src/other.py"})


def test_a_change_closed_as_a_gap_is_not_remembered_since_a_better_test_may_notice_it(product):
    with patch.object(mutation_guided, "settled", return_value=False):
        from app.graph.workflow import _settle_the_fix

        finding = mutation_guided.defect(_a_site()).model_copy(update={"fix_attempts": mutation_guided.MOST_TRIES - 1})
        cycle = RemediationCycle(sprint_goal="g", defects=[finding])
        state = {"repository": SimpleNamespace(root_path=str(product)), "specialist_outputs": {}, "test_round": 2}
        update, _ = _settle_the_fix(state, cycle, 0, "defect_fix_2_0", SpecialistOutput(changed_files=["tests/t.py"]),
                                    measured="x")
    assert update["remediation"].defects[0].status == "accepted_risk"
    assert not mutation_equivalents.is_known(product, _a_site())


@pytest.mark.parametrize("said", [
    f"Equivalent: {WHY}", f"Equivalent mutant: {WHY}", f"equivalent - {WHY}",
    f"This is an equivalent mutant: {WHY}", f"An equivalent change - {WHY}",
])
def test_the_verdict_is_read_in_its_usual_spellings(product, said):
    assert mutation_guided.equivalent_because(SpecialistOutput(decisions=[said])) == WHY


@pytest.mark.parametrize("said", ["Equivalent: yes", "not equivalent: the tests are weak", f"The change is {WHY}"])
def test_a_reason_too_short_or_a_verdict_of_not_equivalent_is_no_verdict(product, said):
    assert mutation_guided.equivalent_because(SpecialistOutput(decisions=[said])) == ""


def test_off_only_the_one_prefix_counts_and_nothing_is_kept_or_skipped(product, monkeypatch):
    monkeypatch.setenv("EQUIVALENT_MUTANTS_REMEMBERED", "off")
    assert mutation_guided.equivalent_because(SpecialistOutput(decisions=[f"Equivalent mutant: {WHY}"])) == ""
    assert mutation_guided.equivalent_because(SpecialistOutput(decisions=[f"Equivalent: {WHY}"])) == WHY

    with patch.object(mutation_guided, "settled", return_value=False):
        _settle(product, SpecialistOutput(decisions=[f"Equivalent: {WHY}"]))
    assert not (product / mutation_equivalents.FILE).exists()
    survivors = mutation_guided.probe(product, ["src/calc.py"], count=12, run_unit=lambda: True)
    assert (2, ">", "<=") in [(s["line"], s["original"], s["replacement"]) for s in survivors]


def test_the_record_is_kept_beside_the_harness_s_own_files_where_git_ignores_it():
    assert mutation_equivalents.FILE.startswith(".harness/")
    assert not BANNED.search(mutation_equivalents.__doc__.split("\n\n")[0])


def test_the_switch_is_an_experiment_that_ships_off():
    from app import switches

    assert "EQUIVALENT_MUTANTS_REMEMBERED" in switches.EXPERIMENTS
    assert "EQUIVALENT_MUTANTS_REMEMBERED" not in switches.EXPERIMENTS_ON
    assert mutation_equivalents.ON_BY_DEFAULT is False
