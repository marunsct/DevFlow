"""QA repairing a locked suite repairs every test with the named test's fault, not only the named ones.

Measured on a held-out run: a test round named two tests that signed in as a user the test never created. QA
saw the same fault in seven more tests, read "change only the tests named above", and left them. The next round
failed those seven, the dispute cap was spent on the first two, and the sprint was planned again, twice.
"""
from __future__ import annotations

import re

from app.acceptance import suite
from app.graph import acceptance_nodes
from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

HEAD = "import { test, expect } from '@playwright/test';\n"
ONE = "test('[AC-2] lists', async ({ request }) => {\n  expect(1).toBe(1);\n  expect(mine.length).toBe(2);\n});\n"
TWO = "test('[AC-3] reads', async ({ request }) => {\n  expect(1).toBe(1);\n  expect(mine.length).toBe(3);\n});\n"


def test_the_rule_lets_a_test_with_the_same_fault_be_repaired_in_the_same_pass():
    rule = acceptance_nodes.REPAIR_RULE
    assert "not named above that has the very same fault" in rule
    assert "repaired the same way in this pass" in rule
    assert "stays exactly as it is" in rule and "repaired, not rewritten" in rule


def test_the_rule_names_no_product_words():
    assert not BANNED.search(acceptance_nodes.REPAIR_RULE)


def test_a_repair_that_also_changes_a_sibling_is_reviewed_whole_not_locked_on_the_checks(tmp_path):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True, exist_ok=True)
    spec = folder / "api.spec.js"
    spec.write_text(HEAD + ONE + TWO)
    suite.lock(tmp_path)
    suite.unlock(tmp_path)
    suite.repairing(tmp_path, ["[AC-2] lists"])
    spec.write_text(HEAD + ONE.replace("mine", "ours") + TWO.replace("mine", "ours"))
    assert suite.only_the_repaired_tests_changed(tmp_path) is False
