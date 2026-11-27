"""A fixer that finds a locked test no right product can pass says so and is heard, not overruled.

Measured on one run: two fixers worked out, in their own words, that a locked test's locator found two of its own
records ("the filter matches BOTH list items"), then wrote "but I can't change the test", spent every call reshaping a
right page, and gave no answer; nothing reached the QA lead until the attempt's rounds were spent. A fixer that does
answer "a locked test cannot pass" with nothing changed was handed to the harness's rewrite after a surrender, whose
change to the product replaced the answer naming the test, so no dispute was held either (LF.1616).

And the dispute, when it came, was shown the suite cut at 16,000 characters in the runner's order: the file holding two
of the three failing tests was never shown, and the judge ruled on code it wrote out from memory (LF.1618).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import the_fix_stage
from the_fix_stage import a_state

from app.acceptance import suite
from app.acceptance.criteria import Criterion
from app.agents import lean_fixer
from app.agents.specialists import SpecialistOutput

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_a_fixer_is_told_to_name_an_unpassable_locked_test_and_stop():
    prompt = lean_fixer.system_prompt("ui_ux")

    assert "no product meeting its criterion can pass" in prompt
    assert "change nothing for it, return at once, and put in `blockers` the test's name" in prompt


def test_the_rule_is_in_plain_words():
    assert not BANNED.search(lean_fixer.LOCKED_TEST_THAT_CANNOT_PASS)


@pytest.fixture
def locked(tmp_path: Path, monkeypatch) -> Path:
    (tmp_path / ".project-directory").write_text("app\n")
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "stack-pack.json").write_text(json.dumps({
        "pack": "any", "project": "app", "acceptance_dir": "acceptance",
        "unit_report": "r/unit.xml", "acceptance_report": "r/acceptance.xml",
    }))
    (tmp_path / "app" / "acceptance").mkdir(parents=True)
    (tmp_path / "app" / "acceptance" / "ui-validation.spec.js").write_text(
        "test('[AC-9] Bookmark items display title as link', async () => {});\n")
    suite.save_criteria(tmp_path, [Criterion("AC-9", "Each bookmark is an item", "brief")])
    suite.lock(tmp_path)
    monkeypatch.setenv("SURRENDER_TO_REWRITE", "on")
    monkeypatch.setattr("app.graph.workflow._the_locked_tests_still_failing",
                        lambda state: [("[AC-9] Bookmark items display title as link", "AC-9: x", "strict mode")])
    return tmp_path


BLAMES = SpecialistOutput(blockers=[
    "ui-validation.spec.js line 31 cannot pass: `filter({ hasText: `ac9-link-${t}` })` also matches the item of "
    "`ac9-link-${t}-no-tag`, a record the test makes itself"])
REWRITTEN = SpecialistOutput(changed_files=["app/public/main.js"], decisions=["Rewrote app/public/main.js"])


def test_an_answer_that_names_an_unpassable_locked_test_goes_to_the_qa_lead_not_the_rewrite(locked):
    update, seen = the_fix_stage.run(locked, a_state(locked), answer=BLAMES, rewrite=REWRITTEN)

    assert "rewrite" not in seen.events
    assert seen.settled == [BLAMES]
    assert update["stage"] == "acceptance_dispute"


def test_once_the_attempt_has_had_its_dispute_the_rewrite_is_tried_as_before(locked):
    state = a_state(locked, disputed_sprints=["0:0"])

    update, seen = the_fix_stage.run(locked, state, answer=BLAMES, rewrite=REWRITTEN)

    assert "rewrite" in seen.events
    assert seen.settled == [REWRITTEN]


def test_a_surrender_that_names_no_locked_test_is_rewritten_as_before(locked):
    _, seen = the_fix_stage.run(locked, a_state(locked), answer=SpecialistOutput(blockers=["the port is taken"]),
                                rewrite=REWRITTEN)

    assert "rewrite" in seen.events and seen.settled == [REWRITTEN]


def test_a_dispute_is_shown_the_files_of_the_tests_it_judges_first(tmp_path):
    (tmp_path / ".project-directory").write_text("app\n")
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "stack-pack.json").write_text(json.dumps({
        "pack": "any", "project": "app", "acceptance_dir": "acceptance",
        "unit_report": "r/unit.xml", "acceptance_report": "r/acceptance.xml",
    }))
    folder = tmp_path / "app" / "acceptance"
    folder.mkdir(parents=True)
    (folder / "api-bookmarks.spec.js").write_text("test('[AC-2] newest first', async () => {});\n" + "// x\n" * 2500)
    (folder / "delete-and-endpoints.spec.js").write_text("test('[AC-13] delete', async () => {});\n" + "// y\n" * 2500)
    (folder / "ui-validation.spec.js").write_text("test('[AC-9] Bookmark items', async () => {\n  JUDGED\n});\n")

    code = suite.the_code_for_a_dispute(tmp_path, ["[AC-9] Bookmark items"])

    assert len(code) <= suite.MOST_CODE_FOR_A_DISPUTE
    assert code.startswith("--- app/acceptance/ui-validation.spec.js ---") and "JUDGED" in code
