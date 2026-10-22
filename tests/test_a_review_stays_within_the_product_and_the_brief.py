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


class TestSecurityIsGradedByItsOwnReview:
    """One run's milestone review made the security review's medium finding
    major, twice in one sprint, and three attempts went on encryption."""

    @staticmethod
    def _milestone(*findings):
        from app.agents.milestone_reviewer import MilestoneReviewFinding, MilestoneReviewOutput

        return MilestoneReviewOutput(
            status="changes_required",
            findings=[MilestoneReviewFinding(severity=sev, category=cat, description=d, required_remediation="r")
                      for sev, cat, d in findings],
            acceptance_evidence="e", documentation_reviewed=True, tests_reviewed=True,
        )

    def test_a_security_finding_the_security_review_did_not_gate_is_minor(self) -> None:
        review = self._milestone(("major", "security", "XOR with a fixed key"), ("major", "correctness", "Save does nothing"))
        security = SecurityReviewOutput(status="findings", findings=[_finding("XOR with a fixed key").model_copy(update={"severity": "medium"})])

        graded = workflow._security_graded_by_its_own_review(review, security)

        assert [(f.category, f.severity) for f in graded.findings] == [("security", "minor"), ("correctness", "major")]

    def test_one_it_graded_high_still_gates(self) -> None:
        review = self._milestone(("blocking", "security", "Stored text runs as markup"))
        security = SecurityReviewOutput(status="findings", findings=[_finding("innerHTML").model_copy(update={"severity": "high"})])

        assert workflow._security_graded_by_its_own_review(review, security) is review

    def test_without_a_security_review_nothing_changes(self) -> None:
        review = self._milestone(("major", "security", "x"))

        assert workflow._security_graded_by_its_own_review(review, None) is review


class TestTheBriefSControlsStayUsable:
    """One run's interface design disabled the brief's "Add task" until its
    title held text; the customer's check that an empty entry is refused timed
    out waiting for the control."""

    BRIEF = 'A text field labelled "Title" and a button named "Add task".'

    def test_one_disabled_on_load_is_named(self) -> None:
        from app.analysis.interface_checks import named_controls_disabled_on_load

        shows = '- main:\n  - textbox "Title"\n  - button "Add task" [disabled]\n  - button "Other" [disabled]'

        assert named_controls_disabled_on_load(self.BRIEF, shows) == ["Add task"]
        assert named_controls_disabled_on_load(self.BRIEF, '- button "Add task"') == []

    def test_it_is_a_ui_ux_defect_that_names_no_product(self, tmp_path) -> None:
        import json
        from types import SimpleNamespace

        from app.acceptance import suite
        from app.graph import acceptance_nodes

        path = tmp_path / suite.RESULT_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"ran": True, "shows": '- button "Add task" [disabled]'}))

        defects = acceptance_nodes.interface_defects(
            {"repository": SimpleNamespace(root_path=str(tmp_path)), "document": SimpleNamespace(text=self.BRIEF)}
        )

        [defect] = [d for d in defects if "disabled" in d.description]
        assert defect.owner == "ui_ux" and '"Add task"' in defect.description
        rule = f"{defect.expected_behavior} {defect.reproduction_steps}".lower()
        for word in BANNED:
            assert not re.search(rf"\b{word}\b", rule), word

    def test_advice_never_disables_one(self) -> None:
        from app.agents.specialist_advice import _SYSTEM_PROMPT as ADVISOR

        assert "never by disabling the control" in ADVISOR


class TestALocatorThatContradictsItsAssertion:
    EDIT = (
        "test('[AC-3] edit', async ({ page }) => {\n"
        "  const item = page.getByRole('listitem').filter({ hasText: /Original/ });\n"
        "  await item.getByRole('button', { name: 'Edit' }).click();\n"
        "  await page.getByLabel('Edit title').fill('Updated');\n"
        "  await expect(item.locator('h3')).not.toContainText('Original');\n"
        "});\n"
    )

    def test_is_named_with_its_line(self) -> None:
        from app.stacks.packs._javascript import asserted_without_the_text_it_is_found_by

        assert asserted_without_the_text_it_is_found_by(self.EDIT) == [(5, "item", "Original")]

    def test_a_test_that_finds_it_again_by_its_new_text_is_not(self) -> None:
        from app.stacks.packs._javascript import asserted_without_the_text_it_is_found_by

        fixed = self.EDIT.replace(
            "await expect(item.locator('h3')).not.toContainText('Original');",
            "await expect(page.getByRole('listitem').filter({ hasText: 'Original' })).toHaveCount(0);",
        )

        assert asserted_without_the_text_it_is_found_by(fixed) == []

    def test_the_review_sends_it_back(self, tmp_path) -> None:
        from app.acceptance import suite
        from app.stacks.scaffold import scaffold

        pack = pack_named("browser-javascript")

        def smoke(argv, category, wd):
            report = tmp_path / wd / pack.acceptance_report
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text("<testsuites><testcase name='smoke'/></testsuites>")
            unit = tmp_path / wd / pack.unit_report
            unit.parent.mkdir(parents=True, exist_ok=True)
            unit.write_text("<testsuites><testcase name='smoke'/></testsuites>")
            return {"returncode": "0"}

        assert scaffold(tmp_path, pack, "notes", "Notes", run=smoke).ok
        (tmp_path / "notes" / "acceptance").mkdir(parents=True, exist_ok=True)
        (tmp_path / "notes" / "acceptance" / "edit.spec.js").write_text(self.EDIT)

        [problem] = suite.locators_that_contradict_their_assertions(tmp_path)

        assert "line 5" in problem and "keeps the old text hidden" in problem
        for word in BANNED:
            assert not re.search(rf"\b{word}\b", problem.split("(`")[0].lower()), word


