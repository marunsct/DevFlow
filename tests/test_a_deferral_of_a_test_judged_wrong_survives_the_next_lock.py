"""A deferral the harness made because its judged tests cannot pass survives the next lock while those tests stand.

Measured on one run: a dispute ruled two tests wrong past the reclassification cap and their criteria were deferred;
the next lock took the deferrals off because another test - repaired for its own fault - carried one of the ids in its
title, and fixers worked a right product for 283 more model calls.
"""
from __future__ import annotations

import json

from app.acceptance import suite
from app.acceptance.criteria import number

BRIEF = "# Brief\n## Features\n- Count words\n- Print JSON\n- Keep a trailing newline\n"
HARNESS = f"{suite.DEFERRED_BY_THE_HARNESS[1]} whatever is built: the expected count is 24 for a 25-character input"
SPEC = ("test('[AC-1][AC-3] counts', async () => { expect(1).toBe(1); });\n"
        "test('[AC-2] json', async () => { expect(24).toBe(25); });\n"
        "test('[AC-3] trailing', async () => { expect(18).toBe(19); });\n")


def _workspace(tmp_path, spec_text=SPEC):
    (tmp_path / ".project-directory").write_text("words\n")
    suite.save_criteria(tmp_path, number(BRIEF), {"AC-2": HARNESS, "AC-3": HARNESS})
    spec = tmp_path / "words" / "acceptance" / "words.spec.js"
    spec.parent.mkdir(parents=True)
    spec.write_text(spec_text)
    suite.record_judged_unpassable(tmp_path, {"AC-2": ["[AC-2] json"], "AC-3": ["[AC-3] trailing"]})
    return tmp_path, spec


def _repairing(root, names):
    path = root / suite.STATE_FILE
    state = json.loads(path.read_text())
    state["repairing"] = names
    path.write_text(json.dumps(state))


def test_a_repair_of_another_test_carrying_the_id_keeps_both_deferred(tmp_path):
    root, _ = _workspace(tmp_path)
    _repairing(root, ["[AC-1][AC-3] counts"])
    assert suite.undefer_what_a_test_now_carries(root) == []
    assert set(suite.deferred(root)) == {"AC-2", "AC-3"}


def test_the_judged_test_sent_for_repair_lifts_its_deferral(tmp_path):
    root, _ = _workspace(tmp_path)
    _repairing(root, ["[AC-2] json"])
    assert suite.undefer_what_a_test_now_carries(root) == ["AC-2"]


def test_the_judged_test_rewritten_or_renamed_lifts_its_deferral(tmp_path):
    root, spec = _workspace(tmp_path)
    spec.write_text(SPEC.replace("expect(24).toBe(25)", "expect(25).toBe(25)"))
    assert suite.undefer_what_a_test_now_carries(root) == ["AC-2"]
    (tmp_path / "b").mkdir()
    root2, spec2 = _workspace(tmp_path / "b")
    spec2.write_text(SPEC.replace("[AC-3] trailing", "[AC-3] keeps its trailing newline"))
    assert suite.undefer_what_a_test_now_carries(root2) == ["AC-3"]


def test_a_deferral_qa_made_is_lifted_as_before(tmp_path):
    root, _ = _workspace(tmp_path)
    suite.save_criteria(root, number(BRIEF), {"AC-2": "no test title carries this id"})
    assert suite.undefer_what_a_test_now_carries(root) == ["AC-2"]


# Measured on one run with a Python suite written as classes: a dispute called six tests wrong (a shared helper had
# lost its `+`), two were repaired, four went past the cap and AC-7 and AC-11 were deferred - and the very next lock
# lifted both, because no test had been recorded against them: the dispute's sentences carry no criterion tags, and the
# test reader found no method inside a class. Fixers were then sent to tests no product could pass.
PY = '''import json


class TestAC7Words:
    def test_ac7_apostrophes(self, run_cli):
        assert run_cli("f").stdout == _compute(TEXT)

    def test_ac7_trailing_newline(self, run_cli):
        assert run_cli("g").stdout == _compute(TEXT)


class TestAC11Exact:
    def test_ac11_exact_counts(self, run_cli):
        assert run_cli("h").stdout == _compute(TEXT)
'''


def test_a_python_class_suite_s_judged_tests_keep_their_deferrals(tmp_path):
    from types import SimpleNamespace

    from app.graph import acceptance_nodes
    from app.graph.workflow import criteria_past_the_cap, past_the_cap_with_their_criteria

    (tmp_path / ".project-directory").write_text("words\n")
    suite.save_criteria(tmp_path, number(BRIEF + "- Exact counts\n- Words with apostrophes\n- More\n- More\n- More\n"
                                         "- More\n- More\n- More\n"))
    path = tmp_path / "words" / "acceptance" / "test_cli.py"
    path.parent.mkdir(parents=True)
    path.write_text(PY)
    failing = [("test_ac7_apostrophes", "[AC-7] A word is a run of letters", "assert 10 == 2"),
               ("test_ac7_trailing_newline", "[AC-7] A word is a run of letters", "assert 10 == 2"),
               ("test_ac11_exact_counts", "[AC-11] Counts are exact", "assert 10 == 2")]
    past = ["`test_ac7_apostrophes` cannot pass for any product that does what its criterion says",
            "test_ac7_trailing_newline", "`test_ac11_exact_counts` cannot pass: the helper counts letters"]

    lines = past_the_cap_with_their_criteria(failing, past)
    assert lines[0].startswith("[AC-7] `test_ac7_apostrophes`") and lines[1] == "[AC-7] `test_ac7_trailing_newline`"
    assert lines[2].startswith("[AC-11] `test_ac11_exact_counts`")

    state = SimpleNamespace(root_path=str(tmp_path))
    acceptance_nodes.defer_what_is_beyond_repair(
        {"repository": state}, criteria_past_the_cap(failing, past),
        [f"{line}: the dispute judged it wrong, and this run may reclassify no more tests" for line in lines])

    assert set(suite.deferred(tmp_path)) == {"AC-7", "AC-11"}
    assert suite.undefer_what_a_test_now_carries(tmp_path) == []
    assert set(suite.deferred(tmp_path)) == {"AC-7", "AC-11"}
