"""Mutation findings in one file are shown to each fixer together, and one an earlier fix settled gets no fixer.

Measured on one run: three findings, each `True` made `False` at the same column of one file, went to three fix
stages of 11 to 13 calls each, about nine minutes; one test written with all three in view could settle them together,
and a finding a test already notices needs two unit runs, not a fix stage.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from app.acceptance import mutation_guided
from app.graph import workflow

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _site(line, file="api/app.py"):
    return {"file": file, "line": line, "column": 39, "original": "True", "replacement": "False",
            "text": "    return jsonify(found), True"}


def test_a_fixer_is_shown_the_other_open_findings_in_its_file():
    one, two, three, elsewhere = (mutation_guided.defect(_site(71)), mutation_guided.defect(_site(141)),
                                  mutation_guided.defect(_site(180)), mutation_guided.defect(_site(9, "api/db.py")))
    three.status = "fixed"
    told = mutation_guided.what_settles_it(one, [one, two, three, elsewhere])
    assert "`api/app.py` line 141, column 39: `True` made `False`" in told
    assert "line 71," not in told.split("--- What settles this finding ---")[0]  # not itself
    assert "line 180" not in told and "api/db.py" not in told  # not a settled one, nor another file's
    assert not BANNED.search(told)
    assert "The other changes" not in mutation_guided.what_settles_it(elsewhere, [elsewhere])


def test_the_brief_is_given_the_round_s_findings():
    import inspect

    assert "mutation_guided.what_settles_it(defect, cycle.defects)" in inspect.getsource(workflow)


def test_a_finding_an_earlier_fix_settled_is_closed_before_a_fixer(monkeypatch, tmp_path):
    finding = mutation_guided.defect(_site(71))
    state = {"repository": SimpleNamespace(root_path=str(tmp_path))}
    monkeypatch.setattr(mutation_guided, "settled", lambda root, defect: True)
    assert workflow._resolved_by_a_measurement(state, finding)[0] == "the unit tests"
    # Not at the round's own measurement: a finding its probe just raised is unnoticed by definition.
    assert workflow._resolved_by_a_measurement(state, finding, measured_since=False) == ("", "")
    monkeypatch.setattr(mutation_guided, "settled", lambda root, defect: False)
    assert workflow._resolved_by_a_measurement(state, finding) == ("", "")