def test_a_lead_is_told_untested_is_no_reason_to_decline() -> None:
    from app.agents.technical_lead import NOT_A_REASON_TO_DECLINE

    assert "is not a reason to decline it" in NOT_A_REASON_TO_DECLINE
    assert "no test checks an item is not a reason" in workflow._only_what_was_carried("x")
    for word in BANNED:
        assert not re.search(rf"\b{word}\b", NOT_A_REASON_TO_DECLINE.lower()), word


class TestALocatorLeftBehindByItsOwnChange:
    """One run's two locked edit tests found the item by its old title, changed
    it, then looked for the new title through the same locator - "element(s)
    not found" on every round of two attempts, handed to product fixers."""

    MESSAGE = (
        "expect(locator).toContainText(expected) failed\n\n"
        "    Locator: getByRole('listitem').filter({ hasText: 'Old entry' })\n"
        '    Expected substring: "New entry"\n'
        "    Timeout: 3000ms\n"
        "    Error: element(s) not found\n"
        "\nWhat the page showed when this failed:\n"
        "- main:\n  - list:\n    - listitem:\n      - text: New entry\n"
    )

    def test_is_read_from_the_failure_and_the_page(self) -> None:
        from app.stacks.packs._javascript import a_locator_left_behind

        assert a_locator_left_behind(self.MESSAGE) == ("Old entry", "New entry")

    @pytest.mark.parametrize("change", [
        ("New entry\n", "Something else\n"),         # the page does not show the change
        ("New entry\n", "Old entry New entry\n"),    # the page still shows the old text
        ("element(s) not found", "Received string: \"x\""),  # the locator found something
    ])
    def test_a_product_that_did_not_make_the_change_is_not_excused(self, change) -> None:
        from app.stacks.packs._javascript import a_locator_left_behind

        assert a_locator_left_behind(self.MESSAGE.replace(*change)) is None

    def test_it_goes_back_to_qa_as_a_test_that_cannot_pass(self, scaffolded) -> None:
        from app.acceptance import junit, suite

        result = suite.AcceptanceResult(ran=True, command="npm run test:acceptance", report=junit.Report(
            found=True, tests=[junit.TestResult(name="[AC-3] edits", outcome="failed", message=self.MESSAGE)],
        ))

        [problem] = suite.tests_left_behind_by_their_own_change(str(scaffolded), result)

        assert "`[AC-3] edits`" in problem and "Find the item again by the text it shows now" in problem


class TestASpecificationThatDisablesAControl:
    """One run's UI/UX advice, told never to disable a control the brief names,
    advised disabling it until its field held text; the architect adopted it,
    code review demanded it, the page check demanded the opposite, and the
    sprint's fixers undid each other until its attempts ran out."""

    @staticmethod
    def _spec(**sections):
        from app.agents.principal_architect import TechnicalSpecificationOutput
        from test_graph_routing import _spec

        return _spec(**sections)

    def test_is_sent_back_to_the_architect(self) -> None:
        from app.agents.specialist_advice import what_the_specification_owes

        spec = self._spec(
            interface_design=["The primary control is disabled until the first field holds text."],
            specialist_advice_decisions=["UX-1: adopted - interface_design"],
        )

        [problem] = what_the_specification_owes(spec, {"ui_ux": ["x"]})

        assert "disables a control until something is done" in problem
        for word in BANNED:
            assert not re.search(rf"\b{word}\b", problem.split('"')[0].lower() + problem.split('". ')[-1].lower()), word

    @pytest.mark.parametrize("line", [
        "Buttons have hover, focus and disabled states.",
        "A disabled control is shown at half opacity.",
        "The list fades in when the page loads.",
    ])
    def test_a_disabled_style_alone_is_not(self, line) -> None:
        from app.agents.specialist_advice import controls_disabled_until_something

        assert controls_disabled_until_something(self._spec(interface_design=[line])) == []


