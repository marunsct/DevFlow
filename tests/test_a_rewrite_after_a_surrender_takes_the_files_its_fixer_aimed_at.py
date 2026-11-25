"""The rewrite after a surrender takes the files the fixer aimed at, and a decline names the file and the rule.

Measured over the last 45 runs: 19 rewrites after a surrender were declined with one line, "the rewrite found no file
it may write, or wrote none". Eleven found no file - seven were criteria the acceptance suite judges, whose defect
named no file and whose failure named only the acceptance test, while the fixer had tried to edit the product module
at fault (the language service refused the edit) or named it in its answer. Eight rewrote a file and got it back
unchanged. Nothing said which. (LF.1401-LF.1403.)
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
import the_fix_stage

from app.agents.specialists import SpecialistOutput
from app.graph import rewritten_fixes
from app.sprint import Defect

GAVE_UP = SpecialistOutput(changed_files=[])


@pytest.fixture(autouse=True)
def _a_run_with_a_transcript(tmp_path, monkeypatch):
    monkeypatch.setenv("SURRENDER_TO_REWRITE", "on")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    # A node run on its own has no graph config to name its run by.
    monkeypatch.setattr("app.observability.transcript._run_id_from_config", lambda: "r")


def _workspace(root):
    for name, text in {"proj/acceptance/auth.spec.js": "test('[AC-1] sign-up', () => {});\n",
                       "proj/app/db.js": "export const db = null;\n",
                       "proj/app/routes.js": "export const routes = [];\n"}.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)


def _a_criterion_the_suite_judges(**more):
    fields = {"severity": "major", "owner": "backend", "reproduction_steps": "run the acceptance suite",
              "expected_behavior": "201", "affected_files": [],
              "actual_behavior": "Expected: 201\nReceived: 500\n    at /workspace/proj/acceptance/auth.spec.js:27:29",
              **more}
    return Defect(description="[AC-1] Sign-up works - the acceptance suite says this does not work yet.", **fields)


def _declined(root, state, **run):
    from app.observability.transcript import read_transcript

    _, seen = the_fix_stage.run(root, state, real_files=True, **run)
    said = [r["detail"] for r in read_transcript("r", {"defect"}) if r.get("event") == "rewrite after surrender"]
    return seen, said


def test_the_rewrite_takes_a_file_the_fixer_tried_to_write(tmp_path):
    """The fixer's edit of the module at fault was refused; the defect and its failure name only the acceptance test."""
    from app.observability.transcript import record

    _workspace(tmp_path)
    tried = lambda stage: record("r", stage, "tool_call", tool="edit_artifact",  # noqa: E731
                                 args={"relative_path": "proj/app/db.js", "find": "null", "replace": "open()"})

    seen, _ = _declined(tmp_path, the_fix_stage.a_state(tmp_path, _a_criterion_the_suite_judges()),
                        answer=GAVE_UP, during=tried)

    assert [r["files"] for r in seen.rewrites] == [["proj/app/db.js"]]


def test_the_rewrite_takes_a_file_the_fixer_named_in_its_answer(tmp_path):
    _workspace(tmp_path)
    named = SpecialistOutput(blockers=["proj/app/routes.js line 3 never reads the request body"])

    seen, _ = _declined(tmp_path, the_fix_stage.a_state(tmp_path, _a_criterion_the_suite_judges()), answer=named)

    assert [r["files"] for r in seen.rewrites] == [["proj/app/routes.js"]]


def test_a_rewrite_that_finds_no_file_names_each_file_and_the_rule_that_left_it_out(tmp_path):
    _workspace(tmp_path)

    seen, said = _declined(tmp_path, the_fix_stage.a_state(tmp_path, _a_criterion_the_suite_judges()), answer=GAVE_UP)

    assert seen.rewrites == [], "no rewrite is asked with no file to rewrite"
    [detail] = said
    assert "proj/acceptance/auth.spec.js" in detail and "the acceptance suite judges this criterion" in detail


def test_a_file_an_attempt_held_to_tests_may_not_write_is_named_with_that_rule(tmp_path):
    from app.tools import tests_only_writes

    _workspace(tmp_path)
    defect = the_fix_stage.a_defect("The sign-up handler accepts a duplicate name", affected_files=["proj/app/db.js"])

    _, said = _declined(tmp_path, the_fix_stage.a_state(tmp_path, defect), answer=GAVE_UP,
                        during=lambda stage: tests_only_writes.hold("r", stage))

    [detail] = said
    assert "`proj/app/db.js`: this attempt may write tests only" in detail


def test_a_rewrite_that_wrote_nothing_says_what_each_file_came_to(tmp_path):
    _workspace(tmp_path)

    def came_back_unchanged(defect, *, why, **_):
        why["why"] = "the rewrite wrote nothing: `proj/app/db.js` came back unchanged"

    _, said = _declined(tmp_path, the_fix_stage.a_state(tmp_path, the_fix_stage.a_defect(affected_files=["proj/app/db.js"])),
                        answer=GAVE_UP, rewrite=came_back_unchanged)

    assert said == ["declined: the rewrite wrote nothing: `proj/app/db.js` came back unchanged"]


def test_the_rewrite_says_which_file_came_back_unchanged(tmp_path):
    _workspace(tmp_path)
    defect = SimpleNamespace(description="The routes are empty", expected_behavior="They list", actual_behavior="",
                             affected_files=["proj/app/routes.js"], reproduction_steps=[])

    class SendsItBack:
        def invoke(self, messages, **kwargs):
            return SimpleNamespace(content="```js\n" + (tmp_path / "proj/app/routes.js").read_text() + "```")

    told: dict[str, str] = {}
    assert rewritten_fixes.fix_by_rewriting(defect, tmp_path, SendsItBack(), why=told) is None
    assert told["why"] == "the rewrite wrote nothing: `proj/app/routes.js` came back unchanged"


def test_a_file_a_trace_names_under_the_sandbox_s_mount_is_the_workspace_s(tmp_path):
    """Commands run in the sandbox print `/workspace/<project>/...`; read as `workspace/...`, it named no file."""
    _workspace(tmp_path)
    defect = SimpleNamespace(description="The count is wrong", expected_behavior="3", affected_files=[],
                             actual_behavior="TypeError: db is null\n    at open (/workspace/proj/app/db.js:3:5)",
                             reproduction_steps=[])

    files = rewritten_fixes.files_to_fix(defect, rewritten_fixes.what_failed(defect, tmp_path), tmp_path, lambda _: True)

    assert files == ["proj/app/db.js"]


def test_with_nothing_named_anywhere_the_decline_says_so():
    from app.graph import surrender_evidence

    assert "names a file" in surrender_evidence.why_none({})


@pytest.mark.parametrize("word", ["task", "tasks", "to-do", "todo", "button", "click", "checkbox"])
def test_the_decline_s_own_words_carry_no_product_word(word):
    import re

    from app.graph import surrender_evidence

    said = " ".join([surrender_evidence.why_none({}), surrender_evidence.why_none({"a.py": "x"})])
    assert not re.search(rf"\b{re.escape(word)}\b", said, re.I)
