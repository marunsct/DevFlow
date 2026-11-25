"""A fixer that changed nothing gets the rewrite after a surrender in a batch too, and one that gave no answer is
rewritten on the files it read most (LF.1404).

Measured on one medium run: two fixers of one batch read for 17 and 19 calls (31 and 27 reads of 10 files, one file
8 times), wrote nothing - one edit refused - and ended with no answer, the harness's record of it in its place. A
fixer alone that surrendered got the rewrite; these two did not, because fixers of a batch never asked for it, and a
fixer that gave no answer names no file in an answer for the rewrite to take.
"""
from __future__ import annotations

import pytest
import the_fix_stage

from app.agents.specialists import SpecialistOutput
from app.graph import batch_file_claims as claims
from app.sprint import Defect

GAVE_UP = SpecialistOutput(changed_files=[])


@pytest.fixture(autouse=True)
def _a_run_with_a_transcript(tmp_path, monkeypatch):
    monkeypatch.setenv("SURRENDER_TO_REWRITE", "on")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr("app.observability.transcript._run_id_from_config", lambda: "r")
    yield
    claims.forget("r", [f"defect_fix_2_{index}" for index in range(10)])


def _workspace(root):
    for name, text in {"proj/acceptance/auth.spec.js": "test('[AC-1] sign-up', () => {});\n",
                       "proj/app/db.js": "export const db = null;\n",
                       "proj/app/routes.js": "export const routes = [];\n",
                       "proj/app/main.js": "export const main = 1;\n",
                       "proj/app/schemas.js": "export const schemas = {};\n"}.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)


def _a_criterion_the_suite_judges():
    return Defect(description="[AC-1] Sign-up works - the acceptance suite says this does not work yet.",
                  severity="major", owner="backend", reproduction_steps="run the acceptance suite",
                  expected_behavior="201", affected_files=[],
                  actual_behavior="Expected: 201\nReceived: 500\n    at /workspace/proj/acceptance/auth.spec.js:27:29")


def _no_answer():
    """What the harness records for a fix stage whose calls were spent with no answer."""
    from app.graph.workflow import _blocked_when_retries_exhausted

    return _blocked_when_retries_exhausted("defect_fix_2_0")


def _reads(*paths):
    from app.observability.transcript import record

    def reading(stage):
        for path in paths:
            record("r", stage, "tool_call", tool="read_file", args={"file_path": path})
    return reading


def test_a_fixer_of_a_batch_that_changed_nothing_gets_the_rewrite(tmp_path):
    _workspace(tmp_path)
    defect = the_fix_stage.a_defect("The sign-up handler drops the name", affected_files=["proj/app/db.js"])
    wrote = SpecialistOutput(changed_files=["proj/app/db.js"])

    update, seen = the_fix_stage.run(tmp_path, the_fix_stage.a_state(tmp_path, defect, __fix_index=0),
                                     node="defect_fix_worker", answer=GAVE_UP, rewrite=wrote, real_files=True)

    assert [r["files"] for r in seen.rewrites] == [["proj/app/db.js"]]
    assert update["specialist_outputs"]["defect_fix_2_0"] is wrote


def test_a_fixer_that_gave_no_answer_is_rewritten_on_the_files_it_read_most(tmp_path):
    """Its defect and failure name only the acceptance test; it read the module at fault most."""
    _workspace(tmp_path)
    read = _reads("proj/app/routes.js", "proj/app/db.js", "proj/app/db.js", "proj/app/main.js", "proj/app/db.js",
                  "proj/app/schemas.js", "proj/app/main.js")

    _, seen = the_fix_stage.run(tmp_path, the_fix_stage.a_state(tmp_path, _a_criterion_the_suite_judges()),
                                answer=_no_answer(), during=read, real_files=True)

    assert [r["files"] for r in seen.rewrites] == [["proj/app/db.js", "proj/app/main.js", "proj/app/routes.js"]]


def test_a_fixer_that_answered_is_not_rewritten_on_what_it_only_read(tmp_path):
    """An answer names where it looked; reads join only when there is no answer to name a file."""
    _workspace(tmp_path)

    _, seen = the_fix_stage.run(tmp_path, the_fix_stage.a_state(tmp_path, _a_criterion_the_suite_judges()),
                                answer=GAVE_UP, during=_reads("proj/app/db.js", "proj/app/db.js"), real_files=True)

    assert seen.rewrites == []


def test_a_batch_fixer_s_rewrite_leaves_a_file_another_fixer_of_its_batch_wrote(tmp_path):
    from app.observability.transcript import read_transcript

    _workspace(tmp_path)
    defect = the_fix_stage.a_defect("The sign-up handler drops the name",
                                    affected_files=["proj/app/db.js", "proj/app/routes.js"])

    def another_fixer_writes_db(stage):
        with claims.holding("r", "defect_fix_2_9"):
            claims.claim("r", "defect_fix_2_9", "write_artifact", {"relative_path": "proj/app/db.js"})

    _, seen = the_fix_stage.run(tmp_path, the_fix_stage.a_state(tmp_path, defect, __fix_index=0),
                                node="defect_fix_worker", answer=GAVE_UP, during=another_fixer_writes_db,
                                real_files=True)

    assert [r["files"] for r in seen.rewrites] == [["proj/app/routes.js"]]
    assert [r["event"] for r in read_transcript("r", {"defect"})].count("rewrite after surrender") == 1


def test_what_a_batch_fixer_s_rewrite_wrote_is_that_fixer_s_when_its_batch_is_measured(tmp_path):
    """A batch that broke a test puts back the culprit's files: the rewrite's files are its fixer's."""
    _workspace(tmp_path)
    defect = the_fix_stage.a_defect("The sign-up handler drops the name", affected_files=["proj/app/db.js"])

    the_fix_stage.run(tmp_path, the_fix_stage.a_state(tmp_path, defect, __fix_index=0), node="defect_fix_worker",
                      answer=GAVE_UP, rewrite=SpecialistOutput(changed_files=["proj/app/db.js"]), real_files=True)

    assert claims.written_by("r", "defect_fix_2_0") == ["proj/app/db.js"]
