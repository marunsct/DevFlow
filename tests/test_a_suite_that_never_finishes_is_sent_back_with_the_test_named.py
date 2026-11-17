"""A suite that timed out goes back to QA with the test that never finished named, and why.

One run's suite timed out with `FFF.F.F.FFF.`: twelve tests finished and the
thirteenth ran the product's start script, which never returns. QA was told only
"timed out" and decided the product was missing - forty calls trying to build it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.acceptance import suite

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _suite(root: Path, names: list[str]) -> None:
    (root / ".harness").mkdir()
    (root / ".harness" / "acceptance.json").write_text(json.dumps({"project": "notes-api", "acceptance_dir": "acceptance"}))
    folder = root / "notes-api" / "acceptance"
    folder.mkdir(parents=True)
    (folder / "test_acceptance.py").write_text("".join(f"def {name}(base_url):\n    pass\n\n" for name in names))


def test_the_test_after_the_last_mark_is_the_one_that_never_finished(tmp_path):
    names = [f"test_ac{i}_x" for i in range(1, 15)]
    _suite(tmp_path, names)
    output = "collecting ... collected 14 items\nFFF.F.F.FFF.\n"

    assert suite.the_test_that_did_not_finish(tmp_path, output) == "`test_ac13_x` in `notes-api/acceptance/test_acceptance.py`"
    assert suite.the_test_that_did_not_finish(tmp_path, "..........  [ 71%]\n") == "`test_ac11_x` in `notes-api/acceptance/test_acceptance.py`"


def test_no_marks_or_every_test_marked_names_none(tmp_path):
    _suite(tmp_path, ["test_ac1_x", "test_ac2_x"])

    assert suite.the_test_that_did_not_finish(tmp_path, "collected 2 items\n") == ""
    assert suite.the_test_that_did_not_finish(tmp_path, "..\n") == ""


def test_the_review_sends_it_back_as_a_test_problem_not_a_missing_product(tmp_path):
    from workflow_nodes import an_acceptance_review_measured

    names = [f"test_ac{i}_x" for i in range(1, 15)]
    timed_out = suite.AcceptanceResult(ran=False, exit_code=124, problem="timed out",
                                       output="collecting ... collected 14 items\nFFF.F.F.FFF.\n")

    update = an_acceptance_review_measured(tmp_path, timed_out, pack="python-http-api", files={
        "test_acceptance.py": "".join(f"def {name}(base_url):\n    pass\n\n" for name in names)})

    [said] = [problem for problem in update["acceptance_feedback"] if "never finished" in problem]
    assert update["stage"] == "acceptance_author"
    assert "`test_ac13_x`" in said and "not the product" in said
    assert not BANNED.search(said)
