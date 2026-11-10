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