class TestAdviceThatDisablesAControlIsLeftOut:
    """Given anyway on two runs, adopted, and in the second carried forward as
    owed work by the sprint's advice check."""

    @pytest.mark.parametrize("item", [
        "The 'Add task' button is disabled (aria-disabled=true) until the Title input has at least one non-space character.",
        "Enable the primary control only when the first field holds text.",
        "The save control becomes active once the field is edited.",
    ])
    def test_is_dropped(self, item) -> None:
        from types import SimpleNamespace

        from app.agents.specialist_advice import advice_from

        kept = advice_from(SimpleNamespace(recommendations=[item, "Stack the form above the list below 600px."]))

        assert kept == ["Stack the form above the list below 600px."]

    def test_a_disabled_style_is_kept(self) -> None:
        from types import SimpleNamespace

        from app.agents.specialist_advice import advice_from

        item = "Give controls hover, focus and disabled styles from one palette."

        assert advice_from(SimpleNamespace(recommendations=[item])) == [item]


def test_disabling_advice_adopted_earlier_is_never_owed() -> None:
    from types import SimpleNamespace

    from app.agents.specialist_advice import adopted

    advice = {"ui_ux": ["Stack the form above the list.", "The add control is disabled until the title holds text."]}
    spec = SimpleNamespace(specialist_advice_decisions=["UX-1: adopted", "UX-2: adopted"])

    assert adopted(advice, spec, "ui_ux") == ["UX-1: Stack the form above the list."]


def test_a_specification_that_disables_on_a_condition_in_any_wording_is_caught() -> None:
    """One run's specification said "If invalid, the form disables the Add
    button" - a verb form and an order the first pattern did not know."""
    from app.agents.specialist_advice import disables_on_a_condition

    assert disables_on_a_condition("2. If invalid, the form disables the primary control (`disabled` attribute).")
    assert disables_on_a_condition("On an empty field the control is disabled.")
    assert not disables_on_a_condition("Visual states: placeholder, focus ring, hover, disabled, toast.")


class TestALocatorFilteredByAFieldValue:
    """One run's locked edit tests found "Edit title" and "Save" inside the item
    filtered by its title; while it was edited the item held a field whose
    value was the title, so the filter matched nothing, on every round of
    three attempts at a sprint."""

    @staticmethod
    def _message(locator: str, list_lines: str) -> str:
        return (
            "Error: locator.click: Timeout 3000ms exceeded.\n    Call log:\n"
            f"      - waiting for {locator}\n\n"
            "What the page showed when this failed:\n- main:\n  - list:\n    - listitem:\n" + list_lines
        )

    def test_the_title_moved_into_the_field(self) -> None:
        from app.stacks.packs._javascript import a_locator_filtered_by_a_field_value

        message = self._message(
            "getByRole('listitem').filter({ hasText: 'Entry one' }).getByLabel('Edit title')",
            '      - textbox "Edit title": Entry one\n      - button "Save"\n',
        )

        assert a_locator_filtered_by_a_field_value(message) == "Entry one"

    def test_the_field_already_holds_the_new_title(self) -> None:
        from app.stacks.packs._javascript import a_locator_filtered_by_a_field_value

        message = self._message(
            "getByRole('listitem').filter({ hasText: 'Entry one' }).getByRole('button', { name: 'Save' })",
            '      - textbox "Edit title": Entry two\n      - button "Save"\n',
        )

        assert a_locator_filtered_by_a_field_value(message) == "Entry one"

    @pytest.mark.parametrize("list_lines", [
        "      - text: Entry one\n",                                      # shown as text: the filter would match
        '      - textbox "Edit title": Entry two\n',                      # what it looked for is not there
    ])
    def test_a_product_that_lost_the_item_is_not_excused(self, list_lines) -> None:
        from app.stacks.packs._javascript import a_locator_filtered_by_a_field_value

        message = self._message(
            "getByRole('listitem').filter({ hasText: 'Entry one' }).getByRole('button', { name: 'Save' })",
            list_lines,
        )

        assert a_locator_filtered_by_a_field_value(message) is None

    def test_it_reopens_the_suite(self, scaffolded) -> None:
        from app.acceptance import junit, suite

        message = self._message(
            "getByRole('listitem').filter({ hasText: 'Entry one' }).getByLabel('Edit title')",
            '      - textbox "Edit title": Entry one\n',
        )
        result = suite.AcceptanceResult(ran=True, command="npm run test:acceptance", report=junit.Report(
            found=True, tests=[junit.TestResult(name="[AC-3] edits", outcome="failed", message=message)],
        ))

        [problem] = suite.tests_left_behind_by_their_own_change(str(scaffolded), result)

        assert "only as the value of a field" in problem
        for word in BANNED:
            assert not re.search(rf"\b{word}\b", problem.split("`")[-1].lower()), word
