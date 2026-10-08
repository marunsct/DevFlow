"""A locked test held the product to an order no criterion stated, and another test to the opposite one.

Measured on one run: the locked list test added two items and expected the
second at position 0 and the first at position 1 - newest first - while the
locked removal test removed the first item and expected the second to remain -
oldest first. Neither criterion said anything about order. Each fix that made one
pass broke the other, twice in one round, before the QA lead was asked.

Before the suite is locked, a test that asserts what two places of a list show,
for criteria that state no order, is sent back to QA; and the QA lead is told
to compare tests that take the same steps.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.acceptance import suite
from app.acceptance.criteria import Criterion
from app.stacks import contract, pack_named
from app.stacks.packs._javascript import positions_it_asserts

NEWEST_FIRST = """test('[AC-8] items appear as list items', async ({ page }) => {
  await add(page, 'First item');
  await add(page, 'Second item');
  const items = page.locator('[data-testid="item"]');
  await expect(items.nth(0)).toContainText('Second item');
  await expect(items.nth(1)).toContainText('First item');
});
"""

REMOVAL = """test('[AC-4] an item can be removed', async ({ page }) => {
  const first = page.locator('[data-testid="item"]').first();
  await first.getByRole('button', { name: 'Remove' }).click();
  const remaining = page.locator('[data-testid="item"]').first();
  await expect(remaining).toContainText('Item two');
});
"""

ACTING_ON_PLACES = """test('[AC-5] views', async ({ page }) => {
  const items = page.getByRole('listitem');
  await items.nth(0).getByRole('checkbox').check();
  await items.nth(1).getByRole('checkbox').check();
  await expect(items.first()).toContainText('Done item');
});
"""


class TestWhatATestAssertsOfPlaces:
    def test_what_two_places_show_is_an_order(self):
        assert positions_it_asserts(NEWEST_FIRST) == [(4, "[AC-8] items appear as list items", ["0", "1"])]

    def test_one_place_read_twice_is_not(self):
        assert positions_it_asserts(REMOVAL) == []

    def test_places_acted_on_are_not(self):
        assert positions_it_asserts(ACTING_ON_PLACES) == []


def _project(tmp_path: Path, criterion_text: str) -> Path:
    contract.write(tmp_path, pack_named("browser-javascript"), "notes", "Notes")
    spec = tmp_path / "notes" / "acceptance" / "list.spec.js"
    spec.parent.mkdir(parents=True)
    spec.write_text(NEWEST_FIRST + REMOVAL)
    suite.save_criteria(tmp_path, [
        Criterion("AC-4", "An item can be removed", "brief"),
        Criterion("AC-8", criterion_text, "brief"),
    ])
    return tmp_path


class TestBeforeTheSuiteIsLocked:
    def test_an_order_no_criterion_states_is_sent_back(self, tmp_path):
        problems = suite.tests_that_assert_an_unstated_order(_project(tmp_path, "Each item is an item of a list"))

        assert len(problems) == 1
        assert "`[AC-8] items appear as list items` checks what 2 places of a list show" in problems[0]
        assert "AC-8 states none" in problems[0]

    def test_an_order_the_criterion_states_is_fine(self, tmp_path):
        root = _project(tmp_path, "Items are listed newest first")

        assert suite.tests_that_assert_an_unstated_order(root) == []

    def test_a_project_no_pack_set_up_is_not_checked(self, tmp_path):
        assert suite.tests_that_assert_an_unstated_order(tmp_path) == []


class TestTheQaLead:
    def test_is_told_to_compare_tests_that_take_the_same_steps(self):
        from app.agents.acceptance_reviewer import _SYSTEM_PROMPT

        assert "Two tests that take the same steps must expect\nthe same result" in _SYSTEM_PROMPT
        assert "Name every pair of tests whose expectations contradict" in _SYSTEM_PROMPT

    def test_the_new_words_name_no_product(self):
        from app.agents.acceptance_reviewer import _SYSTEM_PROMPT

        start = _SYSTEM_PROMPT.index("Then read the tests side by side")
        text = _SYSTEM_PROMPT[start:_SYSTEM_PROMPT.index("Do not ask for style changes")].lower()

        for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox"):
            assert not re.search(rf"\b{re.escape(word)}\b", text), word
