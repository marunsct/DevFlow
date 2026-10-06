"""Reviews and advice stay within the product the brief describes.

Measured on one run's last sprint:
- the security review found that the harness's own test server serves any
  file under the project; the milestone review copied it as a major finding
  and the sprint was sent back for work no work order may do;
- the same review rated records kept in the user's own browser "readable via
  devtools" medium, the milestone review made it major, and two attempts were
  spent base64-encoding them;
- the database specialist advised that titles be unique, the architect adopted
  it, and the product refused a second record with a title already in use -
  a rule the brief never states.
"""

from __future__ import annotations

import re

import pytest

from app.agents.security_reviewer import (
    BROWSER_KEPT_DATA,
    SecurityFinding,
    SecurityReviewOutput,
    _SYSTEM_PROMPT,
)
from app.graph import workflow
from app.stacks import contract, pack_named

BANNED = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")


def _finding(description: str, files: list[str] | None = None) -> SecurityFinding:
    return SecurityFinding(
        severity="medium", category="filesystem", description=description,
        affected_files=files or [], remediation="Restrict what it serves.",
    )


@pytest.fixture
def scaffolded(tmp_path):
    contract.write(tmp_path, pack_named("browser-javascript"), "notes", "Notes")
    return tmp_path


class TestAFindingAboutTheHarnessSFiles:
    def test_is_left_out(self, scaffolded) -> None:
        review = SecurityReviewOutput(status="findings", findings=[
            _finding("The development server in scripts/serve.mjs serves any file under the project."),
            _finding("load() in src/storage.js parses stored text without a guard."),
            _finding("Nothing names a file here."),
            _finding("serve.mjs and app.js both expose it."),
        ])

        kept = workflow._without_findings_about_the_harness_s_files(review, str(scaffolded))

        assert [f.description[:16] for f in kept.findings] == [
            "load() in src/st", "Nothing names a ", "serve.mjs and ap",
        ]
        assert kept.status == "findings"

    def test_named_only_in_its_files(self, scaffolded) -> None:
        review = SecurityReviewOutput(status="findings", findings=[
            _finding("It serves any file under the project.", ["notes/scripts/serve.mjs"]),
        ])

        kept = workflow._without_findings_about_the_harness_s_files(review, str(scaffolded))

        assert kept.findings == [] and kept.status == "passed"

    def test_a_workspace_with_no_contract_keeps_everything(self, tmp_path) -> None:
        review = SecurityReviewOutput(status="findings", findings=[_finding("scripts/serve.mjs serves it.")])

        assert workflow._without_findings_about_the_harness_s_files(review, str(tmp_path)) is review


def test_the_security_reviewer_is_told_whose_browser_data_is_whose() -> None:
    assert BROWSER_KEPT_DATA in _SYSTEM_PROMPT
    for word in BANNED:
        assert not re.search(rf"\b{word}\b", BROWSER_KEPT_DATA.lower()), word


def test_advice_adds_no_rule_the_brief_does_not_state() -> None:
    from app.agents.specialist_advice import _SYSTEM_PROMPT as ADVISOR, advice_block

    rule = "Nor may advice add a rule the brief does not state that refuses or limits what a person may do"
    assert rule in ADVISOR
    told = advice_block({"database": ["Reject a second record with the same name."]})
    assert "it adds a rule the brief does not state that refuses or limits what a person may do" in told
    sentence = ADVISOR[ADVISOR.index(rule):].split("Each recommendation")[0].lower()
    for word in BANNED:
        assert not re.search(rf"\b{word}\b", sentence), word
