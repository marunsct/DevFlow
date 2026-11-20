"""Every lock of the suite - a repair out of rounds too - makes its once-per-lock send-backs at the limit available again.

Found in the suite-repair design review: only the review's own lock cleared the once-at-the-limit marks and the copy
of the suite kept before such a send-back. A repair that ran out of rounds locked without clearing them, so the next
reopen had no send-back at its limit, and could later put back a suite from before that lock.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.acceptance import suite
from app.graph import acceptance_nodes
from workflow_nodes import an_acceptance_review_measured

LOCKED = "test('[AC-1] adds', async () => { expect(1).toBe(1); });\ntest('[AC-2] deletes', async () => {});\n"
UNLOADABLE = "test('[AC-1] adds', async () => { expect(\n"
MARKS = {"partial_strengthened_once": True, "cannot_pass_repaired_once": True, "strengthened_once": True,
         "cannot_pass_sent": 3}


def test_a_repair_out_of_rounds_clears_the_send_backs_spent_and_the_suite_kept_before_them(tmp_path):
    (tmp_path / ".project-directory").write_text("notes\n")
    spec = tmp_path / "notes" / "acceptance" / "notes.spec.js"
    spec.parent.mkdir(parents=True)
    spec.write_text(LOCKED)
    suite.lock(tmp_path)
    suite.unlock(tmp_path)
    suite.repairing(tmp_path, ["[AC-1] adds"])
    saved = tmp_path / ".harness" / "acceptance.json"
    saved.write_text(json.dumps({**json.loads(saved.read_text()), **MARKS}))
    kept_before = tmp_path / ".harness" / "suite-before-the-send-back.json"
    kept_before.write_text(json.dumps({str(spec): "an older suite"}))

    update = an_acceptance_review_measured(
        tmp_path, suite.AcceptanceResult(ran=False, problem="SyntaxError: the spec file cannot load"),
        files={"notes.spec.js": UNLOADABLE},
        state={"acceptance_round": acceptance_nodes.MAX_ACCEPTANCE_ROUNDS + 2, "acceptance_return_to": "release"})

    assert update["stage"] == "release" and suite.is_locked(tmp_path)
    assert not set(MARKS) & set(json.loads(saved.read_text()))
    assert not Path(kept_before).exists()
