"""Behind `STRUCTURED_DISPUTE_VERDICT` (off until measured), the dispute is read by one ruling per test, not its prose.

Plan item 19. The prose reading (`judged_by_the_code`) needed four patches, the last after "its own steps never set up"
was filed as a reason about the product and a test no product could pass stayed locked.
"""
from __future__ import annotations

import inspect
import re

from app.agents import suite_dispute
from app.agents.suite_dispute import DisputeRuling, SuiteDispute, SuiteDisputeWithRulings

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
FAILING = ["[AC-2][AC-9] list notes returns 200 with a JSON array", "[AC-4] updates a note"]
QUOTE = "AC-2 List all notes: GET /notes answers 200 with every note"


def _answer(*rulings, prose=()):
    return SuiteDisputeWithRulings(cannot_pass=list(prose), rulings=list(rulings))


def test_a_ruling_that_the_test_is_wrong_with_a_quote_reopens_it_whatever_its_words(monkeypatch):
    monkeypatch.setenv("STRUCTURED_DISPUTE_VERDICT", "on")
    ruling = DisputeRuling(test=FAILING[0], the_test_is_wrong=True,
                           the_test_asserts="titles starting `list-${slug}-` number two, though it sent `list-a-${slug}`",
                           the_standard_says=QUOTE)
    named = suite_dispute.tests_it_names(_answer(ruling), FAILING)
    assert len(named) == 1 and named[0].startswith(f"`{FAILING[0]}`") and QUOTE in named[0]
    assert not BANNED.search(named[0])


def test_a_ruling_for_the_product_or_without_a_quote_reopens_nothing(monkeypatch):
    monkeypatch.setenv("STRUCTURED_DISPUTE_VERDICT", "on")
    right = DisputeRuling(test=FAILING[1], the_test_is_wrong=False, the_test_asserts="the title changes",
                          the_standard_says="AC-4 Update a note's title and body")
    unquoted = DisputeRuling(test=FAILING[0], the_test_is_wrong=True, the_test_asserts="two notes", the_standard_says="")
    assert suite_dispute.tests_it_names(_answer(right, unquoted), FAILING) == []


def test_off_the_prose_is_read_and_the_model_sees_no_rulings(monkeypatch):
    monkeypatch.setenv("STRUCTURED_DISPUTE_VERDICT", "off")
    ruling = DisputeRuling(test=FAILING[0], the_test_is_wrong=True, the_test_asserts="two notes", the_standard_says=QUOTE)
    assert suite_dispute.tests_it_names(_answer(ruling), FAILING) == []
    assert "rulings" not in SuiteDispute.model_fields
    assert "SuiteDisputeWithRulings if structured_verdict_switch.enabled() else SuiteDispute" in inspect.getsource(
        suite_dispute.create_suite_dispute_agent)
    for field in DisputeRuling.model_fields.values():
        assert not BANNED.search(field.description or "")
