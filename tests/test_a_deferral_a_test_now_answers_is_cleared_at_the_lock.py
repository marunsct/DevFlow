"""A criterion QA deferred for want of a test is no longer deferred once a test's title carries it.

Measured on a held-out run: QA deferred AC-14 and AC-15 in its first round, wrote two tests titled `[AC-14][AC-15]`
in a later one, and the deferral stayed. The suite locked with a note saying the reason no longer held, and the
release listed both criteria as shipped unproven although a locked test covered them.
"""
from __future__ import annotations

import inspect

from app.acceptance import suite
from app.acceptance.criteria import number
from app.graph import acceptance_nodes

BRIEF = "# Brief\n## Features\n- Add a note\n- Delete a note\n- Start it\n"


def _workspace(tmp_path, spec_text):
    (tmp_path / ".project-directory").write_text("notes\n")
    suite.save_criteria(tmp_path, number(BRIEF), {
        "AC-2": "no test title carries this id", "AC-3": "no automated test can check how it starts"})
    spec = tmp_path / "notes" / "acceptance" / "notes.spec.js"
    spec.parent.mkdir(parents=True)
    spec.write_text(spec_text)
    return tmp_path


def test_a_deferred_criterion_a_test_now_carries_is_taken_off_the_list(tmp_path):
    root = _workspace(tmp_path, "test('[AC-1] adds', async () => {});\ntest('[AC-2] deletes', async () => {});\n")
    assert suite.undefer_what_a_test_now_carries(root) == ["AC-2"]
    assert set(suite.deferred(root)) == {"AC-3"}


def test_a_deferred_criterion_no_test_carries_stays_deferred(tmp_path):
    root = _workspace(tmp_path, "test('[AC-1] adds', async () => {});\n")
    assert suite.undefer_what_a_test_now_carries(root) == []
    assert set(suite.deferred(root)) == {"AC-2", "AC-3"}


def test_the_lock_clears_them_before_it_records(tmp_path):
    source = inspect.getsource(acceptance_nodes.acceptance_review)
    assert source.index("undefer_what_a_test_now_carries") < source.index("suite.lock(root)")
